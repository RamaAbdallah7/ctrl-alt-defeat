"""
The negotiating agents.

Four specialists that do not call each other. Each owns one decision and
publishes it; the protocol is what emerges from what they read:

  Scheduler   owns the timeline. Proposes closing a task when its work is done.
  Risk        owns exposure. Can VETO a closure -- an unmitigated high-severity
              risk attached to the task blocks it, whatever the schedule wants.
  Compliance  owns the audit trail and approvals. Collects the votes, applies
              the conflict-resolution policy, and escalates to a human when the
              agents disagree. It is the only agent that can close a task.
  Reporter    owns the summary. Says what happened, for people who were not
              watching the bus.

Conflict-resolution policy, deliberately explicit rather than emergent:

  1. A veto beats any number of endorsements. Safety is not a majority vote.
  2. A vetoed closure is never auto-resolved -- it escalates to a human, who
     may override with a reason that is recorded.
  3. Quorum: Compliance waits for every registered reviewer before resolving.
     Missing reviewers block, they do not default to approval.

That last rule is the one most systems get wrong: a reviewer that never
answers must not be read as consent.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from bus.events import (
    Event,
    TASK_CLOSE_PROPOSED, TASK_CLOSED, TASK_CLOSE_BLOCKED,
    REVIEW_ENDORSED, REVIEW_VETOED,
    ESCALATION_RAISED, HUMAN_DECISION, BRIEF_PUBLISHED,
)


class SchedulerAgent:
    """Owns timelines. Proposes; never closes."""

    name = "Scheduler"

    def __init__(self, bus):
        self.bus = bus

    def propose_close(self, task_id: str, reason: str) -> Event:
        return self.bus.publish(Event(
            type=TASK_CLOSE_PROPOSED,
            stream=f"task/{task_id}",
            actor=self.name,
            payload={"task_id": task_id, "reason": reason},
        ))


class RiskAgent:
    """Owns exposure scoring. Holds a veto over closure."""

    name = "Risk"

    def __init__(self, risks_by_task: Dict[str, list] = None, veto_threshold: float = 15.0):
        self.risks_by_task = risks_by_task or {}
        self.veto_threshold = veto_threshold

    def __call__(self, event: Event) -> List[Event]:
        if event.type != TASK_CLOSE_PROPOSED:
            return []
        task_id = event.payload["task_id"]
        blocking = [
            r for r in self.risks_by_task.get(task_id, [])
            if r.get("severity", 0) >= self.veto_threshold and r.get("status", "open") == "open"
        ]
        if blocking:
            worst = max(blocking, key=lambda r: r["severity"])
            return [Event(
                type=REVIEW_VETOED, stream=event.stream, actor=self.name,
                payload={
                    "task_id": task_id,
                    "reason": f"{worst['name']} is open at severity {worst['severity']:g}/25, "
                              f"at or above the veto threshold of {self.veto_threshold:g}",
                    "risks": [r["name"] for r in blocking],
                },
            )]
        return [Event(
            type=REVIEW_ENDORSED, stream=event.stream, actor=self.name,
            payload={"task_id": task_id, "reason": "no open risk above the veto threshold"},
        )]


class ComplianceAgent:
    """
    Owns approvals and the audit trail. The only agent that can close a task.
    Applies the conflict policy and escalates rather than guessing.
    """

    name = "Compliance"

    def __init__(self, bus, reviewers=("Risk",)):
        self.bus = bus
        self.reviewers = list(reviewers)
        self.votes: Dict[str, Dict[str, Event]] = {}
        self.escalated: Dict[str, str] = {}     # stream -> escalation event id

    def __call__(self, event: Event) -> List[Event]:
        if event.type == TASK_CLOSE_PROPOSED:
            self.votes[event.stream] = {}
            return []

        if event.type in (REVIEW_ENDORSED, REVIEW_VETOED):
            self.votes.setdefault(event.stream, {})[event.actor] = event
            return self._resolve(event)

        if event.type == HUMAN_DECISION:
            return self._apply_human(event)

        return []

    # -------------------------------------------------------------- resolution

    def _resolve(self, event: Event) -> List[Event]:
        votes = self.votes.get(event.stream, {})
        missing = [r for r in self.reviewers if r not in votes]
        if missing:
            # Quorum not met. A reviewer that has not answered is NOT consent.
            return []

        vetoes = [v for v in votes.values() if v.type == REVIEW_VETOED]
        task_id = event.payload["task_id"]

        if vetoes:
            # Policy 1 and 2: a veto beats endorsements and always escalates.
            self.escalated[event.stream] = event.id
            return [Event(
                type=ESCALATION_RAISED, stream=event.stream, actor=self.name,
                payload={
                    "task_id": task_id,
                    "conflict": f"{self.name} cannot resolve this: "
                                f"{len(votes) - len(vetoes)} endorsement(s) against "
                                f"{len(vetoes)} veto(es).",
                    "vetoed_by": [v.actor for v in vetoes],
                    "reasons": [v.payload.get("reason") for v in vetoes],
                    "requires": "human override with a recorded reason",
                },
            )]

        return [Event(
            type=TASK_CLOSED, stream=event.stream, actor=self.name,
            payload={"task_id": task_id, "basis": "unanimous endorsement",
                     "endorsed_by": [v.actor for v in votes.values()]},
        )]

    def _apply_human(self, event: Event) -> List[Event]:
        decision = (event.payload.get("decision") or "").lower()
        task_id = event.payload.get("task_id")
        if decision == "override":
            return [Event(
                type=TASK_CLOSED, stream=event.stream, actor=self.name,
                payload={"task_id": task_id,
                         "basis": "human override of an agent veto",
                         "overridden_by": event.actor,
                         "reason": event.payload.get("reason")},
            )]
        return [Event(
            type=TASK_CLOSE_BLOCKED, stream=event.stream, actor=self.name,
            payload={"task_id": task_id, "basis": "human upheld the veto",
                     "upheld_by": event.actor,
                     "reason": event.payload.get("reason")},
        )]


class ReporterAgent:
    """Owns the summary. Reads everything, decides nothing."""

    name = "Reporter"

    def __init__(self):
        self.lines: List[str] = []

    def __call__(self, event: Event) -> List[Event]:
        p = event.payload
        say = {
            TASK_CLOSE_PROPOSED: lambda: f"Scheduler proposed closing {p['task_id']}: {p['reason']}.",
            REVIEW_ENDORSED: lambda: f"{event.actor} endorsed it -- {p['reason']}.",
            REVIEW_VETOED: lambda: f"{event.actor} VETOED it -- {p['reason']}.",
            ESCALATION_RAISED: lambda: (
                f"Escalated to a human: {p['conflict']} Vetoed by "
                f"{', '.join(p['vetoed_by'])}. Needs {p['requires']}."),
            TASK_CLOSED: lambda: f"{p['task_id']} closed on {p['basis']}.",
            TASK_CLOSE_BLOCKED: lambda: f"{p['task_id']} stays open -- {p['basis']}.",
            HUMAN_DECISION: lambda: f"{event.actor} decided: {p.get('decision')}.",
        }.get(event.type)
        if say is None:
            return []
        line = say()
        self.lines.append(line)
        if event.type in (TASK_CLOSED, TASK_CLOSE_BLOCKED):
            return [Event(type=BRIEF_PUBLISHED, stream=event.stream, actor=self.name,
                          payload={"summary": list(self.lines)})]
        return []


def wire(bus, risks_by_task=None, reviewers=("Risk",)):
    """Subscribe the roster to the bus and hand back the agents."""
    scheduler = SchedulerAgent(bus)
    risk = RiskAgent(risks_by_task)
    compliance = ComplianceAgent(bus, reviewers=reviewers)
    reporter = ReporterAgent()

    bus.subscribe("Risk", risk, types=[TASK_CLOSE_PROPOSED])
    bus.subscribe("Compliance", compliance,
                  types=[TASK_CLOSE_PROPOSED, REVIEW_ENDORSED, REVIEW_VETOED, HUMAN_DECISION])
    bus.subscribe("Reporter", reporter)
    return {"scheduler": scheduler, "risk": risk,
            "compliance": compliance, "reporter": reporter}
