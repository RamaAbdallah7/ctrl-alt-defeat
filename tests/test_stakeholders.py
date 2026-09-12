"""Stakeholder grid and communication channels."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.stakeholders import analyze_stakeholders, communication_channels, StakeholderError


def test_communication_channels_formula():
    # n(n-1)/2 -- the classic result: headcount rises linearly, channels quadratically
    assert [communication_channels(n) for n in (1, 2, 3, 6, 12)] == [0, 1, 3, 15, 66]


def test_quadrants_map_to_the_four_strategies():
    r = analyze_stakeholders([
        {"name": "HH", "power": 5, "interest": 5},
        {"name": "HL", "power": 5, "interest": 1},
        {"name": "LH", "power": 1, "interest": 5},
        {"name": "LL", "power": 1, "interest": 1},
    ])
    by = {s["name"]: s["strategy"] for s in r["stakeholders"]}
    assert by == {"HH": "manage closely", "HL": "keep satisfied",
                  "LH": "keep informed", "LL": "monitor"}


def test_engagement_gap_is_measured_in_levels():
    r = analyze_stakeholders([{"name": "X", "power": 5, "interest": 5,
                               "current_engagement": "resistant",
                               "desired_engagement": "leading"}])
    assert r["stakeholders"][0]["engagement_gap"] == 3


def test_resistant_and_powerful_is_called_out():
    r = analyze_stakeholders([{"name": "Finance", "power": 5, "interest": 4,
                               "current_engagement": "resistant"}])
    assert any("resistant AND powerful" in f for f in r["flags"])
    assert any("Finance is resistant" in f for f in r["flags"]), "singular verb expected"


def test_team_size_drives_the_channel_count_not_stakeholder_count():
    r = analyze_stakeholders([{"name": "A", "power": 3, "interest": 3}], team_size=12)
    assert r["communication_channels"] == 66


def test_unknown_engagement_level_is_rejected():
    with pytest.raises(StakeholderError):
        analyze_stakeholders([{"name": "X", "power": 3, "interest": 3,
                               "current_engagement": "grumpy"}])
