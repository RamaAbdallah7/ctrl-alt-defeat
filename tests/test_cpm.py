"""Validate CPM engine on a small, hand-checkable network."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.cpm import compute_critical_path, CPMError


def test_simple_diamond():
    # A(3) -> B(4) -> D(2)
    # A(3) -> C(1) -> D(2)
    # Critical path A-B-D = 9 (float on C = (3+4)-(3+1) = 3)
    tasks = [
        {"id": "A", "name": "Start", "duration": 3, "predecessors": []},
        {"id": "B", "name": "Design", "duration": 4, "predecessors": ["A"]},
        {"id": "C", "name": "Docs", "duration": 1, "predecessors": ["A"]},
        {"id": "D", "name": "Finish", "duration": 2, "predecessors": ["B", "C"]},
    ]
    result = compute_critical_path(tasks)
    assert result["project_duration"] == 9
    assert result["critical_path"] == ["A", "B", "D"]

    by_id = {t["id"]: t for t in result["tasks"]}
    assert by_id["C"]["total_float"] == 3
    assert by_id["A"]["is_critical"] and by_id["B"]["is_critical"] and by_id["D"]["is_critical"]
    assert not by_id["C"]["is_critical"]
    print("test_simple_diamond PASSED:", result["project_duration"], result["critical_path"])


def test_cycle_detected():
    tasks = [
        {"id": "A", "name": "A", "duration": 1, "predecessors": ["B"]},
        {"id": "B", "name": "B", "duration": 1, "predecessors": ["A"]},
    ]
    try:
        compute_critical_path(tasks)
        assert False, "expected CPMError on cycle"
    except CPMError:
        print("test_cycle_detected PASSED")


def test_unknown_predecessor():
    tasks = [{"id": "A", "name": "A", "duration": 1, "predecessors": ["Z"]}]
    try:
        compute_critical_path(tasks)
        assert False, "expected CPMError on unknown predecessor"
    except CPMError:
        print("test_unknown_predecessor PASSED")


if __name__ == "__main__":
    test_simple_diamond()
    test_cycle_detected()
    test_unknown_predecessor()
    print("ALL CPM TESTS PASSED")


def test_reference_network_matches_course_table_6_1():
    """Figure 6-2 / Table 6-1: duration 16, path B-E-H-J, task F holds 7 days float."""
    tasks = [
        {"id": "A", "name": "A", "duration": 1, "predecessors": []},
        {"id": "B", "name": "B", "duration": 2, "predecessors": []},
        {"id": "C", "name": "C", "duration": 3, "predecessors": []},
        {"id": "D", "name": "D", "duration": 4, "predecessors": ["A"]},
        {"id": "E", "name": "E", "duration": 5, "predecessors": ["B"]},
        {"id": "F", "name": "F", "duration": 4, "predecessors": ["B"]},
        {"id": "G", "name": "G", "duration": 6, "predecessors": ["C"]},
        {"id": "H", "name": "H", "duration": 6, "predecessors": ["D", "E"]},
        {"id": "I", "name": "I", "duration": 2, "predecessors": ["G"]},
        {"id": "J", "name": "J", "duration": 3, "predecessors": ["F", "H", "I"]},
    ]
    r = compute_critical_path(tasks)
    assert r["project_duration"] == 16
    assert r["critical_path"] == ["B", "E", "H", "J"]
    assert r["has_parallel_critical_paths"] is False

    # free slack / total slack, exactly as Table 6-1 prints them
    expected = {"A": (0, 2), "B": (0, 0), "C": (0, 2), "D": (2, 2), "E": (0, 0),
                "F": (7, 7), "G": (0, 2), "H": (0, 0), "I": (2, 2), "J": (0, 0)}
    for t in r["tasks"]:
        assert (t["free_float"], t["total_float"]) == expected[t["id"]], t["id"]


def test_parallel_critical_paths_are_listed_separately():
    """Two equal-length paths must come back as two chains, not one fake path."""
    tasks = [
        {"id": "S", "name": "S", "duration": 1, "predecessors": []},
        {"id": "P", "name": "P", "duration": 4, "predecessors": ["S"]},
        {"id": "Q", "name": "Q", "duration": 4, "predecessors": ["S"]},
        {"id": "E", "name": "E", "duration": 1, "predecessors": ["P", "Q"]},
    ]
    r = compute_critical_path(tasks)
    assert r["has_parallel_critical_paths"] is True
    assert r["critical_paths"] == [["S", "P", "E"], ["S", "Q", "E"]]
