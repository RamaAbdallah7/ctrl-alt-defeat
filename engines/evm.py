"""
Earned Value Management (EVM) engine -- standard project cost-control math
(Chapter 07, Project Cost Management).

Implements the full Table 7-4 formula set:

  CV   = EV - AC                 SV   = EV - PV
  CPI  = EV / AC                 SPI  = EV / PV
  EAC  = BAC / CPI               ETC  = EAC - AC        VAC = BAC - EAC
  TCPI (to BAC) = (BAC - EV) / (BAC - AC)
  TCPI (to EAC) = (BAC - EV) / (EAC - AC)
  EAC (CPI and SPI both influencing) = AC + (BAC - EV) / (CPI * SPI)

plus the schedule forecast the text derives alongside them:

  estimated duration = planned duration / SPI

and the two definitions used to obtain PV and EV in the first place:

  PV = planned %% complete x BAC        EV = actual %% complete x BAC
"""

from __future__ import annotations


class EVMError(ValueError):
    pass


def evm_from_percentages(planned_pct: float, actual_pct: float, ac: float, bac: float) -> dict:
    """
    Convenience entry point for the way the course states most problems:
    "50%% of the work should be done, only 40%% is, and we've spent X".

    Percentages may be given as 50 or as 0.50.
    """
    def _frac(p, label):
        p = float(p)
        if p < 0:
            raise EVMError(f"{label} cannot be negative")
        return p / 100.0 if p > 1 else p

    bac = float(bac)
    if bac <= 0:
        raise EVMError("Budget at completion (BAC) must be > 0")

    pv = _frac(planned_pct, "planned %% complete") * bac
    ev = _frac(actual_pct, "actual %% complete") * bac
    return compute_evm(pv, ev, ac, bac)


def compute_evm(pv: float, ev: float, ac: float, bac: float,
                planned_duration: float = None) -> dict:
    """
    planned_duration: optional planned project length (months, weeks, days --
    whatever the caller uses). When given, the schedule forecast
    planned_duration / SPI is included.
    """
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

    # To-complete performance index: the cost performance the remaining work
    # must achieve to still land on BAC (or on the forecast EAC).
    tcpi_bac = ((bac - ev) / (bac - ac)) if (bac - ac) != 0 else None
    tcpi_eac = ((bac - ev) / (eac - ac)) if (eac is not None and (eac - ac) != 0) else None

    # EAC when both cost and schedule performance drag on the remaining work.
    eac_cpi_spi = (ac + (bac - ev) / (cpi * spi)) if (cpi and spi) else None

    estimated_duration = None
    if planned_duration is not None and spi:
        estimated_duration = float(planned_duration) / spi

    flags = []
    if cpi is not None and cpi < 1:
        flags.append(f"Over budget: CPI = {cpi:.2f} (every $1 spent is returning ${cpi:.2f} of planned value)")
    elif cpi is not None and cpi > 1.05:
        flags.append(f"Under budget: CPI = {cpi:.2f}")
    if spi is not None and spi < 1:
        flags.append(f"Behind schedule: SPI = {spi:.2f}")
    elif spi is not None and spi > 1.05:
        flags.append(f"Ahead of schedule: SPI = {spi:.2f}")
    if tcpi_bac is not None and tcpi_bac > 1.1:
        flags.append(
            f"To still finish on budget the remaining work must run at a "
            f"TCPI of {tcpi_bac:.2f} -- materially better than the {cpi:.2f} "
            f"achieved so far, which is rarely realistic without a change in plan."
            if cpi else
            f"Remaining work must run at a TCPI of {tcpi_bac:.2f} to finish on budget."
        )
    if estimated_duration is not None and planned_duration:
        delta = estimated_duration - float(planned_duration)
        if abs(delta) > 1e-9:
            direction = "longer than" if delta > 0 else "shorter than"
            flags.append(
                f"Schedule forecast: {estimated_duration:.1f} vs {float(planned_duration):.1f} planned "
                f"({abs(delta):.1f} {direction} plan at the current SPI)."
            )

    return {
        "pv": pv, "ev": ev, "ac": ac, "bac": bac,
        "cv": round(cv, 2), "sv": round(sv, 2),
        "cpi": round(cpi, 4) if cpi is not None else None,
        "spi": round(spi, 4) if spi is not None else None,
        "eac": round(eac, 2) if eac is not None else None,
        "etc": round(etc, 2) if etc is not None else None,
        "vac": round(vac, 2) if vac is not None else None,
        "tcpi_bac": round(tcpi_bac, 4) if tcpi_bac is not None else None,
        "tcpi_eac": round(tcpi_eac, 4) if tcpi_eac is not None else None,
        "eac_cpi_spi": round(eac_cpi_spi, 2) if eac_cpi_spi is not None else None,
        "planned_duration": float(planned_duration) if planned_duration is not None else None,
        "estimated_duration": round(estimated_duration, 2) if estimated_duration is not None else None,
        "percent_complete": percent_complete,
        "flags": flags,
    }
