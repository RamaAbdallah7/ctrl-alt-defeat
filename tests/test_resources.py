"""Resource loading: over-allocation CPM alone cannot see."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.resources import analyze_resources, ResourceError

# B and C both start at day 0 and both belong to Rama -- a real clash.
CLASH = [
    {"id": "A", "name": "A", "duration": 2, "predecessors": [], "assignee": "Khadeja"},
    {"id": "B", "name": "B", "duration": 3, "predecessors": [], "assignee": "Rama"},
    {"id": "C", "name": "C", "duration": 2, "predecessors": [], "assignee": "Rama"},
    {"id": "D", "name": "D", "duration": 2, "predecessors": ["B", "C"], "assignee": "Khadeja"},
]


def test_double_booking_is_detected():
    r = analyze_resources(CLASH)
    assert r["has_over_allocation"]
    c = r["conflicts"][0]
    assert c["person"] == "Rama"
    assert set(c["tasks"]) == {"B", "C"}
    assert c["peak_load"] == 2.0


def test_levelling_hint_names_the_task_with_float():
    """C has float (B is longer and drives D), so C is the one to move."""
    r = analyze_resources(CLASH)
    assert "C" in r["conflicts"][0]["levelling_hint"]


def test_no_clash_when_work_is_sequential():
    seq = [
        {"id": "A", "name": "A", "duration": 2, "predecessors": [], "assignee": "Rama"},
        {"id": "B", "name": "B", "duration": 2, "predecessors": ["A"], "assignee": "Rama"},
    ]
    r = analyze_resources(seq)
    assert not r["has_over_allocation"]
    assert any("No over-allocation" in f for f in r["flags"])


def test_part_time_units_do_not_clash():
    half = [dict(t, units=0.5) for t in CLASH]
    assert not analyze_resources(half)["has_over_allocation"]


def test_capacity_override_is_respected():
    r = analyze_resources(CLASH, capacity={"Rama": 2.0})
    assert not r["has_over_allocation"]


def test_tasks_without_assignees_are_rejected_clearly():
    with pytest.raises(ResourceError, match="assignee"):
        analyze_resources([{"id": "A", "name": "A", "duration": 1, "predecessors": []}])
