#!/usr/bin/env python3
"""
Watch the agents disagree.

Scheduler wants a task closed. Risk vetoes it. Compliance refuses to resolve
an agent disagreement on its own and escalates. Two humans then answer at the
same moment, and exactly one of them wins.

  python demo/negotiation_demo.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.negotiation import wire
from bus.bus import EventBus
from bus.events import Event, HUMAN_DECISION
from bus.store import ConcurrencyError

RISKS = {
    "T-47": [
        {"name": "Unvalidated file upload", "severity": 20, "status": "open"},
        {"name": "Verbose error messages", "severity": 6, "status": "open"},
    ],
    "T-12": [{"name": "Minor copy inconsistency", "severity": 3, "status": "open"}],
}


def rule(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def show(bus, since=0):
    for e in bus.store.all()[since:]:
        who = f"{e.actor:<11}"
        print(f"  [{e.lamport:>2}] {who} {e.type:<24} {_one_line(e)}")
    return len(bus.store.all())


def _one_line(e):
    p = e.payload
    for k in ("reason", "conflict", "basis", "decision", "summary"):
        if k in p:
            v = p[k]
            return (v[-1] if isinstance(v, list) and v else str(v))[:88]
    return ""


def main():
    bus = EventBus()
    agents = wire(bus, risks_by_task=RISKS)

    rule("1. A clean task closes with no human involved")
    n = len(bus.store.all())
    agents["scheduler"].propose_close("T-12", "copy review signed off")
    n = show(bus, n)

    rule("2. A risky task: Scheduler proposes, Risk vetoes, Compliance escalates")
    agents["scheduler"].propose_close("T-47", "all acceptance tests pass")
    n = show(bus, n)

    rule("3. Two humans answer the escalation at the same instant")
    stream = "task/T-47"
    version = bus.store.version(stream)
    print(f"  Both clients read stream '{stream}' at version {version}.")
    print("  Khadeja presses Uphold. Rama presses Override. Both write at once.\n")

    bus.publish(
        Event(type=HUMAN_DECISION, stream=stream, actor="Khadeja Ahmed",
              payload={"task_id": "T-47", "decision": "uphold",
                       "reason": "fix the upload validation before release"}),
        expected_version=version,
    )
    try:
        bus.publish(
            Event(type=HUMAN_DECISION, stream=stream, actor="Rama Abdallah",
                  payload={"task_id": "T-47", "decision": "override",
                           "reason": "deadline, accept for v1"}),
            expected_version=version,
        )
        print("  BUG: both writes were accepted.")
    except ConcurrencyError as exc:
        print(f"  Rejected: {exc}")
        print("  Rama is told the decision was already made, rather than silently")
        print("  overwriting it. She can still raise a new override on top of it.")
    print()
    n = show(bus, n)

    rule("What the Reporter would post")
    for line in agents["reporter"].lines:
        print("  -", line)

    rule("Integrity")
    v = bus.store.verify()
    print(f"  {len(bus.store.all())} events, hash chain {'intact' if v['ok'] else 'BROKEN at ' + str(v['broken_at'])}")
    print(f"  dead letters: {bus.dead_letters or 'none'}")
    print(f"  undelivered (buffered) events: {bus.pending_count()}")


if __name__ == "__main__":
    main()
