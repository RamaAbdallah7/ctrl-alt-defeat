"""
Earned Value Management (EVM) engine -- standard project cost-control math
(Chapter 07, Project Cost Management).

Given planned value (PV / BCWS), earned value (EV / BCWP), actual cost
(AC / ACWP) and the budget at completion (BAC), computes the standard
variance and performance indices, an estimate at completion, and simple
status flags an orchestrator can use to raise risks.
"""

from __future__ import annotations


class EVMError(ValueError):
    pass


def compute_evm(pv: float, ev: float, ac: float, bac: float) -> dict:
    pv, ev, ac, bac = float(pv), float(ev), float(ac), float(bac)
    if bac <= 0:
        raise EVMError("Budget at completion (BAC) must be > 0")
    if ac < 0 or pv < 0 or ev < 0:
        raise EVMError("PV, EV and AC must be non-negative")

    cv = ev - ac
    sv = ev - pv
    cpi = (ev / ac) if ac else None
    spi = (ev / pv) if pv else None

    eac = (bac / cpi) if cpi else None
    etc = (eac - ac) if eac is not None else None
    vac = (bac - eac) if eac is not None else None
    percent_complete = round((ev / bac) * 100, 2) if bac else None

    flags = []
    if cpi is not None and cpi < 1:
        flags.append(f"Over budget: CPI = {cpi:.2f} (every $1 spent is returning ${cpi:.2f} of planned value)")
    elif cpi is not None and cpi > 1.05:
        flags.append(f"Under budget: CPI = {cpi:.2f}")
    if spi is not None and spi < 1:
        flags.append(f"Behind schedule: SPI = {spi:.2f}")
    elif spi is not None and spi > 1.05:
        flags.append(f"Ahead of schedule: SPI = {spi:.2f}")

    return {
        "pv": pv, "ev": ev, "ac": ac, "bac": bac,
        "cv": round(cv, 2), "sv": round(sv, 2),
        "cpi": round(cpi, 4) if cpi is not None else None,
        "spi": round(spi, 4) if spi is not None else None,
        "eac": round(eac, 2) if eac is not None else None,
        "etc": round(etc, 2) if etc is not None else None,
        "vac": round(vac, 2) if vac is not None else None,
        "percent_complete": percent_complete,
        "flags": flags,
    }
