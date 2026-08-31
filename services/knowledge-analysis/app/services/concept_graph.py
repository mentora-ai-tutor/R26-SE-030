"""Loader and query helpers for the Java concept graph reference.

The Knowledge Analysis Agent uses this graph (``app/data/java_concept_graph.json``)
to:

* resolve mastery at *exact concept level* — each topic carries a set of leaf
  concepts with ``signal_patterns`` that map raw evidence strings (review
  findings, sandbox error text, quiz misses) to the specific concept a student
  struggles with (e.g. "off-by-one" in loops, "ArrayIndexOutOfBounds" in arrays);
* sequence remediation — ``prerequisite_chain`` walks prerequisite edges so the
  Learning Generator builds materials in dependency order;
* flag downstream risk — ``downstream_topics`` returns concepts that depend on a
  weak prerequisite (a weak "Loops" puts "Arrays", "Algorithms", "Recursion" at
  risk);
* enrich the mastery payload with ``week_area``, ``difficulty``, standard
  misconceptions and suggested content formats for the Content/Peer agents.

The graph is reference data only: it never mutates runtime state.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

GRAPH_PATH = Path(__file__).resolve().parents[1] / "data" / "java_concept_graph.json"

_EDGE_TYPE_PREREQUISITE = "prerequisite"
_EDGE_TYPE_RELATED = "related"

DEFAULT_WEEK_AREA = "Engineering Practice"
DEFAULT_DIFFICULTY = 1
DEFAULT_FOCUS = "Review the flagged concept with small traceable examples."
DEFAULT_MISCONCEPTION = "cannot reliably apply the concept independently"


@lru_cache(maxsize=1)
def _raw_graph() -> dict[str, Any]:
    """Load (and cache) the concept graph JSON file."""
    with open(GRAPH_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def get_graph() -> dict[str, Any]:
    """Return the whole concept graph document (reference for downstream agents)."""
    return _raw_graph()


def schema_version() -> str:
    return _raw_graph().get("schema_version", "kaa-concept-graph-v1.0")


@lru_cache(maxsize=1)
def _nodes() -> dict[str, dict[str, Any]]:
    return _raw_graph()["nodes"]


@lru_cache(maxsize=1)
def _edges() -> list[dict[str, str]]:
    return _raw_graph().get("edges", [])


@lru_cache(maxsize=1)
def _edges_by(from_id: str, edge_type: str) -> list[str]:
    """Ids of nodes this node points to with the given edge type.

    Edge direction is ``from = prerequisite``, ``to = dependent`` for
    ``prerequisite`` edges, so this returns a node's *dependents* for the
    prerequisite type and its related peers for the ``related`` type.
    """
    return [
        edge["to"]
        for edge in _edges()
        if edge.get("from") == from_id and edge.get("type") == edge_type
    ]


@lru_cache(maxsize=1)
def _prerequisites_of(node_id: str) -> list[str]:
    """Ids of the nodes that are direct prerequisites of ``node_id``.

    Reverse of ``_edges_by``: prerequisite edges point *into* the topic they
    enable, so the prerequisites of a node are the ``from`` values of the
    ``prerequisite`` edges whose ``to`` is the node.
    """
    return [
        edge["from"]
        for edge in _edges()
        if edge.get("to") == node_id and edge.get("type") == _EDGE_TYPE_PREREQUISITE
    ]


@lru_cache(maxsize=1)
def _label_index() -> dict[str, str]:
    """label.lower() -> node id for topic nodes."""
    index: dict[str, str] = {}
    for node_id, node in _nodes().items():
        index[node.get("label", "").strip().lower()] = node_id
    return index


def topic_node(name: str | None) -> Optional[dict[str, Any]]:
    """Resolve a topic *name* (as used across the app) to its graph node."""
    if not name:
        return None
    key = (name or "").strip().lower()
    node_id = _label_index().get(key)
    if node_id:
        return _nodes().get(node_id)
    # Whole-word containment (so "oop" does NOT match "Loops").
    for label, node_id in _label_index().items():
        if re.search(rf"\b{re.escape(key)}\b", label):
            return _nodes().get(node_id)
    # Loose fallback: a node whose label contains the whole query.
    for label, node_id in _label_index().items():
        if key in label:
            return _nodes().get(node_id)
    return None


def topic_node_by_id(node_id: str | None) -> Optional[dict[str, Any]]:
    """Return a graph node directly by its stable id (e.g. ``CS201-OOP``)."""
    if not node_id:
        return None
    return _nodes().get(node_id)


def topic_id(name: str | None) -> Optional[str]:
    node = topic_node(name)
    return node["id"] if node else None


def topic_label(node_id: str | None) -> Optional[str]:
    node = _nodes().get(node_id or "")
    return node["label"] if node else None


def week_area(name: str | None) -> str:
    node = topic_node(name)
    return (node or {}).get("week_area") or DEFAULT_WEEK_AREA


def difficulty(name: str | None) -> int:
    node = topic_node(name)
    value = (node or {}).get("difficulty")
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_DIFFICULTY


def concepts_for(name: str | None) -> list[dict[str, Any]]:
    """Leaf concepts (with ids, focus, misconception and signal patterns) for a topic."""
    node = topic_node(name)
    if not node:
        return []
    return list(node.get("concepts", []))


def concept_by_id(name: str | None, concept_id: str | None) -> Optional[dict[str, Any]]:
    for concept in concepts_for(name):
        if concept.get("id") == concept_id:
            return concept
    return None


def concept_labels(name: str | None) -> list[str]:
    return [concept.get("label", "") for concept in concepts_for(name)]


def match_concepts(name: str | None, text: str | None) -> list[dict[str, Any]]:
    """Concepts of a topic whose signal_patterns appear in the evidence text.

    Used to identify the *exact* concept a student is struggling with from raw
    error/evidence strings, e.g. "off-by-one" -> loop boundary conditions.
    """
    if not name or not text:
        return []
    haystack = text.lower()
    matched: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for concept in concepts_for(name):
        for pattern in concept.get("signal_patterns", []):
            try:
                if re.search(pattern, haystack):
                    if concept["id"] not in seen_ids:
                        seen_ids.add(concept["id"])
                        matched.append(concept)
                    break
            except re.error:
                continue
    return matched


def match_concept_ids(name: str | None, text: str | None) -> list[str]:
    return [concept["id"] for concept in match_concepts(name, text)]


def weak_concept_focus(name: str | None, concept_id: str) -> Optional[str]:
    concept = concept_by_id(name, concept_id)
    return (concept or {}).get("focus") or DEFAULT_FOCUS


def misconception_for(name: str | None, concept_id: str) -> Optional[str]:
    concept = concept_by_id(name, concept_id)
    return (concept or {}).get("misconception")


def prerequisite_chain(name: str | None) -> list[str]:
    """Ordered, deduplicated prerequisite labels for a topic (nearest first).

    Walks the prerequisite edges *upstream*: Loops -> [Conditionals,
    Types & Operators, Variables], so the Learning Generator builds materials in
    dependency order (the first hop is the most immediate gap).
    """
    node = topic_node(name)
    if not node:
        return []
    node_id = node["id"]
    ordered: list[str] = []
    seen: set[str] = set()

    def walk(current_id: str) -> None:
        for prereq_id in _prerequisites_of(current_id):
            label = topic_label(prereq_id)
            if label and label not in seen:
                seen.add(label)
                ordered.append(label)
            walk(prereq_id)

    walk(node_id)
    return ordered


def prerequisite_chain_ids(name: str | None) -> list[str]:
    node = topic_node(name)
    if not node:
        return []
    node_id = node["id"]
    ordered: list[str] = []
    seen: set[str] = set()

    def walk(current_id: str) -> None:
        for prereq_id in _prerequisites_of(current_id):
            if prereq_id not in seen:
                seen.add(prereq_id)
                ordered.append(prereq_id)
            walk(prereq_id)

    walk(node_id)
    return ordered


def related_topics(name: str | None) -> list[str]:
    node = topic_node(name)
    if not node:
        return []
    node_id = node["id"]
    labels: list[str] = []
    seen: set[str] = set()
    for edge in _edges():
        target = None
        if edge.get("from") == node_id and edge.get("type") == _EDGE_TYPE_RELATED:
            target = edge.get("to")
        elif edge.get("to") == node_id and edge.get("type") == _EDGE_TYPE_RELATED:
            target = edge.get("from")
        if target:
            label = topic_label(target)
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def downstream_topics(names: Iterable[str]) -> list[str]:
    """Topics that directly depend (via a prerequisite edge) on a weak topic.

    Used to flag risk propagation: a weak "Loops" puts "Arrays", "Iteration
    Patterns", "Recursion", "Algorithms & Complexity" (its dependents) at risk of
    partial mastery.
    """
    weak_ids = {
        node["id"]
        for name in names
        if (node := topic_node(name))
    }
    if not weak_ids:
        return []
    downstream: list[str] = []
    seen: set[str] = set()
    for weak_id in weak_ids:
        for dependent_id in _edges_by(weak_id, _EDGE_TYPE_PREREQUISITE):
            label = topic_label(dependent_id)
            if label and label not in seen:
                seen.add(label)
                downstream.append(label)
    return downstream


def objectives_for_weak_concepts(name: str | None, weak_concept_ids: Iterable[str]) -> list[str]:
    """Learning objectives derived from the focus of the weak concepts."""
    objectives: list[str] = []
    seen: set[str] = set()
    for concept_id in weak_concept_ids:
        concept = concept_by_id(name, concept_id)
        if not concept:
            continue
        objective = f"Improve {concept.get('label', concept_id)}: {concept.get('focus', DEFAULT_FOCUS)}"
        if objective not in seen:
            seen.add(objective)
            objectives.append(objective)
    return objectives


def misconceptions_for_weak_concepts(
    name: str | None, weak_concept_ids: Iterable[str]
) -> list[str]:
    misconceptions: list[str] = []
    seen: set[str] = set()
    for concept_id in weak_concept_ids:
        misconception = misconception_for(name, concept_id)
        if misconception and misconception not in seen:
            seen.add(misconception)
            misconceptions.append(misconception)
    return misconceptions


def graph_summary() -> dict[str, Any]:
    """Small, LMG-consumable snapshot of the graph (reference, not the whole file)."""
    raw = _raw_graph()
    return {
        "schema_version": raw.get("schema_version"),
        "language": raw.get("language"),
        "reference_path": "app/data/java_concept_graph.json",
        "node_count": len(_nodes()),
        "edge_count": len(_edges()),
        "topics": [
            {
                "id": node["id"],
                "label": node.get("label"),
                "week_area": node.get("week_area"),
                "difficulty": node.get("difficulty"),
                "concepts": [
                    {"id": c.get("id"), "label": c.get("label")}
                    for c in node.get("concepts", [])
                ],
            }
            for node in _nodes().values()
        ],
    }