"""Turn a canonical mastery profile + latest quiz result into the model's input vector.

Thin wrapper over ``competency_map``: it builds the {axis: value} map, then orders it by
the model's ``feature_axes`` (the binding order from ``feature_axes.json``) so the vector
columns always line up with the trained weights.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.career import competency_map as cm


def featurize(
    profile: Dict[str, Any],
    quiz_result: Optional[Dict[str, Any]],
    feature_axes: List[str],
) -> List[float]:
    values = cm.build_axis_values(profile, quiz_result)
    return [float(values.get(axis, 0.5)) for axis in feature_axes]


def evidence(profile: Dict[str, Any], quiz_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return cm.evidence_strength(profile, quiz_result)
