"""
Slack event/command handlers. Three ways in, one orchestrator out:

1. Slash command /pm <text>       -- structured or free-text request
2. @mention in a channel           -- conversational request
3. File upload (tasks/scoring/cost CSV) -- structured request, auto-detected

Every path ends the same way: agents.orchestrator.handle_request(...) ->
formatting.brief_blocks(...) posted back into the channel/thread, with
human-decision buttons wired to decision_* action handlers below.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from agents.orchestrator import handle_request
from agents.audit import log_event
from agents.parsers import detect_and_parse, ParseError
from slack_app.formatting import brief_blocks, decision_confirmation_text, error_blocks

DECISION_LABELS = {
    "decision_approve": "✅ Approved",
    "decision_discuss": "\U0001f4ac Flagged for further discussion",
    "decision_reject": "❌ Rejected",
}


def register_handlers(app):
    @app.command("/pm")
    def handle_slash_command(ack, respond, command):
        ack()
        text = (command.get("text") or "").strip()
        if not text:
            respond(
                "Usage: `/pm <question or request>` — e.g. `/pm we need to pick between "
                "three vendors on cost, quality and delivery time`. You can also just "
                "@-mention me, or drop a tasks/scoring/cost CSV in the channel."
            )
            return
        result = handle_request(text, source="slash_command", requester=command["user_id"])
        respond(blocks=brief_blocks(result, command["user_id"]), response_type="in_channel")

    @app.event("app_mention")
    def handle_mention(event, say, client):
        text = event.get("text", "")
        # strip the leading "<@BOTID>" mention
        parts = text.split(">", 1)
        user_text = parts[1].strip() if len(parts) > 1 else text
        if not user_text:
            say(text="Mention me with a question, e.g. `@Tarteeb how's Project X tracking against budget?`", thread_ts=event.get("ts"))
            return
        result = handle_request(user_text, source="mention", requester=event["user"])
        say(blocks=brief_blocks(result, event["user"]), thread_ts=event.get("ts"))

    @app.event("message")
    def handle_file_upload(event, say, client, logger):
        files = event.get("files") or []
        if not files:
            return  # not a file-bearing message, ignore (avoids double-handling app_mention etc)

        for f in files:
            if not f.get("name", "").lower().endswith(".csv"):
                continue
            try:
                url = f["url_private_download"]
                token = client.token
                resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=15)
                resp.raise_for_status()
                content = resp.text
                structured_hint = detect_and_parse(f["name"], content)
            except ParseError as e:
                say(blocks=error_blocks(f"Couldn't read `{f['name']}`: {e}"), thread_ts=event.get("ts"))
                continue
            except Exception as e:
                logger.exception("file download/parse failed")
                say(blocks=error_blocks(f"Something went wrong reading `{f['name']}`: {e}"), thread_ts=event.get("ts"))
                continue

            result = handle_request(
                f"Analyze uploaded file {f['name']}",
                source="file_upload",
                requester=event.get("user", "unknown"),
                structured_hint=structured_hint,
            )
            say(blocks=brief_blocks(result, event.get("user", "unknown")), thread_ts=event.get("ts"))

    @app.action("decision_approve")
    @app.action("decision_discuss")
    @app.action("decision_reject")
    def handle_decision(ack, body, action, respond):
        ack()
        action_id = action["action_id"]
        event_id = action["value"]
        user_id = body["user"]["id"]
        label = DECISION_LABELS.get(action_id, action_id)

        log_event(
            source="human_decision", requester=user_id, user_text=None,
            outcome="human_decision", decision=label, decision_for_event=event_id,
        )
        respond(
            replace_original=False,
            text=decision_confirmation_text(label, user_id),
        )
