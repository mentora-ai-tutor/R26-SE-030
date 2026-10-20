"""Train the hand-made career-fit classifier and export serving artifacts.

Numpy-only (no sklearn/torch) so it reproduces the Colab run for CI. The Colab notebook
performs the same steps plus the figures. Stack Overflow survey CSV is optional and only
sets class priors; without it the synthetic class balance is uniform.

Run:  python ml/train.py [--so-csv data/survey_results_public.csv] [--epochs 1500]
Exports to app/services/career/artifacts/:
  model_weights.npz (W, b, T)   scaler.json (mu, sd, axes)   metrics.json
  + role_matrix.json / label_map.json / feature_axes.json (via build_matrix)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import career_lib as cl  # noqa: E402
import build_matrix  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parents[1] / "app" / "services" / "career" / "artifacts"


def priors_from_so(csv_path: Path) -> np.ndarray | None:
    """Map Stack Overflow DevType frequencies onto our roles -> prior weights."""
    try:
        import pandas as pd  # local import; optional
    except Exception:
        print("[train] pandas unavailable; skipping SO priors")
        return None
    if not csv_path or not csv_path.exists():
        print(f"[train] SO csv not found at {csv_path}; using uniform priors")
        return None
    df = pd.read_csv(csv_path, usecols=lambda c: c in {"DevType"}, low_memory=False)
    counts = np.ones(len(cl.ROLES))  # Laplace smoothing so no class is zero
    ridx = cl.role_index(cl.ROLES)
    for cell in df["DevType"].dropna():
        low = str(cell).lower()
        for key, role in cl.DEVTYPE_TO_ROLE.items():
            if key in low:
                counts[ridx[role]] += 1
                break
    print(f"[train] SO priors (counts): {dict(zip(cl.ROLES, counts.astype(int)))}")
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-csv", type=Path, default=None)
    ap.add_argument("--n-samples", type=int, default=12000)
    ap.add_argument("--epochs", type=int, default=1500)
    ap.add_argument("--lr", type=float, default=0.5)
    ap.add_argument("--lam", type=float, default=1e-3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=ARTIFACTS)
    args = ap.parse_args()

    np.random.seed(args.seed)
    roles = cl.ROLES
    K = len(roles)
    M = cl.matrix_to_array(cl.DEFAULT_ROLE_MATRIX, roles)

    priors = priors_from_so(args.so_csv) if args.so_csv else None
    X, y = cl.sample_synthetic_learners(M, n_samples=args.n_samples, priors=priors, seed=args.seed)

    tr, va, te = cl.stratified_split(y, seed=args.seed)
    mu, sd = cl.fit_standardizer(X[tr])
    Xz = cl.apply_standardizer(X, mu, sd)

    # class weights = inverse frequency (handle imbalance from priors)
    freq = np.bincount(y[tr], minlength=K).astype(float)
    class_weight = (freq.sum() / (K * (freq + 1e-9)))

    result = cl.train_softmax(
        Xz[tr], y[tr], K, lr=args.lr, lam=args.lam, epochs=args.epochs,
        Xval=Xz[va], yval=y[va], class_weight=class_weight, seed=args.seed,
    )
    W, b, hist = result["W"], result["b"], result["history"]

    # calibrate on val, evaluate on test
    T = cl.fit_temperature(cl.logits(Xz[va], W, b), y[va])
    probs_uncal = cl.softmax(cl.logits(Xz[te], W, b))
    probs_cal = cl.softmax(cl.logits(Xz[te], W, b) / T)
    y_pred = probs_cal.argmax(axis=1)

    cm = cl.confusion_matrix(y[te], y_pred, K)
    prf = cl.precision_recall_f1(cm)
    metrics = {
        "model_version": f"numpy-softmax-seed{args.seed}",
        "n_samples": int(args.n_samples),
        "epochs": int(args.epochs),
        "temperature": round(T, 4),
        "test_top1_acc": round(float((y_pred == y[te]).mean()), 4),
        "test_top3_acc": round(cl.topk_accuracy(probs_cal, y[te], 3), 4),
        "macro_f1": round(prf["macro_f1"], 4),
        "ece_before": round(cl.expected_calibration_error(probs_uncal, y[te]), 4),
        "ece_after": round(cl.expected_calibration_error(probs_cal, y[te]), 4),
        "final_train_loss": round(hist["train_loss"][-1], 4),
        "final_val_acc": round(hist["val_acc"][-1], 4),
        "per_class_f1": {roles[i]: round(float(prf["f1"][i]), 4) for i in range(K)},
        "confusion_matrix": cm.tolist(),
    }

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    build_matrix.write_matrix_artifacts(out)
    np.savez(out / "model_weights.npz", W=W, b=b, T=np.array([T]))
    (out / "scaler.json").write_text(
        json.dumps({"mu": mu.tolist(), "sd": sd.tolist(), "axes": cl.FEATURE_AXES}, indent=2),
        encoding="utf-8",
    )
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("\n=== Career model trained ===")
    for k in ("test_top1_acc", "test_top3_acc", "macro_f1", "ece_before", "ece_after", "temperature"):
        print(f"  {k:14s}: {metrics[k]}")
    print(f"  artifacts -> {out}")


if __name__ == "__main__":
    main()
