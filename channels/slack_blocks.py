"""BriefView -> Slack Block Kit."""

from __future__ import annotations

from channels.brief import BriefView, DECISIONS

_STYLE = {"good": "primary", "danger": "danger", "default": None}
_EMOJI = {"decision_approve": "✅", "decision_discuss": "\U0001f4ac", "decision_reject": "❌"}


def render(view: BriefView) -> list:
    if view.status == "needs_info":
        return [{"type": "section", "text": {"type": "mrkdwn",
                 "text": f":thinking_face: *{view.title}:*\n{view.body}"}}]
    if view.status == "error":
        return [{"type": "section", "text": {"type": "mrkdwn", "text": f":warning: {view.body}"}}]

    blocks = [{"type": "header", "text": {"type": "plain_text", "text": view.title}}]

    ctx = view.context or ""
    if view.requester:
        ctx += f"  -  requested by <@{view.requester}>"
    if ctx:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": ctx}]})

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": view.body}})

    if view.findings:
        blocks.append({"type": "divider"})
        for f in view.findings:
            mark = "" if f.ok else ":warning: "
            blocks.append({"type": "section", "text": {"type": "mrkdwn",
                           "text": f"{mark}*{f.agent}*\n{f.text}"}})

    if view.wants_decision:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "actions",
            "block_id": f"human_decision__{view.event_id}",
            "elements": [
                {k: v for k, v in {
                    "type": "button",
                    "text": {"type": "plain_text", "text": f"{_EMOJI.get(d['id'], '')} {d['label']}".strip()},
                    "style": _STYLE.get(d["style"]),
                    "action_id": d["id"],
                    "value": view.event_id,
                }.items() if v is not None}
                for d in DECISIONS
            ],
        })

    if view.footer:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"_{view.footer}_"}]})
    return blocks
