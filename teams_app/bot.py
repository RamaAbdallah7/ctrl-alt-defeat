"""
Tarteeb for Microsoft Teams.

Three ways in, the same orchestrator out -- deliberately mirroring the Slack
handlers so the two surfaces cannot drift apart in behaviour:

  1. a message to the bot (1:1 or @mention in a channel)
  2. a CSV attached to a message
  3. an Adaptive Card button, which is how a human decision comes back

Teams differences that actually bite, handled here:
  * In a channel the message text carries an `<at>Tarteeb</at>` mention that
    must be stripped, or the router reads the bot's own name as input.
  * Card buttons arrive as an ordinary message activity whose `value` holds
    the Action.Submit data -- not as a distinct event type the way Slack
    sends block_actions.
  * Teams file attachments are not the file: a channel upload arrives as a
    downloadUrl, and a personal-chat upload arrives as a consent card. Only
    the first is downloadable without extra permissions, which is what the
    demo uses.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from botbuilder.core import ActivityHandler, MessageFactory, TurnContext
from botbuilder.schema import Attachment, ChannelAccount

from agents.audit import log_event
from agents.orchestrator import handle_request
from agents.parsers import detect_and_parse, ParseError
from channels import brief as brief_model
from channels import teams_cards

DECISION_LABELS = {
    "decision_approve": "Approved",
    "decision_discuss": "Flagged for further discussion",
    "decision_reject": "Rejected",
}

_MENTION = re.compile(r"<at>.*?</at>", re.IGNORECASE | re.DOTALL)

WELCOME = (
    "I'm Tarteeb, a project-management copilot. Ask me a question in plain "
    "language -- about a schedule, a budget, a vendor choice, a business case "
    "-- or drop a tasks/scoring/cost CSV in here. I'll route it to whichever "
    "specialists apply and come back with one brief for you to decide on."
)


def _card_activity(view) -> "Activity":
    return MessageFactory.attachment(
        Attachment(
            content_type=teams_cards.CARD_CONTENT_TYPE,
            content=teams_cards.render(view),
        )
    )


class TarteebBot(ActivityHandler):
    async def on_members_added_activity(self, members_added: list, turn_context: TurnContext):
        for member in members_added:
            if member.id != turn_context.activity.recipient.id:
                await turn_context.send_activity(MessageFactory.text(WELCOME))

    async def on_message_activity(self, turn_context: TurnContext):
        activity = turn_context.activity

        # 1. an Adaptive Card button press arrives as a message with `value`
        value = activity.value or {}
        if isinstance(value, dict) and value.get("action") in DECISION_LABELS:
            return await self._handle_decision(turn_context, value)

        requester = self._requester(activity)

        # 2. a CSV attached to the message
        for att in (activity.attachments or []):
            if self._is_csv(att):
                handled = await self._handle_csv(turn_context, att, requester)
                if handled:
                    return

        # 3. plain text
        text = self._clean_text(activity.text or "")
        if not text:
            await turn_context.send_activity(MessageFactory.text(WELCOME))
            return

        result = handle_request(text, source="teams_message", requester=requester)
        view = brief_model.from_result(result, requester=requester)
        await turn_context.send_activity(_card_activity(view))

    # ---------------------------------------------------------------- helpers

    async def _handle_decision(self, turn_context: TurnContext, value: dict):
        label = DECISION_LABELS[value["action"]]
        user = self._requester(turn_context.activity)
        log_event(
            source="human_decision", requester=user, user_text=None,
            outcome="human_decision", decision=label,
            decision_for_event=value.get("event_id"),
        )
        name = getattr(turn_context.activity.from_property, "name", None) or "A reviewer"
        await turn_context.send_activity(
            MessageFactory.text(f"**{label}** by {name}. Logged to the audit trail.")
        )

    async def _handle_csv(self, turn_context: TurnContext, att: Attachment, requester: str) -> bool:
        url = self._download_url(att)
        if not url:
            await turn_context.send_activity(_card_activity(brief_model.error_view(
                f"I can see `{att.name}`, but Teams did not give me a link I can download "
                f"without extra permissions. Uploading it to a channel (rather than a "
                f"personal chat) gives me a direct link."
            )))
            return True
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            structured_hint = detect_and_parse(att.name, resp.text)
        except ParseError as e:
            await turn_context.send_activity(_card_activity(brief_model.error_view(
                f"Couldn't read `{att.name}`: {e}")))
            return True
        except Exception as e:
            await turn_context.send_activity(_card_activity(brief_model.error_view(
                f"Something went wrong reading `{att.name}`: {e}")))
            return True

        result = handle_request(
            f"Analyze uploaded file {att.name}",
            source="teams_file_upload", requester=requester,
            structured_hint=structured_hint,
        )
        await turn_context.send_activity(
            _card_activity(brief_model.from_result(result, requester=requester)))
        return True

    @staticmethod
    def _is_csv(att: Attachment) -> bool:
        name = (att.name or "").lower()
        return name.endswith(".csv") or (att.content_type or "").endswith("csv")

    @staticmethod
    def _download_url(att: Attachment):
        # channel uploads carry a downloadUrl in content; some clients put it on the attachment
        content = att.content if isinstance(att.content, dict) else {}
        return content.get("downloadUrl") or att.content_url

    @staticmethod
    def _clean_text(text: str) -> str:
        return _MENTION.sub("", text).strip()

    @staticmethod
    def _requester(activity) -> str:
        f = getattr(activity, "from_property", None)
        return (getattr(f, "id", None) or getattr(f, "name", None) or "unknown")
