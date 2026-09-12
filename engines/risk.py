"""
Risk register engine -- qualitative and quantitative risk analysis.

Two things project managers conflate and shouldn't:

  * Qualitative: probability x impact on an ordinal scale, which ranks risks
    against each other but is not money.
  * Quantitative: expected monetary value, EMV = probability x monetary
    impact, which is money and is what a contingency reserve is sized from.

Both are here, plus the response strategy each risk implies. A threat with a
high EMV and no owner is the single most common finding, so the engine says
so rather than leaving it to be noticed.

Scales are 1-5 for probability and impact (the usual 5x5 matrix); severity
is their product, 1-25.
"""

from __future__ import annotations


class RiskError(ValueError):
    pass


# 5x5 matrix bands
def _band(severity: float) -> str:
    if severity >= 15:
        return "extreme"
    if severity >= 9:
        return "high"
    if severity >= 4:
        return "moderate"
    return "low"


# Standard responses: threats vs opportunities
THREAT_RESPONSES = {
    "extreme": "avoid or transfer -- at this severity, accepting it is a decision someone must sign",
    "high": "mitigate -- reduce probability or impact, and name an owner with a date",
    "moderate": "mitigate or accept actively, with a trigger that says when to act",
    "low": "accept passively -- log it and review at the next gate",
}
OPPORTUNITY_RESPONSES = {
    "extreme": "exploit -- make sure it happens",
    "high": "enhance -- increase the probability or the upside",
    "moderate": "share or enhance",
    "low": "accept -- take it if it arrives",
}


def analyze_risks(risks: list, contingency_confidence: float = 1.0) -> dict:
    """
    risks: [{"id": "R1", "name": "...", "probability": 4, "impact": 5,
             "cost_impact": 25000, "kind": "threat"|"opportunity",
             "owner": "name", "status": "open"}, ...]

    probability/impact are 1-5. `cost_impact` is optional; when present the
    risk contributes to expected monetary value. Probability may also be given
    as a percentage (0-1 or 0-100) for the EMV calculation -- see below.

    contingency_confidence: multiplier on the summed EMV when recommending a
    contingency reserve (1.0 = the plain expected value).
    """
    if not risks:
        raise RiskError("No risks provided")

    rows, emv_total, threats, opps = [], 0.0, 0, 0
    unowned = []

    for r in risks:
        rid = str(r.get("id", r.get("name", f"R{len(rows) + 1}")))
        try:
            p = float(r["probability"])
            i = float(r["impact"])
        except (KeyError, TypeError, ValueError) as e:
            raise RiskError(f"Risk '{rid}' needs numeric probability and impact ({e})")
        if not (1 <= p <= 5 and 1 <= i <= 5):
            raise RiskError(
                f"Risk '{rid}': probability and impact are 1-5 scores (got {p}, {i})"
            )

        kind = (r.get("kind") or "threat").lower()
        if kind not in ("threat", "opportunity"):
            raise RiskError(f"Risk '{rid}': kind must be 'threat' or 'opportunity'")

        severity = p * i
        band = _band(severity)

        # EMV uses a real probability, not the 1-5 score. Accept an explicit
        # percentage, else map the ordinal score onto a probability.
        if r.get("probability_pct") is not None:
            pct = float(r["probability_pct"])
            pct = pct / 100.0 if pct > 1 else pct
        else:
            pct = {1: 0.1, 2: 0.3, 3: 0.5, 4: 0.7, 5: 0.9}[int(round(p))]

        cost = r.get("cost_impact")
        emv = None
        if cost is not None:
            emv = pct * float(cost) * (1 if kind == "threat" else -1)
            emv_total += emv

        owner = r.get("owner")
        if not owner and band in ("high", "extreme"):
            unowned.append(rid)

        if kind == "threat":
            threats += 1
        else:
            opps += 1

        rows.append({
            "id": rid,
            "name": r.get("name", rid),
            "kind": kind,
            "probability": p,
            "impact": i,
            "severity": severity,
            "band": band,
            "probability_pct": round(pct, 4),
            "cost_impact": float(cost) if cost is not None else None,
            "emv": round(emv, 2) if emv is not None else None,
            "owner": owner,
            "status": r.get("status", "open"),
            "recommended_response": (THREAT_RESPONSES if kind == "threat" else OPPORTUNITY_RESPONSES)[band],
        })

    rows.sort(key=lambda r: (-r["severity"], -(r["emv"] or 0)))

    contingency = emv_total * float(contingency_confidence) if emv_total > 0 else 0.0
    top = rows[0]

    flags = [
        f"Top risk: {top['name']} at severity {top['severity']:g}/25 ({top['band']}) -- "
        f"{top['recommended_response']}."
    ]
    extremes = [r for r in rows if r["band"] == "extreme"]
    if extremes:
        flags.append(
            f"{len(extremes)} risk(s) in the extreme band: "
            f"{', '.join(r['name'] for r in extremes)}. These are not 'manage carefully' risks -- "
            f"they need a decision."
        )
    if emv_total:
        flags.append(
            f"Expected monetary value across the register is {emv_total:,.0f}. "
            f"A contingency reserve below that is, on the numbers, underfunded."
        )
    if unowned:
        flags.append(
            f"{len(unowned)} high-or-worse risk(s) have no owner ({', '.join(unowned)}). "
            f"An unowned risk is not being managed, whatever the register says."
        )

    return {
        "risks": rows,
        "count": len(rows),
        "threats": threats,
        "opportunities": opps,
        "by_band": {b: len([r for r in rows if r["band"] == b])
                    for b in ("extreme", "high", "moderate", "low")},
        "emv_total": round(emv_total, 2),
        "recommended_contingency": round(contingency, 2),
        "unowned_high_risks": unowned,
        "flags": flags,
    }
