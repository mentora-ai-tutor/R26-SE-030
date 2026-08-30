"""Generate academic figures for the career-fit model into ml/figures/.

Loads the committed serving artifacts, regenerates the SAME seeded test split as
evaluate.py, and renders publication-ready PNGs for the report:
  1. confusion_matrix.png    — row-normalised, counts annotated
  2. per_class_metrics.png   — precision / recall / F1 per role
  3. reliability_diagram.png — calibration before vs after temperature scaling

Numbers match metrics.json / evaluate.py (same seed, same artifacts).

Run (in an env with matplotlib + numpy):
  python ml/make_figures.py [--seed 42] [--out ml/figures]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import career_lib as cl  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parents[1] / "app" / "services" / "career" / "artifacts"
SHORT = ["Backend", "General SE", "DSA", "Systems", "QA"]


def load_artifacts(path: Path):
    w = np.load(path / "model_weights.npz")
    scaler = json.loads((path / "scaler.json").read_text())
    return w["W"], w["b"], float(w["T"][0]), np.array(scaler["mu"]), np.array(scaler["sd"])


def reliability_bins(probs: np.ndarray, y: np.ndarray, n_bins: int = 10):
    conf = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == y).astype(float)
    edges = np.linspace(0, 1, n_bins + 1)
    xs, ys = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            xs.append(conf[m].mean())
            ys.append(correct[m].mean())
    return np.array(xs), np.array(ys)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-samples", type=int, default=12000)
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "figures")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    W, b, T, mu, sd = load_artifacts(args.artifacts)
    roles, K = cl.ROLES, len(cl.ROLES)
    M = cl.matrix_to_array(cl.DEFAULT_ROLE_MATRIX, roles)

    X, y = cl.sample_synthetic_learners(M, n_samples=args.n_samples, seed=args.seed)
    _, _, te = cl.stratified_split(y, seed=args.seed)
    Xz = cl.apply_standardizer(X, mu, sd)
    lg = cl.logits(Xz[te], W, b)
    probs_cal = cl.softmax(lg / T)
    probs_uncal = cl.softmax(lg)
    y_true, y_pred = y[te], probs_cal.argmax(axis=1)

    cm = cl.confusion_matrix(y_true, y_pred, K)
    prf = cl.precision_recall_f1(cm)
    top1 = float((y_pred == y_true).mean())
    top3 = cl.topk_accuracy(probs_cal, y_true, 3)
    ece_b = cl.expected_calibration_error(probs_uncal, y_true)
    ece_a = cl.expected_calibration_error(probs_cal, y_true)

    # 1) confusion matrix (row-normalised, counts annotated)
    cmn = cm / cm.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(6.4, 5.4))
    im = ax.imshow(cmn, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(K)); ax.set_yticks(range(K))
    ax.set_xticklabels(SHORT, rotation=30, ha="right"); ax.set_yticklabels(SHORT)
    ax.set_xlabel("Predicted role"); ax.set_ylabel("True role")
    ax.set_title(f"Confusion matrix (row-normalised)\n"
                 f"Top-1 {top1:.1%} · Top-3 {top3:.1%} · macro-F1 {prf['macro_f1']:.3f}")
    for i in range(K):
        for j in range(K):
            ax.text(j, i, f"{cm[i, j]}\n{cmn[i, j]:.0%}", ha="center", va="center",
                    color="white" if cmn[i, j] > 0.5 else "black", fontsize=8)
    fig.colorbar(im, fraction=0.046, pad=0.04); fig.tight_layout()
    fig.savefig(args.out / "confusion_matrix.png", dpi=150); plt.close(fig)

    # 2) per-class precision / recall / F1
    x = np.arange(K); w = 0.26
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.bar(x - w, prf["precision"], w, label="Precision")
    ax.bar(x, prf["recall"], w, label="Recall")
    ax.bar(x + w, prf["f1"], w, label="F1")
    ax.set_xticks(x); ax.set_xticklabels(SHORT, rotation=20, ha="right")
    ax.set_ylim(0, 1.05); ax.set_ylabel("Score")
    ax.set_title("Per-class precision / recall / F1")
    ax.legend(); ax.grid(axis="y", alpha=0.3); fig.tight_layout()
    fig.savefig(args.out / "per_class_metrics.png", dpi=150); plt.close(fig)

    # 3) reliability diagram (calibration)
    xb, yb = reliability_bins(probs_uncal, y_true)
    xa, ya = reliability_bins(probs_cal, y_true)
    fig, ax = plt.subplots(figsize=(5.6, 5.4))
    ax.plot([0, 1], [0, 1], "--", color="gray", label="Perfect calibration")
    ax.plot(xb, yb, "o-", label=f"Before (ECE {ece_b:.3f})")
    ax.plot(xa, ya, "s-", label=f"After T={T:.3f} (ECE {ece_a:.3f})")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    ax.set_xlabel("Mean predicted confidence"); ax.set_ylabel("Empirical accuracy")
    ax.set_title("Reliability diagram (calibration)")
    ax.legend(loc="upper left"); ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(args.out / "reliability_diagram.png", dpi=150); plt.close(fig)

    print(f"[figures] wrote 3 PNGs -> {args.out}")
    print(f"[figures] top1={top1:.4f} top3={top3:.4f} macroF1={prf['macro_f1']:.4f} "
          f"ece {ece_b:.4f}->{ece_a:.4f}")


if __name__ == "__main__":
    main()
