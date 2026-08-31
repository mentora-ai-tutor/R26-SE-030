"""Unit tests for the Java concept-graph reference used by the mastery bridge.

The concept graph is pure reference data (no DB / no LLM): these tests pin the
graph topology, the notional-week mapping, and the exact-concept matching that
drives ``weak_concept_ids`` in mastery gaps.
"""
from app.services import concept_graph as cg


def test_graph_loads_topic_and_engineering_nodes():
    g = cg.get_graph()
    assert len(g["nodes"]) == 33
    assert g["nodes"]["CS101-LOOP"]["label"] == "Loops"
    assert g["nodes"]["SE-TEST"]["label"] == "Testing & Verification"
    assert g["nodes"]["CS-GEN"]["label"] == "General Code Quality"


# ---------------------------------------------------------------- topic labelling
def test_topic_node_matches_whole_word_before_substring():
    assert cg.topic_node("OOP")["id"] == "CS201-OOP"
    assert cg.topic_node("Collections")["id"] == "CS201-DS"
    assert cg.topic_node("Threads")["id"] == "CS301-CONC"
    assert cg.topic_node("Iteration Patterns")["id"] == "CS101-ITER"
    assert cg.topic_node("Binary Search Trees")["id"] == "CS201-BST"
    assert cg.topic_node("Method")["id"] == "CS101-FUNC"
    assert cg.topic_node("Lists?") is None


def test_topic_node_by_id_resolves_ids():
    assert cg.topic_node_by_id("CS101-REC")["label"] == "Recursion"
    assert cg.topic_node_by_id("CS101-COND")["label"] == "Conditionals"
    assert cg.topic_node_by_id("nope") is None


# ------------------------------------------------------------- topology / chains
def test_prerequisite_chain_walks_the_reverse_edge():
    # Edges are from=prerequisite -> to=dependent, so chains follow them backwards.
    assert cg.prerequisite_chain("Loops") == ["Conditionals", "Types & Operators", "Variables"]


def test_downstream_topics_follows_forward_dependents():
    assert cg.downstream_topics(["Loops"]) == [
        "Arrays",
        "Iteration Patterns",
        "Methods & Functions",
        "Recursion",
        "Algorithms & Complexity",
    ]


def test_related_topics_includes_graph_related_edges():
    related = cg.related_topics("Loops")
    assert "Conditionals" in related


# --------------------------------------------------------------- week mapping
def test_week_area_is_resolved_from_graph():
    assert cg.week_area("Recursion") == "W09 - Recursion"
    assert cg.week_area("Loops") == "W02 - Control Flow"
    assert cg.week_area("Binary Search Trees").startswith("W")
    assert cg.week_area("Completely Unknown Topic") == cg.DEFAULT_WEEK_AREA


# ------------------------------------------------------- concept-level matching
def test_match_concepts_resolves_raw_evidence_to_leaf_concepts():
    matched = cg.match_concepts("Recursion", "base case is never reached; stack overflow")
    ids = {m["id"] for m in matched}
    assert "CS101-REC-BASE" in ids
    assert "CS101-REC-STACK" in ids


def test_weak_concept_metadata_and_objectives():
    assert cg.concept_by_id("Loops", "CS101-LOOP-BOUNDARY") is not None
    assert cg.misconception_for("Loops", "CS101-LOOP-BOUNDARY")
    objectives = cg.objectives_for_weak_concepts("Loops", ["CS101-LOOP-BOUNDARY"])
    assert objectives
    assert all("boundary" in o.lower() for o in objectives)