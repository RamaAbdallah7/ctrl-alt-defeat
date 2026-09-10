"""Block Kit formatting: turns an orchestrator result into a Slack message,
including the human-decision buttons and a link to 'show the math'."""

from __future__ import annotations


def brief_blocks(result: dict, requester: str) -> list:
    if result["status"] == "needs_info":
        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": f":thinking_face: *I need one more thing:*\n{result['question']}"}},
        ]

    brief = result["brief"]
    domains = ", ".join(result["specialist_outputs"].keys()) or "none"
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": "DIR'A-PM — Executive Brief"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Specialists consulted: *{domains}*  •  requested by <@{requester}>  •  event `{result['event_id']}`"}]},
        {"type": "section", "text": {"type": "mrkdwn", "text": brief}},
        {"type": "divider"},
        {
            "type": "actions",
            "block_id": f"human_decision__{result['event_id']}",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "✅ Approve"}, "style": "primary", "action_id": "decision_approve", "value": result["event_id"]},
                {"type": "button", "text": {"type": "plain_text", "text": "\U0001f4ac Discuss further"}, "action_id": "decision_discuss", "value": result["event_id"]},
                {"type": "button", "text": {"type": "plain_text", "text": "❌ Reject"}, "style": "danger", "action_id": "decision_reject", "value": result["event_id"]},
            ],
        },
        {"type": "context", "elements": [{"type": "mrkdwn", "text": "_AI advises. Humans decide. This decision is logged to the audit trail._"}]},
    ]
    return blocks


def decision_confirmation_text(decision_label: str, user_id: str) -> str:
    return f"{decision_label} by <@{user_id}>. Logged to the audit trail."


def error_blocks(message: str) -> list:
    return [{"type": "section", "text": {"type": "mrkdwn", "text": f":warning: {message}"}}]
