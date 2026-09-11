"""
Slack rendering. The presentation model lives in channels/brief.py and the
Block Kit rendering in channels/slack_blocks.py, so Slack and Microsoft Teams
render the same brief rather than each growing their own copy of it.

This module stays as the Slack app's entry point into that layer.
"""

from __future__ import annotations

from channels import brief as brief_model
from channels import slack_blocks


def brief_blocks(result: dict, requester: str) -> list:
    return slack_blocks.render(brief_model.from_result(result, requester=requester))


def decision_confirmation_text(decision_label: str, user_id: str) -> str:
    return f"{decision_label} by <@{user_id}>. Logged to the audit trail."


def error_blocks(message: str) -> list:
    return slack_blocks.render(brief_model.error_view(message))
