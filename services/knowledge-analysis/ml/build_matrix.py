"""Build the role -> competency matrix artifacts.

Authoritative source is the O*NET/ESCO-informed expert matrix in ``career_lib`` — it is
deterministic so the model is reproducible and the matrix is thesis-defensible. The
Hugging Face ``fazni/roles-based-on-skills`` set is an *optional cross-check* only
(``--with-hf``); it never silently changes the trained matrix.

Outputs (to app/services/career/artifacts/ by default):
  role_matrix.json    {role: [a1..a8]}        — requirement/importance per axis
  label_map.json      {role: index}           — classifier label order
  feature_axes.json   {"axes": [...], names}  — BINDING feature-vector order
  matrix_provenance.json (only with --with-hf) — HF keyword cross-check report

Run:  python ml/build_matrix.py [--with-hf] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make career_lib importable
import career_lib as cl  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "app" / "services" / "career" / "artifacts"


def write_matrix_artifacts(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "role_matrix.json").write_text(
        json.dumps(cl.DEFAULT_ROLE_MATRIX, indent=2), encoding="utf-8"
    )
    (out_dir / "label_map.json").write_text(
        json.dumps({r: i for i, r in enumerate(cl.ROLES)}, indent=2), encoding="utf-8"
    )
    (out_dir / "feature_axes.json").write_text(
        json.dumps({"axes": cl.FEATURE_AXES, "names": cl.AXIS_NAMES}, indent=2),
        encoding="utf-8",
    )
    print(f"[build_matrix] wrote role_matrix / label_map / feature_axes -> {out_dir}")


def hf_cross_check(out_dir: Path) -> None:
    """Best-effort: tally how often each axis's keywords appear in the HF skill text per
    role, as a face-validity check against the expert matrix. Never modifies the matrix.
    """
    try:
        from datasets import load_dataset  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dep
        print(f"[build_matrix] --with-hf skipped (datasets not available: {exc})")
        return

    axis_keywords = {
        "A1": ["loop", "variable", "syntax", "basic", "fundamental"],
        "A2": ["oop", "object", "class", "inheritance", "interface", "design"],
        "A3": ["data structure", "collection", "tree", "hashmap", "list", "queue"],
        "A4": ["algorithm", "recursion", "complexity", "dynamic programming", "sorting"],
        "A5": ["exception", "error", "testing", "robust", "logging", "file"],
        "A6": ["thread", "concurrency", "parallel", "async", "lock"],
        "A7": ["problem solving", "analytical", "debug", "reasoning"],
        "A8": ["independent", "ownership", "code review", "authorship"],
    }
    try:
        ds = load_dataset("fazni/roles-based-on-skills")
        split = ds[list(ds.keys())[0]]
        cols = split.column_names
        text_col = next((c for c in cols if "skill" in c.lower() or "description" in c.lower()), cols[-1])
        report = {"source": "fazni/roles-based-on-skills", "columns": cols, "axis_hits": {}}
        blob = " ".join(str(r.get(text_col, "")) for r in split).lower()
        report["axis_hits"] = {a: sum(blob.count(k) for k in kws) for a, kws in axis_keywords.items()}
        (out_dir / "matrix_provenance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[build_matrix] HF cross-check written; axis hit counts: {report['axis_hits']}")
    except Exception as exc:  # pragma: no cover
        print(f"[build_matrix] HF cross-check failed (non-fatal): {exc}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--with-hf", action="store_true", help="also run the HF face-validity cross-check")
    args = ap.parse_args()
    write_matrix_artifacts(args.out)
    if args.with_hf:
        hf_cross_check(args.out)


if __name__ == "__main__":
    main()
