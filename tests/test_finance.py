"""Validate the finance engine against the Chapter 04 worked example."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from engines.finance import compute_financials, FinanceError


def test_discount_factor_matches_worked_example():
    # Ch4: "the discounted cost for Year 1 is $40,000 x 0.935 = $37,200",
    # with the factor rounded to two decimals -> 1/1.08 = 0.93, 40000 x 0.93.
    r = compute_financials([40000], [0], 0.08, rounding="course", start_year=1)
    assert r["rows"][0]["discount_factor"] == 0.93
    assert r["rows"][0]["discounted_cost"] == 37200.00


def test_npv_and_roi_relationship():
    # Ch4 Figure 4-5 totals: benefits 516,000, costs 243,200
    # -> NPV 272,800 and ROI = 272,800/243,200 = 112%.
    r = compute_financials([243200], [516000], 0.0)
    assert r["npv"] == 272800.00
    assert round(r["roi"] * 100) == 112


def test_percentage_rate_is_accepted():
    a = compute_financials([1000], [2000], 8)
    b = compute_financials([1000], [2000], 0.08)
    assert a["npv"] == b["npv"]


def test_payback_is_interpolated_within_the_year():
    # costs all up front, benefits arriving evenly -> payback partway through
    r = compute_financials([100, 0, 0], [0, 60, 60], 0.0)
    assert r["payback_year"] == pytest.approx(1.67, abs=0.01)


def test_never_paying_back_is_reported_not_faked():
    r = compute_financials([100, 100], [10, 10], 0.0)
    assert r["payback_year"] is None
    assert r["npv"] < 0
    assert any("never pays back" in f for f in r["flags"])


def test_rejects_bad_rounding_mode():
    with pytest.raises(FinanceError):
        compute_financials([1], [1], 0.08, rounding="approximate")
