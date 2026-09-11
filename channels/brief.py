"""
Transport-agnostic presentation model.

The orchestrator returns engine output; Slack wants Block Kit and Microsoft
Teams wants an Adaptive Card. Rather than let either platform's vocabulary
leak into the agents, both render from one `BriefView` built here.

Adding a third surface (email, a web hook, SMS) means writing one renderer
against this model -- it does not mean touching the orchestrator or the
specialists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from agents.specialists import BY_KEY


# The human decision is the same everywhere; only the rendering differs.
DECISIONS = [
    {"id": "decision_approve", "label": "Approve", "style": "good"},
    {"id": "decision_discuss", "label": "Discuss further", "style": "default"},
    {"id": "decision_reject", "label": "Reject", "style": "danger"},
]

FOOTER = "AI advises. Humans decide. This decision is logged to the audit trail."


@dataclass
class Finding:
    agent: str
    role: Optional[str]
    text: str
    ok: bool = True


@dataclass
class BriefView:
    status: str                      # "ok" | "needs_info" | "error"
    title: str
    body: str
    event_id: Optional[str] = None
    requester: Optional[str] = None
    findings: List[Finding] = field(default_factory=list)
    context: Optional[str] = None
    footer: str = FOOTER

    @property
    def wants_decision(self) -> bool:
        return self.status == "ok" and bool(self.event_id)


def from_result(result: dict, requester: str = None) -> BriefView:
    """Build the view from an agents.orchestrator.handle_request result."""
    if result.get("status") == "needs_info":
        return BriefView(
            status="needs_info",
            title="One more thing",
            body=result.get("question") or "I need more information to run an analysis.",
            requester=requester,
            footer="Reply in this thread and I'll pick it up.",
        )

    outputs = result.get("specialist_outputs") or {}
    findings = []
    for key, out in outputs.items():
        agent = BY_KEY.get(key)
        name = out.get("agent") or (agent.name if agent else key)
        if out.get("ok"):
            findings.append(Finding(
                agent=name,
                role=out.get("agent_role") or (agent.role if agent else None),
                text=_finding_text(key, out),
            ))
        else:
            findings.append(Finding(
                agent=name,
                role=out.get("agent_role") or (agent.role if agent else None),
                text=f"Could not report: {out.get('error')}",
                ok=False,
            ))

    # The offline templated brief already lists each specialist's finding in
    # its body. Repeating them underneath reads as a bug, so drop the separate
    # list when the body has already said it.
    body = result.get("brief") or "No brief was produced."
    if findings and all(f.agent in body for f in findings):
        findings = []

    n = len(outputs)
    provider = result.get("provider") or "offline"
    context = (
        f"{n} of 10 specialists reported"
        f"  -  routed by {provider}"
        + (f"  -  event {result['event_id']}" if result.get("event_id") else "")
    )

    return BriefView(
        status="ok",
        title="Tarteeb - Executive Brief",
        body=body,
        event_id=result.get("event_id"),
        requester=requester,
        findings=findings,
        context=context,
    )


def _finding_text(key: str, out: dict) -> str:
    from agents.specialists import report
    return report(key, out.get("result") or {}) or "Reported."


def error_view(message: str) -> BriefView:
    return BriefView(status="error", title="Something went wrong", body=message, footer="")
