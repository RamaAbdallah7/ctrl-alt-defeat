"""
Weighted Decision Matrix / Weighted Scoring Model engine.

Deterministic math matching the course's Weighted Scoring Model exercise:
each option gets score = sum(weight_i * raw_score_i) across criteria, where
weights are percentages that should sum to 100. Options are ranked
descending by weighted score.

Verified against the textbook example:
  Criteria weights 30/20/30/10/10, four options -> weighted scores
  72, 58, 50, 72 (tie at rank 1 between option 1 and option 4).
"""

from __future__ import annotations

from typing import Dict, List


class ScoringError(ValueError):
    pass


def _normalise_scores(scores) -> Dict[str, float]:
    """Accept either {"Cost": 100} or [{"criterion": "Cost", "score": 100}]."""
    if scores is None:
        return {}
    if isinstance(scores, dict):
        return scores
    if isinstance(scores, list):
        out = {}
        for entry in scores:
            if not isinstance(entry, dict):
                raise ScoringError(f"Unreadable score entry: {entry!r}")
            name = entry.get("criterion", entry.get("name"))
            if name is None or "score" not in entry:
                raise ScoringError(
                    "Each score entry needs a 'criterion' and a 'score' "
                    f"(got {entry!r})"
                )
            out[str(name)] = entry["score"]
        return out
    raise ScoringError(f"scores must be an object or a list of pairs, got {type(scores).__name__}")


def compute_weighted_scores(
    criteria: List[dict],
    options: List[dict],
    weight_tolerance: float = 0.5,
) -> dict:
    """
    criteria: [{"name": "Cost", "weight": 30}, ...]  weights in percent
    options:  [{"name": "Option 1", "scores": {"Cost": 100, ...}}, ...]
              `scores` may also arrive as a list of
              [{"criterion": "Cost", "score": 100}, ...] -- some providers
              cannot express an open-ended object in a function schema, so
              both shapes are accepted and normalised here.

    Returns per-option weighted scores (ranked) plus a warning if weights
    don't sum to ~100, and a warning per option for any missing criterion
    score (defaulted to 0) -- this doubles as "missing information"
    detection for the orchestrator.
    """
    if not criteria:
        raise ScoringError("No criteria provided")
    if not options:
        raise ScoringError("No options provided")

    options = [{**o, "scores": _normalise_scores(o.get("scores"))} for o in options]

    weight_sum = sum(float(c["weight"]) for c in criteria)
    warnings: List[str] = []
    if abs(weight_sum - 100.0) > weight_tolerance:
        warnings.append(
            f"Criteria weights sum to {weight_sum:g}, not 100 -- scores below "
            f"are normalized against the weights as given."
        )

    results = []
    for opt in options:
        name = opt.get("name", "Unnamed option")
        scores: Dict[str, float] = opt.get("scores", {})
        weighted = 0.0
        breakdown = []
        for c in criteria:
            cname = c["name"]
            weight = float(c["weight"])
            raw = scores.get(cname)
            if raw is None:
                warnings.append(f"'{name}' is missing a score for criterion '{cname}' (treated as 0)")
                raw = 0.0
            raw = float(raw)
            contribution = (weight / weight_sum) * raw if weight_sum else 0.0
            weighted += contribution
            breakdown.append({"criterion": cname, "weight": weight, "raw_score": raw, "contribution": round(contribution, 4)})
        results.append({"option": name, "weighted_score": round(weighted, 4), "breakdown": breakdown})

    results.sort(key=lambda r: r["weighted_score"], reverse=True)
    for i, r in enumerate(results, start=1):
        r["rank"] = i

    return {"weight_sum": weight_sum, "ranked_options": results, "warnings": warnings}
