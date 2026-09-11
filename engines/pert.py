"""
PERT / three-point estimating engine (Chapter 06, Project Schedule
Management -- "Program Evaluation and Review Technique").

PERT handles the case where individual activity durations are genuinely
uncertain, by taking an optimistic, most likely and pessimistic estimate
for each activity instead of a single number:

  PERT weighted average = (optimistic + 4 x most likely + pessimistic) / 6
  standard deviation    = (pessimistic - optimistic) / 6
  variance              = standard deviation ^ 2

The same weighted-average formula is what Chapter 07 refers to when it
describes three-point *cost* estimates, so this engine takes a `unit`
label and is used for both.

Across a path, variances add, so the path standard deviation is the square
root of the summed variances -- which is what makes a probability statement
about the finish date possible.
"""

from __future__ import annotations

import math


class PERTError(ValueError):
    pass


def _phi(z: float) -> float:
    """Standard normal CDF, via the error function -- no scipy dependency."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def compute_pert(activities: list, target: float = None, unit: str = "days") -> dict:
    """
    activities: [{"id": "A", "name": "...", "optimistic": 2,
                  "most_likely": 4, "pessimistic": 12}, ...]
    target: optional target total (e.g. a deadline in days, or a budget cap
            for cost estimates) to compute a completion probability against.

    The project roll-up treats the supplied activities as one sequential
    path -- pass the critical-path activities when you want a schedule
    probability, or every work item when you are three-point estimating a
    cost total.
    """
    if not activities:
        raise PERTError("No activities provided")

    rows = []
    total_expected = 0.0
    total_variance = 0.0
    for a in activities:
        aid = str(a.get("id", a.get("name", f"item{len(rows) + 1}")))
        try:
            o = float(a["optimistic"])
            m = float(a["most_likely"])
            p = float(a["pessimistic"])
        except (KeyError, TypeError, ValueError) as e:
            raise PERTError(f"Activity '{aid}' needs numeric optimistic, most_likely and pessimistic values ({e})")
        if not (o <= m <= p):
            raise PERTError(
                f"Activity '{aid}': estimates must satisfy optimistic <= most likely <= pessimistic "
                f"(got {o}, {m}, {p})"
            )

        expected = (o + 4 * m + p) / 6.0
        sd = (p - o) / 6.0
        var = sd ** 2
        total_expected += expected
        total_variance += var

        rows.append({
            "id": aid,
            "name": a.get("name", aid),
            "optimistic": o,
            "most_likely": m,
            "pessimistic": p,
            "expected": round(expected, 4),
            "standard_deviation": round(sd, 4),
            "variance": round(var, 6),
            "spread": round(p - o, 4),
        })

    project_sd = math.sqrt(total_variance)

    flags = []
    # the single widest-uncertainty activity is the one worth re-estimating
    widest = max(rows, key=lambda r: r["standard_deviation"])
    if widest["standard_deviation"] > 0:
        flags.append(
            f"Most uncertain activity: {widest['name']} "
            f"(range {widest['optimistic']:g}-{widest['pessimistic']:g} {unit}, "
            f"sd {widest['standard_deviation']:.2f}) -- tightening this estimate "
            f"cuts total uncertainty faster than any other."
        )

    result = {
        "unit": unit,
        "activities": rows,
        "expected_total": round(total_expected, 4),
        "total_variance": round(total_variance, 6),
        "standard_deviation": round(project_sd, 4),
        # +/- 1 sd is the conventional ~68% band, +/- 2 sd ~95%
        "range_68": [round(total_expected - project_sd, 2), round(total_expected + project_sd, 2)],
        "range_95": [round(total_expected - 2 * project_sd, 2), round(total_expected + 2 * project_sd, 2)],
        "target": float(target) if target is not None else None,
        "probability_within_target": None,
        "flags": flags,
    }

    if target is not None:
        t = float(target)
        if project_sd == 0:
            prob = 1.0 if t >= total_expected else 0.0
        else:
            prob = _phi((t - total_expected) / project_sd)
        result["probability_within_target"] = round(prob, 4)
        flags.append(
            f"Probability of finishing within {t:g} {unit}: {prob:.0%} "
            f"(expected {total_expected:.1f}, sd {project_sd:.1f})."
        )
        if prob < 0.5:
            flags.append(
                f"That is below an even chance -- the {t:g}-{unit} target is optimistic "
                f"against these estimates."
            )

    return result
