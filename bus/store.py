"""
Append-only event store with per-stream optimistic concurrency.

This is where the two-humans-at-once problem is actually solved. Both read
the decision stream at version N, both try to append at N+1, and the store
accepts exactly one. The loser gets a ConcurrencyError carrying the event
that beat it, so the caller can tell the second person what happened rather
than silently overwriting the first person's decision.

Entries are hash-chained the same way the audit trail is, so the event log
can be verified independently of any agent that wrote to it.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Dict, List, Optional

from bus.events import Event

GENESIS = "0" * 64


class ConcurrencyError(RuntimeError):
    """Raised when an append loses an optimistic-concurrency race."""

    def __init__(self, stream: str, expected: int, actual: int, winner: Optional[Event]):
        self.stream, self.expected, self.actual, self.winner = stream, expected, actual, winner
        super().__init__(
            f"stream '{stream}': expected version {expected}, found {actual}"
            + (f" (written by {winner.actor} as {winner.type})" if winner else "")
        )


class EventStore:
    def __init__(self, path: str = None):
        self.path = path
        self._events: List[Event] = []
        self._by_stream: Dict[str, List[Event]] = {}
        self._idempotency: Dict[str, Event] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ write

    def append(self, event: Event, expected_version: int = None) -> Event:
        """
        expected_version: the stream version the caller believes it is writing
        on top of. None means "append regardless" -- fine for facts, wrong for
        decisions. Pass it whenever two writers could collide.
        """
        with self._lock:
            if event.idempotency_key:
                seen = self._idempotency.get(event.idempotency_key)
                if seen is not None:
                    return seen          # at-least-once delivery, exactly-once effect

            stream = self._by_stream.setdefault(event.stream, [])
            current = len(stream)
            if expected_version is not None and expected_version != current:
                raise ConcurrencyError(
                    event.stream, expected_version, current,
                    stream[expected_version] if expected_version < current else None,
                )

            event.seq = current + 1
            event.prev_hash = self._events[-1].hash if self._events else GENESIS
            event.hash = hashlib.sha256(
                (event.prev_hash + event.canonical()).encode()
            ).hexdigest()

            self._events.append(event)
            stream.append(event)
            if event.idempotency_key:
                self._idempotency[event.idempotency_key] = event

            if self.path:
                os.makedirs(os.path.dirname(self.path), exist_ok=True)
                with open(self.path, "a") as fh:
                    fh.write(json.dumps(event.to_dict(), default=str) + "\n")
            return event

    # ------------------------------------------------------------------- read

    def version(self, stream: str) -> int:
        return len(self._by_stream.get(stream, []))

    def read(self, stream: str) -> List[Event]:
        return list(self._by_stream.get(stream, []))

    def all(self) -> List[Event]:
        return list(self._events)

    def by_correlation(self, correlation_id: str) -> List[Event]:
        return [e for e in self._events
                if e.correlation_id == correlation_id or e.id == correlation_id]

    # --------------------------------------------------------------- validate

    def verify(self) -> dict:
        """Recompute the chain. Returns {ok, broken_at}."""
        prev = GENESIS
        for e in self._events:
            expect = hashlib.sha256((prev + e.canonical()).encode()).hexdigest()
            if e.prev_hash != prev or e.hash != expect:
                return {"ok": False, "broken_at": e.seq, "event": e.id}
            prev = e.hash
        return {"ok": True, "broken_at": None, "event": None}
