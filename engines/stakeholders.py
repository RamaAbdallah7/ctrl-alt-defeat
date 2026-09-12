"""
Stakeholder analysis engine.

Two classic pieces of project-management arithmetic that teams almost never
actually do:

  * the power/interest grid, which sorts stakeholders into the four
    engagement strategies -- manage closely, keep satisfied, keep informed,
    monitor. Getting this wrong is how a project surprises the one person who
    could have stopped it early.
  * communication channels, n(n-1)/2. The count grows quadratically, which is
    why adding people to a late project makes the communication worse rather
    than the delivery faster. Six people carry 15 channels; twelve carry 66.

It also flags the engagement gap: a stakeholder whose current engagement is
below what their power and interest demand is the project's blind spot.
"""

from __future__ import annotations


class StakeholderError(ValueError):
    pass


# Where a stakeholder sits, given power and interest on 1-5 scales.
STRATEGIES = {
    ("high", "high"): ("manage closely",
                       "Engage directly and often. Decisions need their buy-in before, not after."),
    ("high", "low"): ("keep satisfied",
                      "Enough contact that they are never surprised; not so much that they disengage."),
    ("low", "high"): ("keep informed",
                      "They care and will talk. Regular updates stop rumour filling the gap."),
    ("low", "low"): ("monitor",
                     "Minimal effort, but re-check -- power and interest both change."),
}

ENGAGEMENT_LEVELS = ["unaware", "resistant", "neutral", "supportive", "leading"]


def communication_channels(n: int) -> int:
    """n(n-1)/2 -- the number of two-way channels among n people."""
    n = int(n)
    if n < 0:
        raise StakeholderError("Headcount cannot be negative")
    return n * (n - 1) // 2


def analyze_stakeholders(stakeholders: list, team_size: int = None) -> dict:
    """
    stakeholders: [{"name": "...", "power": 5, "interest": 2,
                    "current_engagement": "neutral",
                    "desired_engagement": "supportive"}, ...]
    power/interest are 1-5. Engagement values come from ENGAGEMENT_LEVELS.
    team_size: headcount for the communication-channel calculation; defaults
               to the number of stakeholders given.
    """
    if not stakeholders:
        raise StakeholderError("No stakeholders provided")

    rows, gaps = [], []
    for s in stakeholders:
        name = s.get("name") or f"stakeholder{len(rows) + 1}"
        try:
            power = float(s["power"])
            interest = float(s["interest"])
        except (KeyError, TypeError, ValueError) as e:
            raise StakeholderError(f"'{name}' needs numeric power and interest ({e})")
        if not (1 <= power <= 5 and 1 <= interest <= 5):
            raise StakeholderError(f"'{name}': power and interest are 1-5 (got {power}, {interest})")

        key = ("high" if power >= 3.5 else "low", "high" if interest >= 3.5 else "low")
        strategy, guidance = STRATEGIES[key]

        cur = (s.get("current_engagement") or "neutral").lower()
        des = (s.get("desired_engagement") or "supportive").lower()
        for label, v in (("current", cur), ("desired", des)):
            if v not in ENGAGEMENT_LEVELS:
                raise StakeholderError(
                    f"'{name}': {label}_engagement must be one of {', '.join(ENGAGEMENT_LEVELS)}"
                )
        gap = ENGAGEMENT_LEVELS.index(des) - ENGAGEMENT_LEVELS.index(cur)

        row = {
            "name": name,
            "role": s.get("role"),
            "power": power,
            "interest": interest,
            "quadrant": f"{key[0]} power / {key[1]} interest",
            "strategy": strategy,
            "guidance": guidance,
            "current_engagement": cur,
            "desired_engagement": des,
            "engagement_gap": gap,
            "priority": round(power * interest, 2),
        }
        rows.append(row)
        if gap > 0:
            gaps.append(row)

    rows.sort(key=lambda r: (-r["priority"], r["name"]))
    gaps.sort(key=lambda r: (-r["power"] * r["engagement_gap"]))

    n = int(team_size) if team_size is not None else len(rows)
    channels = communication_channels(n)

    by_strategy = {}
    for r in rows:
        by_strategy.setdefault(r["strategy"], []).append(r["name"])

    flags = []
    close = by_strategy.get("manage closely", [])
    if close:
        flags.append(
            f"Manage closely: {', '.join(close)}. These are the people whose agreement the "
            f"project actually runs on."
        )
    if gaps:
        worst = gaps[0]
        flags.append(
            f"Widest engagement gap: {worst['name']} is {worst['current_engagement']} and needs to be "
            f"{worst['desired_engagement']}, at power {worst['power']:g}/5. That gap, at that power, "
            f"is the project's blind spot."
        )
    resistant = [r for r in rows if r["current_engagement"] == "resistant" and r["power"] >= 3.5]
    if resistant:
        names = ", ".join(r["name"] for r in resistant)
        verb = "is" if len(resistant) == 1 else "are"
        flags.append(
            f"{names} {verb} resistant AND powerful -- this is the combination that stops "
            f"projects late, after the money is spent."
        )
    flags.append(
        f"{n} people means {channels} two-way communication channels (n(n-1)/2). "
        + (f"Adding two more takes it to {communication_channels(n + 2)} -- "
           f"communication load grows faster than headcount."
           if n >= 4 else "")
    )

    return {
        "stakeholders": rows,
        "count": len(rows),
        "by_strategy": by_strategy,
        "engagement_gaps": gaps,
        "team_size": n,
        "communication_channels": channels,
        "flags": flags,
    }
