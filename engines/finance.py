"""
Project selection / financial analysis engine (Chapter 04, Project
Integration Management -- "Performing Financial Analyses").

Deterministic money math -- no LLM involved. Given a stream of yearly costs
and benefits plus a discount rate, computes the discount factor per year,
discounted costs and benefits, NPV, ROI and the payback period.

Convention notes that matter for matching the course's worked examples:

  * discount factor for year t is 1 / (1 + r)**t
  * the text's Figure 4-5 walk-through rounds the discount factor to two
    decimal places before applying it, which is why its numbers are
    "nice": year 1 is 40,000 x 0.93 = $37,200 rather than $37,037.04.
    `rounding="course"` reproduces that; "exact" (the default) keeps full
    precision.
  * Figure 4-5 also labels its first year "Year 1" and discounts it once
    (factor 0.93 = 1/1.08). `start_year=1` reproduces that. `start_year=0`
    (the default) treats the first entry as an undiscounted year 0, which
    is the other convention the text mentions for investment years.
  * payback occurs in the first period where cumulative discounted
    benefits >= cumulative discounted costs; the fractional position
    inside that year is interpolated linearly.
"""

from __future__ import annotations


class FinanceError(ValueError):
    pass


def compute_financials(
    costs: list,
    benefits: list,
    discount_rate: float,
    rounding: str = "exact",
    start_year: int = 0,
) -> dict:
    """
    costs / benefits: per-year amounts, index 0 == year 0.
    discount_rate: e.g. 0.08 for 8% (also accepts 8 and treats it as 8%).
    start_year: exponent applied to the first entry (0 or 1).
    """
    if not costs and not benefits:
        raise FinanceError("Provide at least one year of costs or benefits")
    if rounding not in ("exact", "course"):
        raise FinanceError("rounding must be 'exact' or 'course'")
    if start_year not in (0, 1):
        raise FinanceError("start_year must be 0 or 1")

    # tolerate a percentage given as 8 rather than 0.08
    r = float(discount_rate)
    if r > 1:
        r = r / 100.0
    if r <= -1:
        raise FinanceError("Discount rate must be greater than -100%")

    years = max(len(costs), len(benefits))
    costs = [float(c) for c in costs] + [0.0] * (years - len(costs))
    benefits = [float(b) for b in benefits] + [0.0] * (years - len(benefits))

    rows = []
    cum_c = cum_b = 0.0
    payback_year = None
    for t in range(years):
        factor = 1.0 / ((1.0 + r) ** (t + start_year))
        if rounding == "course":
            factor = round(factor, 2)
        dc = costs[t] * factor
        db = benefits[t] * factor
        prev_gap = cum_b - cum_c
        cum_c += dc
        cum_b += db
        gap = cum_b - cum_c

        if payback_year is None and gap >= 0:
            # linear interpolation inside this year
            if t == 0 or prev_gap == gap:
                payback_year = float(t + start_year)
            else:
                payback_year = (t + start_year - 1) + (-prev_gap / (gap - prev_gap))

        rows.append({
            "year": t + start_year,
            "cost": round(costs[t], 2),
            "benefit": round(benefits[t], 2),
            "discount_factor": round(factor, 6),
            "discounted_cost": round(dc, 2),
            "discounted_benefit": round(db, 2),
            "cumulative_discounted_cost": round(cum_c, 2),
            "cumulative_discounted_benefit": round(cum_b, 2),
            "cumulative_benefit_minus_cost": round(gap, 2),
        })

    total_dc = sum(row["discounted_cost"] for row in rows)
    total_db = sum(row["discounted_benefit"] for row in rows)
    npv = total_db - total_dc
    roi = (npv / total_dc) if total_dc else None

    flags = []
    if npv > 0:
        flags.append(f"Positive NPV ({npv:,.0f}) -- the return exceeds the cost of capital, so this is worth considering on financial grounds.")
    elif npv < 0:
        flags.append(f"Negative NPV ({npv:,.0f}) -- on financial grounds alone this project destroys value at a {r:.0%} discount rate.")
    else:
        flags.append("NPV is exactly zero -- the project breaks even against the cost of capital.")

    if roi is not None:
        flags.append(f"ROI = {roi:.1%}.")
    if payback_year is None:
        flags.append("The project never pays back within the years supplied -- extend the horizon or treat the payback as beyond the analysis window.")
    elif payback_year <= 2:
        flags.append(f"Payback in year {payback_year:.2f} -- an early payback (year 1-2) is considered very good.")
    else:
        flags.append(f"Payback in year {payback_year:.2f}.")

    return {
        "discount_rate": r,
        "rounding": rounding,
        "start_year": start_year,
        "years": years,
        "rows": rows,
        "total_discounted_cost": round(total_dc, 2),
        "total_discounted_benefit": round(total_db, 2),
        "npv": round(npv, 2),
        "roi": round(roi, 4) if roi is not None else None,
        "payback_year": round(payback_year, 2) if payback_year is not None else None,
        "flags": flags,
    }
