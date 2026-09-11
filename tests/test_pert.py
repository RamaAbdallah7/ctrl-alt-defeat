"""Validate the PERT engine against the standard three-point formula."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.pert import compute_pert, PERTError


def test_weighted_average_and_sd():
    # (2 + 4*4 + 12)/6 = 5.0 ; sd = (12-2)/6 = 1.6667
    r = compute_pert([{"id": "A", "optimistic": 2, "most_likely": 4, "pessimistic": 12}])
    a = r["activities"][0]
    assert a["expected"] == 5.0
    assert a["standard_deviation"] == pytest.approx(1.6667, abs=0.0001)


def test_variances_add_across_a_path():
    acts = [
        {"id": "A", "optimistic": 1, "most_likely": 2, "pessimistic": 3},
        {"id": "B", "optimistic": 2, "most_likely": 4, "pessimistic": 6},
    ]
    r = compute_pert(acts)
    assert r["expected_total"] == pytest.approx(2.0 + 4.0)
    # sd = sqrt((2/6)^2 + (4/6)^2)
    assert r["standard_deviation"] == pytest.approx(0.7454, abs=0.0001)


def test_probability_at_the_mean_is_half():
    r = compute_pert([{"id": "A", "optimistic": 2, "most_likely": 4, "pessimistic": 12}], target=5.0)
    assert r["probability_within_target"] == pytest.approx(0.5, abs=1e-6)


def test_generous_target_is_near_certain():
    r = compute_pert([{"id": "A", "optimistic": 2, "most_likely": 4, "pessimistic": 12}], target=20.0)
    assert r["probability_within_target"] > 0.99


def test_rejects_out_of_order_estimates():
    with pytest.raises(PERTError):
        compute_pert([{"id": "A", "optimistic": 9, "most_likely": 4, "pessimistic": 12}])


def test_rejects_empty_input():
    with pytest.raises(PERTError):
        compute_pert([])
