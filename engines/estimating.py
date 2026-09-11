"""
Cost-estimate classification engine (Chapter 07, Table 7-1).

The chapter's point is that an estimate without its accuracy band is
misleading: a rough order of magnitude figure carries a -50%% to +100%%
range, and quoting it as if it were definitive (-5%% to +10%%) is how IT
projects end up with a 27%% average cost overrun.

Given an estimate, its type, and optionally the budget it is being held
against, this engine returns the honest range that estimate implies and
says whether the budget actually sits inside it.
"""

from __future__ import annotations


class EstimateError(ValueError):
    pass


# Table 7-1: type -> (low %, high %, when it is done, why)
ESTIMATE_TYPES = {
    "rom": (-0.50, 1.00,
            "Very early, often 3-5 years before completion or before the project is officially started",
            "Provides a cost figure for selection decisions"),
    "budgetary": (-0.10, 0.25,
                  "Early, 1-2 years out",
                  "Allocates money into the organization's budget"),
    "definitive": (-0.05, 0.10,
                   "Later in the project, less than a year out",
                   "The most accurate of the three; puts firm dollars in the plan"),
}

ALIASES = {
    "rough order of magnitude": "rom", "rough_order_of_magnitude": "rom",
    "order of magnitude": "rom", "ballpark": "rom",
    "budget": "budgetary", "budgetary estimate": "budgetary",
    "definitive estimate": "definitive", "detailed": "definitive",
}


def classify_estimate(estimate: float, estimate_type: str, budget: float = None) -> dict:
    key = str(estimate_type).strip().lower().replace("-", " ")
    key = ALIASES.get(key, key)
    if key not in ESTIMATE_TYPES:
        raise EstimateError(
            f"Unknown estimate type '{estimate_type}'. Use one of: "
            f"{', '.join(sorted(ESTIMATE_TYPES))} (Table 7-1)."
        )

    estimate = float(estimate)
    if estimate <= 0:
        raise EstimateError("Estimate must be greater than zero")

    low_pct, high_pct, when, why = ESTIMATE_TYPES[key]
    low = estimate * (1 + low_pct)
    high = estimate * (1 + high_pct)

    flags = [
        f"A {key.upper()} estimate carries a {low_pct:+.0%} to {high_pct:+.0%} accuracy range, "
        f"so {estimate:,.0f} really means {low:,.0f} to {high:,.0f}.",
        f"When this type is used: {when}. Why: {why.lower()}.",
    ]

    within = None
    if budget is not None:
        budget = float(budget)
        within = low <= budget <= high
        if budget < low:
            flags.append(
                f"The {budget:,.0f} budget sits BELOW the bottom of that range "
                f"({low:,.0f}) -- it is not defensible against this estimate."
            )
        elif budget > high:
            flags.append(
                f"The {budget:,.0f} budget sits above the top of the range "
                f"({high:,.0f}) -- generous, or the estimate is stale."
            )
        else:
            position = (budget - low) / (high - low) if high > low else 0.0
            flags.append(
                f"The {budget:,.0f} budget falls inside the range, "
                f"{position:.0%} of the way from the floor to the ceiling."
            )
            if key == "rom":
                flags.append(
                    "Note that almost any budget falls inside a ROM range -- that is the point "
                    "of a ROM, not reassurance. Get to a budgetary estimate before committing."
                )

    return {
        "estimate": estimate,
        "type": key,
        "low_percent": low_pct,
        "high_percent": high_pct,
        "range_low": round(low, 2),
        "range_high": round(high, 2),
        "when_done": when,
        "why_done": why,
        "budget": budget,
        "budget_within_range": within,
        "flags": flags,
    }
