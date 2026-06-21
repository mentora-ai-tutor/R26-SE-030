"""Serving-side inference for the hand-made career-fit model (NumPy only).

Loads the artifacts produced by ``ml/train.py`` / the Colab notebook and runs the exact
same math as training: standardise -> calibrated softmax. No sklearn/torch in the
container. The artifacts dir is `app/services/career/artifacts/`.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

AXIS_NAMES = {
    "A1": "Programming Fundamentals", "A2": "OOP & Design", "A3": "Data Structures",
    "A4": "Algorithms & Complexity", "A5": "Robustness / Error Handling",
    "A6": "Concurrency", "A7": "Problem-solving Fluency", "A8": "Independent Authorship",
}


def _softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class CareerModel:
    def __init__(self, artifacts_dir: Path = ARTIFACTS_DIR):
        w = np.load(artifacts_dir / "model_weights.npz")
        self.W, self.b, self.T = w["W"], w["b"], float(w["T"][0])
        scaler = json.loads((artifacts_dir / "scaler.json").read_text())
        self.mu = np.array(scaler["mu"], dtype=float)
        self.sd = np.array(scaler["sd"], dtype=float)
        self.feature_axes: List[str] = json.loads((artifacts_dir / "feature_axes.json").read_text())["axes"]
        label_map = json.loads((artifacts_dir / "label_map.json").read_text())
        self.roles: List[str] = [r for r, _ in sorted(label_map.items(), key=lambda kv: kv[1])]
        self.role_matrix = json.loads((artifacts_dir / "role_matrix.json").read_text())
        try:
            self.model_version = json.loads((artifacts_dir / "metrics.json").read_text()).get("model_version", "")
        except Exception:
            self.model_version = ""

    # ---- inference ----
    def predict_proba(self, x_raw: List[float]) -> np.ndarray:
        x = (np.array(x_raw, dtype=float) - self.mu) / self.sd
        return _softmax((x.reshape(1, -1) @ self.W.T + self.b) / self.T)[0]

    def rank(self, x_raw: List[float]) -> List[Tuple[str, float]]:
        p = self.predict_proba(x_raw)
        order = np.argsort(-p)
        return [(self.roles[i], float(p[i])) for i in order]

    def gaps_for(self, x_raw: List[float], role: str, margin: float = 0.05):
        """Axes where the learner is below the role's requirement, biggest gap first."""
        req = self.role_matrix.get(role, [])
        out = []
        for axis, your, need in zip(self.feature_axes, x_raw, req):
            if your < need - margin:
                out.append({
                    "axis": axis, "axis_name": AXIS_NAMES.get(axis, axis),
                    "your_score": round(float(your), 3), "required_score": round(float(need), 3),
                    "gap": round(float(need - your), 3),
                })
        return sorted(out, key=lambda g: g["gap"], reverse=True)

    def matched_for(self, x_raw: List[float], role: str, margin: float = 0.05) -> List[str]:
        req = self.role_matrix.get(role, [])
        return [AXIS_NAMES.get(a, a) for a, your, need in zip(self.feature_axes, x_raw, req) if your >= need - margin]


def readiness_level(overall_0_100: float, difficulty_reached: str = "medium") -> str:
    ceiling = {"easy": 0, "medium": 1, "hard": 2}.get(difficulty_reached, 1)
    if (overall_0_100 or 0) >= 75 and ceiling >= 2:
        return "Strong Junior"
    if (overall_0_100 or 0) >= 55 and ceiling >= 1:
        return "Job-ready (Junior)"
    return "Foundational"


@lru_cache(maxsize=1)
def load_model() -> CareerModel:
    """Load once at first use; cached for the process lifetime."""
    return CareerModel()
