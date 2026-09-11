"""Validate EVM engine against known-good hand-calculated figures."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.evm import compute_evm


def test_over_budget_behind_schedule():
    # PV=1000, EV=800, AC=1000, BAC=5000
    # CV = 800-1000 = -200 ; SV = 800-1000 = -200
    # CPI = 800/1000 = 0.8 ; SPI = 800/1000 = 0.8
    # EAC = 5000/0.8 = 6250
    r = compute_evm(pv=1000, ev=800, ac=1000, bac=5000)
    assert r["cv"] == -200
    assert r["sv"] == -200
    assert abs(r["cpi"] - 0.8) < 1e-6
    assert abs(r["spi"] - 0.8) < 1e-6
    assert abs(r["eac"] - 6250) < 0.01
    assert any("Over budget" in f for f in r["flags"])
    assert any("Behind schedule" in f for f in r["flags"])
    print("test_over_budget_behind_schedule PASSED:", r)


def test_on_track():
    r = compute_evm(pv=1000, ev=1000, ac=1000, bac=5000)
    assert r["cv"] == 0 and r["sv"] == 0
    assert r["flags"] == []
    print("test_on_track PASSED:", r)


if __name__ == "__main__":
    test_over_budget_behind_schedule()
    test_on_track()
    print("ALL EVM TESTS PASSED")
