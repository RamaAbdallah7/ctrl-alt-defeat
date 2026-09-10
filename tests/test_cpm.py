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
