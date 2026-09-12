"""
Credential lifecycle tracking.

A secret is not a fact, it is a state machine, and most leaks happen in the
transitions nobody owns: a key that expired but is still referenced by open
work, or one that was rotated while three tasks still name the old one.

    issued -> active -> expiring -> expired
                 |          |
                 +----------+--> rotated -> revoked
                 |
                 +--> compromised -> revoked

Legal transitions are enforced, because the value of a state machine is
entirely in what it refuses. Marking an expired key "active" again without
rotating it is exactly the move this is here to stop.

`cross_reference` is the part that earns its place: it takes the open tasks
and finds work that still points at a credential which is expiring, expired,
rotated or revoked. That is the gap between "we rotated it" and "everything
that used it was updated".
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional


class CredentialError(ValueError):
    pass


ISSUED, ACTIVE, EXPIRING, EXPIRED = "issued", "active", "expiring", "expired"
ROTATED, REVOKED, COMPROMISED = "rotated", "revoked", "compromised"

TRANSITIONS: Dict[str, set] = {
    ISSUED: {ACTIVE, REVOKED, COMPROMISED},
    ACTIVE: {EXPIRING, EXPIRED, ROTATED, REVOKED, COMPROMISED},
    EXPIRING: {EXPIRED, ROTATED, REVOKED, COMPROMISED},
    EXPIRED: {ROTATED, REVOKED, COMPROMISED},
    COMPROMISED: {ROTATED, REVOKED},
    ROTATED: {REVOKED},
    REVOKED: set(),                     # terminal, deliberately
}

# States where a credential must not still be in use by open work.
UNUSABLE = {EXPIRED, ROTATED, REVOKED, COMPROMISED}

EXPIRING_WINDOW_DAYS = 30


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def can_transition(current: str, target: str) -> bool:
    if current not in TRANSITIONS:
        raise CredentialError(f"Unknown state '{current}'")
    if target not in TRANSITIONS:
        raise CredentialError(f"Unknown state '{target}'")
    return target in TRANSITIONS[current]


def transition(credential: dict, target: str, reason: str = None, today=None) -> dict:
    current = credential.get("state", ISSUED)
    if not can_transition(current, target):
        allowed = ", ".join(sorted(TRANSITIONS[current])) or "nothing -- it is terminal"
        raise CredentialError(
            f"'{credential.get('name', '?')}' cannot go {current} -> {target}. "
            f"From {current} the only legal moves are: {allowed}."
        )
    out = dict(credential)
    out["state"] = target
    out.setdefault("history", list(credential.get("history", [])))
    out["history"].append({
        "from": current, "to": target, "reason": reason,
        "on": str(_as_date(today) or date.today()),
    })
    return out


def assess(credentials: List[dict], today=None, window_days: int = EXPIRING_WINDOW_DAYS) -> dict:
    """
    credentials: [{"id": "...", "name": "...", "state": "active",
                   "expires": "2026-10-01", "owner": "...",
                   "vault_ref": "kv://...", "used_by": ["T-12"]}, ...]

    Derives expiring/expired from the dates rather than trusting the stored
    state, because the stored state is what goes stale.
    """
    if not credentials:
        raise CredentialError("No credentials provided")

    today = _as_date(today) or date.today()
    rows, alerts = [], []

    for c in credentials:
        cid = str(c.get("id", c.get("name", f"cred{len(rows) + 1}")))
        state = c.get("state", ISSUED)
        if state not in TRANSITIONS:
            raise CredentialError(f"'{cid}' has unknown state '{state}'")

        expires = _as_date(c.get("expires"))
        days_left = (expires - today).days if expires else None

        # The derived state, from the calendar rather than from the record.
        derived = state
        if state in (ISSUED, ACTIVE, EXPIRING) and days_left is not None:
            if days_left < 0:
                derived = EXPIRED
            elif days_left <= window_days:
                derived = EXPIRING

        drifted = derived != state
        row = {
            "id": cid,
            "name": c.get("name", cid),
            "owner": c.get("owner"),
            "vault_ref": c.get("vault_ref"),
            "recorded_state": state,
            "state": derived,
            "expires": str(expires) if expires else None,
            "days_left": days_left,
            "used_by": list(c.get("used_by") or []),
            "state_drifted": drifted,
            "history": c.get("history", []),
        }
        rows.append(row)

        if drifted:
            alerts.append({
                "severity": "high" if derived == EXPIRED else "medium",
                "credential": cid,
                "message": f"{row['name']} is recorded as {state} but is actually {derived} "
                           f"({'expired ' + str(abs(days_left)) + ' days ago' if days_left is not None and days_left < 0 else str(days_left) + ' days left'}).",
            })
        if derived == EXPIRED:
            alerts.append({
                "severity": "high", "credential": cid,
                "message": f"{row['name']} expired on {row['expires']}. Rotate it, then revoke the old value.",
            })
        elif derived == EXPIRING:
            alerts.append({
                "severity": "medium", "credential": cid,
                "message": f"{row['name']} expires in {days_left} day(s)"
                           + (f" and is owned by {row['owner']}." if row["owner"] else " and has no owner."),
            })
        if not c.get("owner") and derived not in (REVOKED,):
            alerts.append({
                "severity": "medium", "credential": cid,
                "message": f"{row['name']} has no owner. An unowned credential is one nobody will rotate.",
            })
        if not c.get("vault_ref") and derived not in (REVOKED, ROTATED):
            alerts.append({
                "severity": "low", "credential": cid,
                "message": f"{row['name']} is not linked to a vault entry, so its real value cannot be verified.",
            })

    by_state = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1

    rows.sort(key=lambda r: (r["days_left"] if r["days_left"] is not None else 10 ** 6))

    return {
        "today": str(today),
        "credentials": rows,
        "count": len(rows),
        "by_state": by_state,
        "alerts": sorted(alerts, key=lambda a: {"high": 0, "medium": 1, "low": 2}[a["severity"]]),
        "expiring_within": window_days,
    }


def cross_reference(credentials: List[dict], open_tasks: List[dict], today=None) -> dict:
    """
    Find open work still pointing at a credential that cannot be used.

    open_tasks: [{"id": "T-12", "name": "...", "uses": ["cred-1"], "status": "open"}, ...]
    """
    state = assess(credentials, today=today)
    by_id = {c["id"]: c for c in state["credentials"]}

    problems = []
    for task in open_tasks:
        if (task.get("status") or "open").lower() not in ("open", "in_progress", "in progress"):
            continue
        for ref in task.get("uses") or []:
            cred = by_id.get(str(ref))
            if cred is None:
                problems.append({
                    "severity": "medium", "task": task.get("id"), "credential": str(ref),
                    "message": f"Task {task.get('id')} references credential '{ref}', which is not "
                               f"in the register at all. Untracked credentials are the ones that leak.",
                })
                continue
            if cred["state"] in UNUSABLE:
                problems.append({
                    "severity": "high", "task": task.get("id"), "credential": cred["id"],
                    "message": f"Task {task.get('id')} ({task.get('name')}) still uses "
                               f"{cred['name']}, which is {cred['state']}. The work will fail, or "
                               f"someone will quietly put the old value back.",
                })
            elif cred["state"] == EXPIRING:
                problems.append({
                    "severity": "medium", "task": task.get("id"), "credential": cred["id"],
                    "message": f"Task {task.get('id')} uses {cred['name']}, which expires in "
                               f"{cred['days_left']} day(s). Rotate before the task lands, not after.",
                })

    flags = list(state["alerts"])
    if problems:
        high = len([p for p in problems if p["severity"] == "high"])
        flags.insert(0, {
            "severity": "high" if high else "medium",
            "credential": None,
            "message": f"{len(problems)} open task(s) reference a credential that is expiring or "
                       f"already unusable. This is the gap between rotating a key and finishing "
                       f"the rotation.",
        })

    return {**state, "task_problems": problems, "alerts": flags}
