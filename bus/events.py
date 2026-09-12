"""
Event envelope and logical clock.

Agents in Tarteeb do not call each other. They publish facts to a shared log
and react to what they read, which is what makes the ordering and conflict
problems real rather than decorative.

Two clocks matter and they are not the same thing:

  * `seq`  -- a per-stream sequence number. Monotonic *within* one stream
              (one task, one decision), and what optimistic concurrency is
              checked against. Two writers racing on the same stream both
              try to write the same seq; one loses, by construction.
  * `lamport` -- a logical clock carried across streams. Wall-clock time
              cannot order events from different agents (clocks drift, and
              two events can share a millisecond), so causality is tracked
              with a Lamport counter: on publish, tick; on receive, take
              max(local, incoming) + 1.

`causation_id` says which event directly caused this one; `correlation_id`
groups everything belonging to one conversation. Together they are what lets
the post-incident timeline reconstruct "this led to that" later, instead of
guessing from timestamps.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


# ---------------------------------------------------------------- event types

# scheduling
TASK_CLOSE_PROPOSED = "task.close.proposed"
TASK_CLOSED = "task.closed"
TASK_CLOSE_BLOCKED = "task.close.blocked"

# review votes
REVIEW_ENDORSED = "review.endorsed"
REVIEW_VETOED = "review.vetoed"

# governance
ESCALATION_RAISED = "escalation.raised"
HUMAN_DECISION = "human.decision"
DECISION_REJECTED_STALE = "decision.rejected.stale"

# reporting
BRIEF_PUBLISHED = "brief.published"


@dataclass
class Event:
    type: str
    stream: str                       # the aggregate this belongs to
    payload: Dict[str, Any] = field(default_factory=dict)
    actor: str = "system"
    seq: int = 0                      # assigned by the store
    lamport: int = 0                  # assigned by the bus
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    prev_hash: Optional[str] = None
    hash: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def canonical(self) -> str:
        """Stable serialisation for hashing -- excludes the hash fields."""
        d = self.to_dict()
        d.pop("hash", None)
        d.pop("prev_hash", None)
        return json.dumps(d, sort_keys=True, default=str)

    def caused_by(self, other: "Event") -> "Event":
        self.causation_id = other.id
        self.correlation_id = other.correlation_id or other.id
        return self


class LamportClock:
    """Logical time. Cheap, and correct about causality where wall clocks are not."""

    def __init__(self) -> None:
        self.t = 0

    def tick(self) -> int:
        self.t += 1
        return self.t

    def observe(self, incoming: int) -> int:
        self.t = max(self.t, int(incoming or 0)) + 1
        return self.t
