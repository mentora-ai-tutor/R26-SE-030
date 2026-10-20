"""Reproducibility + quality gate for the trained career model.

Reloads the exported artifacts, regenerates the seeded test split, recomputes metrics
with numpy only, and checks they match the committed metrics.json within tolerance
(plan §10). Optional ``--figures DIR`` dumps the academic plots if matplotlib is present.

Run:  python ml/evaluate.py [--seed 42] [--figures ml/figures]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import career_lib as cl  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parents[1] / "app" / "services" / "career" / "artifacts"


def load_artifacts(path: Path):
    w = np.load(path / "model_weights.npz")
    scaler = json.loads((path / "scaler.json").read_text())
    return w["W"], w["b"], float(w["T"][0]), np.array(scaler["mu"]), np.array(scaler["sd"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-samples", type=int, default=12000)
    ap.add_argument("--artifacts", type=Path, default=ARTIFACTS)
    ap.add_argument("--figures", type=Path, default=None)
    ap.add_argument("--tol", type=float, default=0.03)
    args = ap.parse_args()

    W, b, T, mu, sd = load_artifacts(args.artifacts)
    roles, K = cl.ROLES, len(cl.ROLES)
    M = cl.matrix_to_array(cl.DEFAULT_ROLE_MATRIX, roles)

    X, y = cl.sample_synthetic_learners(M, n_samples=args.n_samples, seed=args.seed)
    _, _, te = cl.stratified_split(y, seed=args.seed)
    Xz = cl.apply_standardizer(X, mu, sd)
    probs = cl.softmax(cl.logits(Xz[te], W, b) / T)
    y_pred = probs.argmax(axis=1)

    cm = cl.confusion_matrix(y[te], y_pred, K)
    prf = cl.precision_recall_f1(cm)
    recomputed = {
        "test_top1_acc": round(float((y_pred == y[te]).mean()), 4),
        "test_top3_acc": round(cl.topk_accuracy(probs, y[te], 3), 4),
        "macro_f1": round(prf["macro_f1"], 4),
        "ece_after": round(cl.expected_calibration_error(probs, y[te]), 4),
    }
    print("[evaluate] recomputed:", recomputed)

    saved_path = args.artifacts / "metrics.json"
    if saved_path.exists():
        saved = json.loads(saved_path.read_text())
        drift = {k: abs(recomputed[k] - saved.get(k, 0)) for k in recomputed}
        worst = max(drift.values())
        status = "OK" if worst <= args.tol else "DRIFT"
        print(f"[evaluate] vs committed metrics.json: {drift} -> {status} (tol={args.tol})")
        if status == "DRIFT":
            sys.exit(1)

    if args.figures:
        _dump_figures(args.figures, cm, prf, roles)


def _dump_figures(out: Path, cm, prf, roles) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # pragma: no cover
        print(f"[evaluate] --figures skipped (matplotlib missing: {exc})")
        return
    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(roles))); ax.set_yticks(range(len(roles)))
    ax.set_xticklabels(range(len(roles))); ax.set_yticklabels(range(len(roles)))
    ax.set_xlabel("predicted"); ax.set_ylabel("true"); ax.set_title("Confusion matrix")
    fig.colorbar(im); fig.tight_layout(); fig.savefig(out / "confusion_matrix.png", dpi=120)
    print(f"[evaluate] figures -> {out}")


if __name__ == "__main__":
    main()
