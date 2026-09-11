"""Append-only audit trail. Every request the orchestrator handles gets one
JSON line here: who asked, what was extracted, what each engine returned,
and the final brief. This is the "Traceable audit trail" feature from the
Tarteeb architecture -- cheap to build, and it's a real differentiator in a
demo because you can show the log after the fact."""

from __future__ import annotations

import json
import os
import time
import uuid

AUDIT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit_log")
AUDIT_FILE = os.path.join(AUDIT_DIR, "audit_trail.jsonl")


def log_event(**fields) -> str:
    os.makedirs(AUDIT_DIR, exist_ok=True)
    event_id = str(uuid.uuid4())[:8]
    record = {
        "event_id": event_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **fields,
    }
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return event_id


def read_recent(n: int = 20) -> list:
    if not os.path.exists(AUDIT_FILE):
        return []
    with open(AUDIT_FILE) as f:
        lines = f.readlines()[-n:]
    return [json.loads(line) for line in lines]
