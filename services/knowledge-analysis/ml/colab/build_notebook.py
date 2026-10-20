"""Assemble train_career_model.ipynb from cell sources via nbformat.

Keeping the notebook in a builder (instead of hand-written JSON) means the cells stay
valid and the hand-written model core is embedded *verbatim* from ml/career_lib.py — so
the notebook can never drift from the library/CLI. Run:  python ml/colab/build_notebook.py
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

HERE = Path(__file__).resolve().parent
CAREER_LIB = (HERE.parent / "career_lib.py").read_text(encoding="utf-8")

nb = nbf.v4.new_notebook()
cells = []
def md(s: str): cells.append(nbf.v4.new_markdown_cell(s.strip("\n")))
def code(s: str): cells.append(nbf.v4.new_code_cell(s.strip("\n")))


md(r"""
# Career-Fit Prediction — Hand-made ML Model (research notebook)

**Goal.** Map a learner's measured Java competency profile to a **best-fit software role**
with a **calibrated** confidence, using a *from-scratch* multinomial logistic regression
(softmax + gradient descent in NumPy — no scikit-learn/torch for the model itself).

**Why weak supervision.** There is no public dataset of *(student-quiz-profile → real job)*.
So we encode domain knowledge — an O*NET/ESCO-informed **role→competency matrix** — and
generate synthetic learners labelled by competency *shape* (cosine to the matrix). The
Stack Overflow Developer Survey supplies realistic **class priors** and a **face-validity**
cross-check. This is stated as a limitation, not hidden.

**Instrumentation note.** The *model* is hand-written; `matplotlib`/`seaborn`/`sklearn.metrics`
are used **only** for plots and scoring curves (ROC/PR/confusion), which is standard.

**Outputs.** `career_artifacts.zip` = `model_weights.npz`, `scaler.json`, `role_matrix.json`,
`label_map.json`, `feature_axes.json`, `metrics.json` — dropped into
`app/services/career/artifacts/` to serve the model.
""")

md(r"""
## 1. Setup — install dependencies (▶ RUN THIS CELL FIRST)

This installs everything the notebook needs **into the current kernel**, on Colab or locally
(VS Code / Jupyter). It's safe to re-run — already-installed packages are skipped. If you're
running locally and the *imports* cell below fails right after this, **restart the kernel once**
(VS Code: the ↻ button) so it picks up the freshly installed packages, then Run All again.
""")
code(r"""
# --- required environment (run before anything else) ---
%pip install -q numpy pandas matplotlib seaborn scikit-learn
print("✅ Dependencies installed. If the next cell errors with ModuleNotFound, RESTART the kernel once.")
""")
code(r"""
import sys, os
IN_COLAB = "google.colab" in sys.modules
import numpy as np, pandas as pd, json, io, zipfile, urllib.request
import matplotlib, matplotlib.pyplot as plt
import seaborn as sns
try:
    get_ipython().run_line_magic("matplotlib", "inline")  # embed figures in the notebook
except Exception:
    pass
sns.set_theme(context="notebook", style="whitegrid")
np.random.seed(42)
print("✅ Imports OK. Running on Colab:", IN_COLAB)
""")

md(r"""
## 2. The hand-made model core (read this — the gradient descent lives here)

The next cell writes `career_lib.py` (embedded verbatim) and imports it. The learning
algorithm is `train_softmax` — full-batch gradient descent on the cross-entropy loss:

$$P(y=k\mid x)=\mathrm{softmax}(Wx+b)_k,\qquad
\mathcal{L}=-\tfrac1N\sum_i\log P(y_i\mid x_i)+\lambda\lVert W\rVert^2$$

with the update $W \leftarrow W - \eta\,\nabla_W\mathcal{L}$. Calibration (`fit_temperature`)
divides the logits by a learned scalar $T$ so the confidences match observed accuracy.
""")
code("%%writefile career_lib.py\n" + CAREER_LIB)
code(r"""
import career_lib as cl
M = cl.matrix_to_array(cl.DEFAULT_ROLE_MATRIX, cl.ROLES)
K = len(cl.ROLES)
print("Roles (K=%d):" % K); [print("  %d. %s" % (i, r)) for i, r in enumerate(cl.ROLES)]
print("Axes:", cl.FEATURE_AXES)
""")

md(r"""
## 3. Get the Stack Overflow survey (public — **no Kaggle login**)

Downloaded straight from Stack Overflow's official GitHub mirror — no account or API token,
on Colab or locally. The full file (~150 MB, 84 columns incl. `DevType`) is **cached** under
`~/.cache/mentora_so`, so it only downloads once. To use a CSV you already have, set `SO_CSV`
to its path and the download is skipped. If the download fails for any reason, the notebook
**falls back to uniform priors** and still trains + plots everything.
""")
code(r"""
# Set SO_CSV to a local full survey CSV to use it; otherwise it auto-downloads the public one.
SO_CSV = None
SO_YEAR = "2023"   # 2023 / 2024 / 2025 all expose the same DevType column
SO_URL = ("https://github.com/StackExchange/Survey/raw/refs/heads/main/"
          "packages/archive/%s/results.csv" % SO_YEAR)
CACHE = os.path.expanduser("~/.cache/mentora_so")

if not SO_CSV:
    try:
        os.makedirs(CACHE, exist_ok=True)
        target = os.path.join(CACHE, "results_%s.csv" % SO_YEAR)
        if not os.path.exists(target) or os.path.getsize(target) < 1_000_000:
            print("Downloading Stack Overflow %s survey (~150 MB, one-time)…" % SO_YEAR)
            urllib.request.urlretrieve(SO_URL, target)
        SO_CSV = target
        print("✅ SO_CSV = %s  (%.0f MB)" % (SO_CSV, os.path.getsize(SO_CSV) / 1e6))
    except Exception as e:
        print("Auto-download failed (%s) -> uniform priors (model still fine)." % e)
        SO_CSV = None
else:
    print("Using provided SO_CSV =", SO_CSV)
""")
code(r"""
# Class priors from SO DevType. Falls back to uniform if the survey is absent OR the
# CSV has no DevType column (e.g. a 'selected-columns' subset) — with a clear message.
priors, so_df = None, None
if SO_CSV and os.path.exists(SO_CSV):
    df = pd.read_csv(SO_CSV, low_memory=False)
    if "DevType" not in df.columns:
        print("WARNING: %s has no 'DevType' column." % SO_CSV)
        print("  columns found:", list(df.columns)[:10])
        print("  -> This is a reduced/'selected-columns' export. For real priors download the")
        print("     FULL survey_results_public.csv. Using UNIFORM priors for now (model is fine).")
    else:
        so_df = df
        counts = np.ones(K)  # Laplace smoothing so no class is zero
        ridx = cl.role_index(cl.ROLES)
        for cell in so_df["DevType"].dropna():
            low = str(cell).lower()
            for key, role in cl.DEVTYPE_TO_ROLE.items():
                if key in low:
                    counts[ridx[role]] += 1; break
        priors = counts
        print("SO priors:", dict(zip(cl.ROLES, counts.astype(int))))
else:
    print("No SO survey CSV at SO_CSV -> uniform priors (model trains fine).")

# Optional HF cross-check (non-fatal).
try:
    from datasets import load_dataset
    ds = load_dataset("fazni/roles-based-on-skills")
    print("Loaded fazni/roles-based-on-skills:", ds)
except Exception as e:
    print("HF cross-check skipped:", e)
""")

md("## 4. Synthesize the training set (weak supervision)")
code(r"""
X, y = cl.sample_synthetic_learners(M, n_samples=12000, priors=priors, seed=42)
print("X:", X.shape, "y:", y.shape)
counts = np.bincount(y, minlength=K)
for i, r in enumerate(cl.ROLES):
    print("  %-36s %5d" % (r, counts[i]))
""")

md("### 4a. Class distribution")
code(r"""
fig, ax = plt.subplots(figsize=(8, 4))
ax.bar(range(K), np.bincount(y, minlength=K), color=sns.color_palette("deep", K))
ax.set_xticks(range(K)); ax.set_xticklabels([r.split(" ")[0] for r in cl.ROLES], rotation=20)
ax.set_ylabel("synthetic learners"); ax.set_title("Class distribution (priors-adjusted)")
plt.tight_layout(); plt.show()
# What this shows: training base rates per role (skewed toward real-world priors if SO loaded).
""")

md("### 4b. Per-axis competency distributions by role")
code(r"""
fig, axes = plt.subplots(2, 4, figsize=(15, 6))
for a, ax in enumerate(axes.ravel()):
    ax.boxplot([X[y == k, a] for k in range(K)], showfliers=False)
    ax.set_title("%s %s" % (cl.FEATURE_AXES[a], cl.AXIS_NAMES[cl.FEATURE_AXES[a]]), fontsize=8)
    ax.set_xticks(range(1, K + 1)); ax.set_xticklabels(range(K)); ax.set_ylim(0, 1)
plt.suptitle("Axis value distribution per role (x-axis = role index)"); plt.tight_layout(); plt.show()
# What this shows: each role's competency 'shape' — e.g. DSA peaks on A3/A4, Systems on A6.
""")

md("### 4c. Axis correlation + role→competency matrix")
code(r"""
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5))
sns.heatmap(np.corrcoef(X.T), annot=True, fmt=".2f", xticklabels=cl.FEATURE_AXES,
            yticklabels=cl.FEATURE_AXES, cmap="coolwarm", center=0, ax=a1)
a1.set_title("Feature correlation (8 axes)")
sns.heatmap(M, annot=True, fmt=".2f", xticklabels=cl.FEATURE_AXES,
            yticklabels=[r.split(" ")[0] for r in cl.ROLES], cmap="viridis", ax=a2)
a2.set_title("Role → competency requirement matrix M")
plt.tight_layout(); plt.show()
""")

md("### 4d. PCA — is the feature space separable?")
code(r"""
from sklearn.decomposition import PCA
mu_all, sd_all = cl.fit_standardizer(X)
Z2 = PCA(n_components=2, random_state=42).fit_transform(cl.apply_standardizer(X, mu_all, sd_all))
fig, ax = plt.subplots(figsize=(7, 6))
for k in range(K):
    m = y == k
    ax.scatter(Z2[m, 0], Z2[m, 1], s=6, alpha=0.4, label=cl.ROLES[k].split(" ")[0])
ax.legend(markerscale=2, fontsize=8); ax.set_xlabel("PC1"); ax.set_ylabel("PC2")
ax.set_title("PCA of standardized features (coloured by role)"); plt.tight_layout(); plt.show()
# What this shows: classes overlap (by design — label noise), so the problem isn't trivial.
""")

md("## 5. Train (hand-written softmax + gradient descent)")
code(r"""
tr, va, te = cl.stratified_split(y, seed=42)
mu, sd = cl.fit_standardizer(X[tr])
Xz = cl.apply_standardizer(X, mu, sd)
freq = np.bincount(y[tr], minlength=K).astype(float)
class_weight = freq.sum() / (K * (freq + 1e-9))   # inverse-frequency weighting

res = cl.train_softmax(Xz[tr], y[tr], K, lr=0.5, lam=1e-3, epochs=1500,
                       Xval=Xz[va], yval=y[va], class_weight=class_weight, seed=42)
W, b, hist = res["W"], res["b"], res["history"]
print("final train acc=%.3f  val acc=%.3f" % (hist["train_acc"][-1], hist["val_acc"][-1]))
""")

md("### 5a. Gradient-descent loss curve  +  train-vs-validation")
code(r"""
fig, axs = plt.subplots(1, 3, figsize=(16, 4))
axs[0].plot(hist["train_loss"]); axs[0].set_title("Gradient descent: training loss")
axs[0].set_xlabel("epoch"); axs[0].set_ylabel("cross-entropy + L2")
axs[1].plot(hist["train_loss"], label="train")
axs[1].plot(hist["val_loss"], label="validation"); axs[1].legend()
axs[1].set_title("Train vs validation loss"); axs[1].set_xlabel("epoch")
axs[2].plot(hist["train_acc"], label="train")
axs[2].plot(hist["val_acc"], label="validation"); axs[2].legend()
axs[2].set_title("Train vs validation accuracy"); axs[2].set_xlabel("epoch")
plt.tight_layout(); plt.show()
# What this shows: GD converging; small train/val gap = good generalization (not overfit).
""")
code(r"""
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(hist["grad_norm"]); ax.set_yscale("log")
ax.set_title("Gradient norm vs epoch (convergence)"); ax.set_xlabel("epoch"); ax.set_ylabel("||∇W|| (log)")
plt.tight_layout(); plt.show()
""")

md("## 6. Calibration (temperature scaling)")
code(r"""
val_logits = cl.logits(Xz[va], W, b)
T = cl.fit_temperature(val_logits, y[va])
test_logits = cl.logits(Xz[te], W, b)
probs_uncal = cl.softmax(test_logits)
probs_cal = cl.softmax(test_logits / T)
ece_b = cl.expected_calibration_error(probs_uncal, y[te])
ece_a = cl.expected_calibration_error(probs_cal, y[te])
print("Temperature T=%.3f   ECE before=%.4f  after=%.4f" % (T, ece_b, ece_a))
""")
code(r"""
def reliability(ax, probs, yt, title):
    conf, pred = probs.max(1), probs.argmax(1)
    correct = (pred == yt).astype(float)
    bins = np.linspace(0, 1, 11); xs, ys = [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any(): xs.append(conf[m].mean()); ys.append(correct[m].mean())
    ax.plot([0, 1], [0, 1], "--", color="gray")
    ax.plot(xs, ys, "o-"); ax.set_xlabel("confidence"); ax.set_ylabel("accuracy")
    ax.set_title(title); ax.set_xlim(0, 1); ax.set_ylim(0, 1)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 5))
reliability(a1, probs_uncal, y[te], "Before (ECE=%.3f)" % ece_b)
reliability(a2, probs_cal, y[te], "After temperature scaling (ECE=%.3f)" % ece_a)
plt.tight_layout(); plt.show()
# What this shows: points nearer the diagonal = better-calibrated confidences.
""")

md("## 7. Evaluation")
code(r"""
from sklearn.metrics import classification_report
y_pred = probs_cal.argmax(1)
cm = cl.confusion_matrix(y[te], y_pred, K)
prf = cl.precision_recall_f1(cm)
print("Top-1 acc : %.3f" % (y_pred == y[te]).mean())
print("Top-3 acc : %.3f" % cl.topk_accuracy(probs_cal, y[te], 3))
print("Macro-F1  : %.3f\n" % prf["macro_f1"])
print(classification_report(y[te], y_pred, target_names=[r.split(" ")[0] for r in cl.ROLES]))
""")
code(r"""
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5))
sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
            xticklabels=[r.split(" ")[0] for r in cl.ROLES],
            yticklabels=[r.split(" ")[0] for r in cl.ROLES], ax=a1)
a1.set_xlabel("predicted"); a1.set_ylabel("true"); a1.set_title("Confusion matrix")
xpos = np.arange(K)
a2.bar(xpos - 0.25, prf["precision"], 0.25, label="precision")
a2.bar(xpos, prf["recall"], 0.25, label="recall")
a2.bar(xpos + 0.25, prf["f1"], 0.25, label="F1")
a2.set_xticks(xpos); a2.set_xticklabels([r.split(" ")[0] for r in cl.ROLES], rotation=20)
a2.legend(); a2.set_title("Per-class precision / recall / F1"); a2.set_ylim(0, 1)
plt.tight_layout(); plt.show()
""")
code(r"""
from sklearn.preprocessing import label_binarize
from sklearn.metrics import roc_curve, auc, precision_recall_curve
Yte = label_binarize(y[te], classes=list(range(K)))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 5))
for k in range(K):
    fpr, tpr, _ = roc_curve(Yte[:, k], probs_cal[:, k])
    a1.plot(fpr, tpr, label="%s (AUC=%.2f)" % (cl.ROLES[k].split(" ")[0], auc(fpr, tpr)))
    pr, rc, _ = precision_recall_curve(Yte[:, k], probs_cal[:, k])
    a2.plot(rc, pr, label=cl.ROLES[k].split(" ")[0])
a1.plot([0, 1], [0, 1], "--", color="gray"); a1.set_title("ROC (one-vs-rest)")
a1.set_xlabel("FPR"); a1.set_ylabel("TPR"); a1.legend(fontsize=8)
a2.set_title("Precision–Recall (one-vs-rest)"); a2.set_xlabel("recall"); a2.set_ylabel("precision"); a2.legend(fontsize=8)
plt.tight_layout(); plt.show()
""")

md("## 8. Interpretability — what drives each role?")
code(r"""
fig, ax = plt.subplots(figsize=(9, 5))
sns.heatmap(W, annot=True, fmt=".2f", center=0, cmap="coolwarm",
            xticklabels=cl.FEATURE_AXES, yticklabels=[r.split(" ")[0] for r in cl.ROLES], ax=ax)
ax.set_title("Learned weight matrix W (row=role, col=axis)"); plt.tight_layout(); plt.show()
# What this shows: positive weight = that axis pushes toward that role (e.g. A6→Systems).
""")

md("## 9. Model selection — learning-rate / λ sweep")
code(r"""
rows = []
for lr in [0.1, 0.3, 0.5, 1.0]:
    for lam in [0.0, 1e-3, 1e-2]:
        r = cl.train_softmax(Xz[tr], y[tr], K, lr=lr, lam=lam, epochs=400,
                             Xval=Xz[va], yval=y[va], class_weight=class_weight, seed=42)
        rows.append((lr, lam, r["history"]["val_acc"][-1]))
sweep = pd.DataFrame(rows, columns=["lr", "lambda", "val_acc"])
piv = sweep.pivot(index="lr", columns="lambda", values="val_acc")
fig, ax = plt.subplots(figsize=(7, 4))
sns.heatmap(piv, annot=True, fmt=".3f", cmap="YlGn", ax=ax)
ax.set_title("Validation accuracy across (lr, λ)"); plt.tight_layout(); plt.show()
""")

md("## 10. Face validity vs Stack Overflow `DevType` (Cohen's κ)")
code(r"""
if so_df is not None:
    from sklearn.metrics import cohen_kappa_score
    OOP = ["java", "c#", "c++", "kotlin", "python", "scala"]
    CONC = ["go", "rust", "c++", "java", "scala"]
    rows, truth = [], []
    ridx = cl.role_index(cl.ROLES)
    sample = so_df.dropna(subset=["DevType"]).sample(min(3000, len(so_df)), random_state=42)
    for _, r in sample.iterrows():
        langs = str(r.get("LanguageHaveWorkedWith", "")).lower()
        yrs = pd.to_numeric(r.get("YearsCodePro", 3), errors="coerce"); yrs = 3 if pd.isna(yrs) else yrs
        lvl = min(0.4 + 0.05 * float(yrs), 0.95)
        vec = [lvl, lvl if any(o in langs for o in OOP) else 0.4, lvl, lvl,
               lvl, 0.7 if any(c in langs for c in CONC) else 0.35, lvl, 0.5]
        rows.append(vec)
        low = str(r["DevType"]).lower()
        truth.append(next((ridx[role] for key, role in cl.DEVTYPE_TO_ROLE.items() if key in low), None))
    rows = np.array(rows); keep = [i for i, t in enumerate(truth) if t is not None]
    pred = cl.predict_proba(rows[keep], W, b, mu, sd, T).argmax(1)
    kappa = cohen_kappa_score([truth[i] for i in keep], pred)
    print("Face-validity Cohen's κ (model vs SO DevType heuristic): %.3f over %d devs" % (kappa, len(keep)))
    print("NOTE: SO measures multi-language pros, not Java sub-skills — κ is a sanity check, not ground truth.")
else:
    print("SO survey not loaded — skipping the κ cross-check.")
""")

md("## 11. Export artifacts")
code(r"""
OUT = "career_artifacts"; os.makedirs(OUT, exist_ok=True)
np.savez(os.path.join(OUT, "model_weights.npz"), W=W, b=b, T=np.array([T]))
json.dump({"mu": mu.tolist(), "sd": sd.tolist(), "axes": cl.FEATURE_AXES},
          open(os.path.join(OUT, "scaler.json"), "w"), indent=2)
json.dump(cl.DEFAULT_ROLE_MATRIX, open(os.path.join(OUT, "role_matrix.json"), "w"), indent=2)
json.dump({r: i for i, r in enumerate(cl.ROLES)}, open(os.path.join(OUT, "label_map.json"), "w"), indent=2)
json.dump({"axes": cl.FEATURE_AXES, "names": cl.AXIS_NAMES}, open(os.path.join(OUT, "feature_axes.json"), "w"), indent=2)
json.dump({"model_version": "numpy-softmax-colab",
           "test_top1_acc": round(float((y_pred == y[te]).mean()), 4),
           "test_top3_acc": round(cl.topk_accuracy(probs_cal, y[te], 3), 4),
           "macro_f1": round(prf["macro_f1"], 4),
           "ece_before": round(ece_b, 4), "ece_after": round(ece_a, 4),
           "temperature": round(T, 4), "confusion_matrix": cm.tolist()},
          open(os.path.join(OUT, "metrics.json"), "w"), indent=2)

with zipfile.ZipFile("career_artifacts.zip", "w") as z:
    for f in os.listdir(OUT):
        z.write(os.path.join(OUT, f), f)
print("Wrote career_artifacts.zip")
if IN_COLAB:
    from google.colab import files; files.download("career_artifacts.zip")
""")

md(r"""
## 12. Conclusion & threats to validity

- **What this is:** a calibrated, interpretable role classifier over 8 SWEBOK-aligned axes,
  trained by weak supervision from an O*NET/ESCO-informed matrix.
- **Threats:** (1) *label provenance* — trained on synthetic profiles, so it learns the matrix's
  boundaries, not real hiring outcomes; (2) *domain shift* — SO survey ≠ Java learners (κ is a
  sanity check only); (3) *narrow signal* — a short Java quiz is thin evidence, hence the
  service's evidence gate and "aspirational/insufficient evidence" flag for non-SE roles.
- **Upgrade path:** log `(profile → shown prediction → feedback)` in production and retrain on
  real labels; this notebook then swaps synthetic `X,y` for the logged data unchanged.

Drop `career_artifacts.zip` into `app/services/career/artifacts/` to serve the model.
""")

nb["cells"] = cells
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nb.metadata["language_info"] = {"name": "python"}
out_path = HERE / "train_career_model.ipynb"
nbf.write(nb, str(out_path))
print("Wrote", out_path, "with", len(cells), "cells")
