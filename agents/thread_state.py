"""
Per-thread conversational state.

A one-shot bot answers the message in front of it. An agentic one remembers
what it just computed, so "what if we cut three days off" is a delta against
the last structured input rather than a fresh request that has to restate
ten tasks.

State is keyed by thread (thread_ts in Slack, conversation+reply-chain in
Teams) and holds the last structured input per engine, the last brief, and
who was involved. SQLite rather than a dict because the bot restarting
mid-demo must not lose the thread it is in the middle of.

`apply_delta` is deliberately narrow: it understands a small set of explicit
adjustments and refuses the rest. A delta interpreter that guesses is worse
than one that asks, because the user cannot see what it assumed.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit_log", "threads.db"
)


class ThreadStore:
    def __init__(self, path: str = None):
        self.path = path or DB_PATH
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_state (
                thread_key   TEXT PRIMARY KEY,
                channel      TEXT,
                tool_calls   TEXT,
                brief        TEXT,
                event_id     TEXT,
                requester    TEXT,
                locked       INTEGER DEFAULT 0,
                updated_at   REAL
            )""")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS thread_files (
                thread_key TEXT, name TEXT, digest TEXT, parsed TEXT, seen_at REAL
            )""")
        self._conn.commit()

    # ------------------------------------------------------------------ state

    def save(self, thread_key: str, *, channel=None, tool_calls=None, brief=None,
             event_id=None, requester=None, locked=None) -> None:
        prior = self.load(thread_key) or {}
        row = {
            "channel": channel if channel is not None else prior.get("channel"),
            "tool_calls": tool_calls if tool_calls is not None else prior.get("tool_calls"),
            "brief": brief if brief is not None else prior.get("brief"),
            "event_id": event_id if event_id is not None else prior.get("event_id"),
            "requester": requester if requester is not None else prior.get("requester"),
            "locked": int(locked if locked is not None else prior.get("locked", 0)),
        }
        self._conn.execute(
            """INSERT INTO thread_state
               (thread_key, channel, tool_calls, brief, event_id, requester, locked, updated_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(thread_key) DO UPDATE SET
                 channel=excluded.channel, tool_calls=excluded.tool_calls,
                 brief=excluded.brief, event_id=excluded.event_id,
                 requester=excluded.requester, locked=excluded.locked,
                 updated_at=excluded.updated_at""",
            (thread_key, row["channel"], json.dumps(row["tool_calls"], default=str),
             row["brief"], row["event_id"], row["requester"], row["locked"], time.time()),
        )
        self._conn.commit()

    def load(self, thread_key: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT channel, tool_calls, brief, event_id, requester, locked, updated_at "
            "FROM thread_state WHERE thread_key=?", (thread_key,))
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "channel": row[0],
            "tool_calls": json.loads(row[1]) if row[1] and row[1] != "null" else None,
            "brief": row[2], "event_id": row[3], "requester": row[4],
            "locked": bool(row[5]), "updated_at": row[6],
        }

    def lock(self, thread_key: str) -> None:
        self.save(thread_key, locked=True)

    def is_locked(self, thread_key: str) -> bool:
        return bool((self.load(thread_key) or {}).get("locked"))

    # ------------------------------------------------------------------ files

    def remember_file(self, thread_key: str, name: str, digest: str, parsed: dict) -> Optional[dict]:
        """Store a parsed upload; return the previous version of the same file if any."""
        cur = self._conn.execute(
            "SELECT digest, parsed FROM thread_files WHERE thread_key=? AND name=? "
            "ORDER BY seen_at DESC LIMIT 1", (thread_key, name))
        row = cur.fetchone()
        previous = None
        if row and row[0] != digest:
            previous = json.loads(row[1])
        self._conn.execute(
            "INSERT INTO thread_files (thread_key, name, digest, parsed, seen_at) VALUES (?,?,?,?,?)",
            (thread_key, name, digest, json.dumps(parsed, default=str), time.time()))
        self._conn.commit()
        return previous

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------- delta

# Verb forms matter: "\bslip\b" does not match "slips", and people write both.
_SHORTEN = re.compile(
    r"\b(?:cuts?|shortens?|reduces?|shaves?|takes?\s+off|bring\s+in|pull\s+in)\b"
    r".*?\b(\d+(?:\.\d+)?)\s*(day|week|month)s?", re.IGNORECASE)
_EXTEND = re.compile(
    r"\b(?:adds?|extends?|slips?|delays?|pushes?|push|overruns?|late\s+by)\b"
    r".*?\b(\d+(?:\.\d+)?)\s*(day|week|month)s?", re.IGNORECASE)
_SET_FIELD = re.compile(
    r"\b(pv|ev|ac|bac|budget|planned value|earned value|actual cost)\b\s*(?:is|to|=|of)?\s*"
    r"\$?\s*([\d,]+(?:\.\d+)?)\s*(k|m)?\b", re.IGNORECASE)
_TASK_DURATION = re.compile(
    r"\b(?:task\s+)?([A-Z]\d?)\b[^.]*?\b(?:takes|is|to)\s+(\d+(?:\.\d+)?)\s*(day|week)s?",
    re.IGNORECASE)

_FIELD_ALIAS = {"budget": "bac", "planned value": "pv", "earned value": "ev", "actual cost": "ac"}
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30}


def apply_delta(prior_calls: List[dict], text: str) -> Tuple[List[dict], List[str]]:
    """
    Adjust the previous structured input by what the follow-up says.

    Returns (new_calls, changes). An empty `changes` means nothing was
    understood -- the caller should fall back to a full re-route rather than
    silently re-running the identical analysis.
    """
    calls = json.loads(json.dumps(prior_calls or [], default=str))   # deep copy
    changes: List[str] = []

    for call in calls:
        inp = call.get("input") or {}

        # explicit per-task duration: "what if task E takes 8 days"
        if "tasks" in inp:
            for m in _TASK_DURATION.finditer(text):
                tid, value, unit = m.group(1).upper(), float(m.group(2)), m.group(3).lower()
                days = value * _UNIT_DAYS[unit]
                for t in inp["tasks"]:
                    if str(t.get("id", "")).upper() == tid:
                        if t.get("duration") != days:
                            changes.append(f"{tid} duration {t.get('duration'):g} -> {days:g} days")
                            t["duration"] = days

        # whole-project compression target: "cut the timeline by 3 days"
        if "tasks" in inp or "target_duration" in inp:
            m = _SHORTEN.search(text)
            if m:
                days = float(m.group(1)) * _UNIT_DAYS[m.group(2).lower()]
                base = inp.get("target_duration")
                if base is None:
                    from engines.cpm import compute_critical_path
                    try:
                        base = compute_critical_path(inp["tasks"])["project_duration"]
                    except Exception:
                        base = None
                if base is not None:
                    inp["target_duration"] = base - days
                    changes.append(f"target duration {base:g} -> {inp['target_duration']:g} days")

        # a slip: "what if the vendor slips 2 weeks"
        if "tasks" in inp:
            m = _EXTEND.search(text)
            if m and not _SHORTEN.search(text):
                days = float(m.group(1)) * _UNIT_DAYS[m.group(2).lower()]
                crit = [t for t in inp["tasks"] if t.get("predecessors")]
                target = crit[-1] if crit else (inp["tasks"][-1] if inp["tasks"] else None)
                if target is not None:
                    old = target.get("duration", 0)
                    target["duration"] = old + days
                    changes.append(
                        f"{target.get('id', 'last task')} duration {old:g} -> "
                        f"{target['duration']:g} days (slip of {days:g})")

        # EVM figures: "what if AC is 50,000"
        for m in _SET_FIELD.finditer(text):
            field = _FIELD_ALIAS.get(m.group(1).lower(), m.group(1).lower())
            if field not in inp:
                continue
            value = float(m.group(2).replace(",", ""))
            if (m.group(3) or "").lower() == "k":
                value *= 1_000
            elif (m.group(3) or "").lower() == "m":
                value *= 1_000_000
            if inp.get(field) != value:
                changes.append(f"{field.upper()} {inp.get(field):,.0f} -> {value:,.0f}")
                inp[field] = value

    return calls, changes


def describe_changes(changes: List[str]) -> str:
    if not changes:
        return ""
    return "Re-ran with: " + "; ".join(changes) + "."
