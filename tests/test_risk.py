"""Risk register: severity banding, EMV, and the things that get missed."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.risk import analyze_risks, RiskError


def test_severity_is_probability_times_impact_and_bands_correctly():
    r = analyze_risks([
        {"name": "Extreme", "probability": 5, "impact": 5},
        {"name": "High", "probability": 3, "impact": 3},
        {"name": "Low", "probability": 1, "impact": 2},
    ])
    by = {x["name"]: x for x in r["risks"]}
    assert by["Extreme"]["severity"] == 25 and by["Extreme"]["band"] == "extreme"
    assert by["High"]["severity"] == 9 and by["High"]["band"] == "high"
    assert by["Low"]["severity"] == 2 and by["Low"]["band"] == "low"


def test_emv_is_probability_times_cost():
    r = analyze_risks([{"name": "R", "probability": 3, "impact": 3,
                        "probability_pct": 0.4, "cost_impact": 50000}])
    assert r["risks"][0]["emv"] == pytest.approx(20000)
    assert r["emv_total"] == pytest.approx(20000)


def test_opportunity_reduces_expected_cost():
    """An opportunity is a negative EMV -- it offsets the threats."""
    r = analyze_risks([
        {"name": "Threat", "probability": 3, "impact": 3, "probability_pct": .5, "cost_impact": 10000},
        {"name": "Upside", "probability": 3, "impact": 3, "probability_pct": .5,
         "cost_impact": 4000, "kind": "opportunity"},
    ])
    assert r["emv_total"] == pytest.approx(5000 - 2000)


def test_unowned_high_risks_are_named():
    r = analyze_risks([
        {"name": "Owned", "probability": 5, "impact": 5, "owner": "Rama"},
        {"name": "Nobody's", "probability": 5, "impact": 4},
        {"name": "Trivial", "probability": 1, "impact": 1},
    ])
    assert r["unowned_high_risks"] == ["Nobody's"]        # not the low-band one
    assert any("no owner" in f for f in r["flags"])


def test_register_is_ranked_worst_first():
    r = analyze_risks([
        {"name": "Mild", "probability": 2, "impact": 2},
        {"name": "Severe", "probability": 5, "impact": 5},
    ])
    assert [x["name"] for x in r["risks"]] == ["Severe", "Mild"]


def test_scores_outside_one_to_five_are_rejected():
    with pytest.raises(RiskError):
        analyze_risks([{"name": "R", "probability": 9, "impact": 3}])
