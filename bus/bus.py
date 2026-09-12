"""
The event bus: ordered, at-least-once delivery to subscribers.

Two things it does that a plain callback list does not:

  * Per-stream ordering. Events can reach the bus out of order -- a retry, a
    slow agent, a redelivery. An event whose stream sequence is ahead of what
    the subscriber has seen is buffered, not delivered, until the gap fills.
    Deliver seq 3 before seq 2 and a Risk veto can land after the task has
    already been closed.
  * Dedupe. Delivery is at-least-once, so the same event can arrive twice.
    Subscribers see it once.

Handlers publish by returning events rather than calling the bus directly,
which keeps the causal chain intact and makes a turn of the protocol a pure
function of what came in.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set

from bus.events import Event, LamportClock
from bus.store import EventStore


class Subscription:
    def __init__(self, name: str, handler: Callable, types: Optional[Set[str]]):
        self.name = name
        self.handler = handler
        self.types = types
        self.delivered: Set[str] = set()
        self.last_seq: Dict[str, int] = defaultdict(int)
        self.pending: Dict[str, Dict[int, Event]] = defaultdict(dict)

    def wants(self, event: Event) -> bool:
        return self.types is None or event.type in self.types


class EventBus:
    def __init__(self, store: EventStore = None):
        self.store = store or EventStore()
        self.clock = LamportClock()
        self.subs: List[Subscription] = []
        self.dead_letters: List[dict] = []
        self.trace: List[dict] = []

    def subscribe(self, name: str, handler: Callable, types=None) -> Subscription:
        sub = Subscription(name, handler, set(types) if types else None)
        self.subs.append(sub)
        return sub

    # ------------------------------------------------------------------ publish

    def publish(self, event: Event, expected_version: int = None) -> Event:
        event.lamport = self.clock.tick()
        stored = self.store.append(event, expected_version=expected_version)
        self._dispatch(stored)
        return stored

    def _dispatch(self, event: Event) -> None:
        # Every subscriber tracks every event in the stream, even the types it
        # does not want. Filtering before the cursor advances would leave a
        # permanent gap at each skipped sequence, and the subscriber would wait
        # for it forever -- a subscriber that ignores one event type would
        # silently stop receiving that stream entirely.
        for sub in self.subs:
            sub.pending[event.stream][event.seq] = event
            self._drain(sub, event.stream)

    def _drain(self, sub: Subscription, stream: str) -> None:
        """Advance over the contiguous run, invoking only for wanted types."""
        while True:
            nxt = sub.last_seq[stream] + 1
            event = sub.pending[stream].pop(nxt, None)
            if event is None:
                return
            sub.last_seq[stream] = nxt
            if event.id in sub.delivered:
                continue                       # at-least-once, delivered once
            sub.delivered.add(event.id)
            if sub.wants(event):
                self._invoke(sub, event)

    def _invoke(self, sub: Subscription, event: Event) -> None:
        self.clock.observe(event.lamport)
        try:
            produced = sub.handler(event) or []
        except Exception as exc:                # a broken agent must not stop the bus
            self.dead_letters.append(
                {"subscriber": sub.name, "event": event.id, "type": event.type, "error": str(exc)}
            )
            return
        self.trace.append({"subscriber": sub.name, "event": event.type,
                           "lamport": event.lamport, "produced": len(produced)})
        for out in produced:
            out.caused_by(event)
            self.publish(out)

    # -------------------------------------------------------------- inspection

    def pending_count(self) -> int:
        return sum(len(p) for s in self.subs for p in s.pending.values())
