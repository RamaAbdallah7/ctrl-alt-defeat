"""
Slack event/command handlers. Four ways in, one orchestrator out:

1. Slash command /pm <text>       -- structured or free-text request
2. @mention in a channel           -- conversational request
3. File upload (tasks/scoring/cost CSV) -- structured request, auto-detected
4. A reply inside the bot's own thread -- a follow-up, applied as a delta
   against what was computed the first time

Every path pulls recent channel history first and hands it to the router, so
the triggering message does not have to be self-contained. "How are we doing
on those numbers?" is answerable only because the numbers are upstream in the
channel; that is what makes this native to Slack rather than delivered
through it.

Replies land in-thread, and the thread's structured input is persisted, so a
follow-up re-runs the affected engines instead of starting over.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from agents.context import from_slack_history
from agents.orchestrator import handle_request
from agents.audit import log_event
from agents.parsers import detect_and_parse, ParseError
from agents.thread_state import ThreadStore
from slack_app.formatting import brief_blocks, decision_confirmation_text, error_blocks

HISTORY_LIMIT = 30
_threads = ThreadStore()


def _thread_key(channel: str, thread_ts: str) -> str:
    return f"{channel}/{thread_ts}"


def _display_names(client, user_ids) -> dict:
    """Resolve ids to names so findings read 'per Sara's cost sheet', not per U04AB."""
    names = {}
    for uid in {u for u in user_ids if u and not str(u).startswith("B")}:
        try:
            info = client.users_info(user=uid)
            profile = info["user"].get("profile", {})
            names[uid] = (profile.get("display_name") or profile.get("real_name")
                          or info["user"].get("name") or uid)
        except Exception:
            names[uid] = uid          # a missing scope must not break the request
    return names


def _fetch_context(client, channel: str, thread_ts: str = None, bot_user_id: str = None):
    """Recent channel (or thread) history, with names resolved."""
    try:
        if thread_ts:
            resp = client.conversations_replies(channel=channel, ts=thread_ts,
                                                limit=HISTORY_LIMIT)
            messages = list(reversed(resp.get("messages", [])))   # replies come oldest first
        else:
            resp = client.conversations_history(channel=channel, limit=HISTORY_LIMIT)
            messages = resp.get("messages", [])
    except Exception:
        # not in the channel, or missing history scope -- degrade to no context
        return None

    names = _display_names(client, [m.get("user") for m in messages])
    ctx = from_slack_history(messages, bot_user_id=bot_user_id, names=names)
    ctx.channel, ctx.thread_ts = channel, thread_ts
    return ctx

DECISION_LABELS = {
    "decision_approve": "✅ Approved",
    "decision_discuss": "\U0001f4ac Flagged for further discussion",
    "decision_reject": "❌ Rejected",
}


_BOT_ID = {}


def _bot_id(client):
    """auth.test once, then cache -- it is the same for the life of the process."""
    if "id" not in _BOT_ID:
        try:
            _BOT_ID["id"] = client.auth_test()["user_id"]
        except Exception:
            _BOT_ID["id"] = None
    return _BOT_ID["id"]


def register_handlers(app):
    @app.command("/pm")
    def handle_slash_command(ack, respond, command, client, say):
        ack()
        text = (command.get("text") or "").strip()
        if not text:
            respond(
                "Usage: `/pm <question or request>` — e.g. `/pm we need to pick between "
                "three vendors on cost, quality and delivery time`. You can also just "
                "@-mention me, or drop a tasks/scoring/cost CSV in the channel."
            )
            return

        channel = command["channel_id"]
        ctx = _fetch_context(client, channel, bot_user_id=_bot_id(client))
        result = handle_request(text, source="slash_command",
                                requester=command["user_id"], context=ctx)

        posted = say(blocks=brief_blocks(result, command["user_id"]),
                     text="Tarteeb brief")
        ts = posted.get("ts") if isinstance(posted, dict) else None
        if ts:
            _threads.save(_thread_key(channel, ts), channel=channel,
                          tool_calls=result.get("tool_calls"), brief=result.get("brief"),
                          event_id=result.get("event_id"), requester=command["user_id"])

    @app.event("app_mention")
    def handle_mention(event, say, client):
        text = event.get("text", "")
        parts = text.split(">", 1)
        user_text = parts[1].strip() if len(parts) > 1 else text
        if not user_text:
            say(text="Mention me with a question, e.g. `@Tarteeb how's Project X tracking against budget?`",
                thread_ts=event.get("ts"))
            return

        channel = event["channel"]
        root = event.get("thread_ts") or event.get("ts")
        key = _thread_key(channel, root)
        prior = _threads.load(key) or {}

        ctx = _fetch_context(client, channel,
                             thread_ts=event.get("thread_ts"),
                             bot_user_id=_bot_id(client))
        result = handle_request(
            user_text, source="mention", requester=event["user"], context=ctx,
            prior_calls=prior.get("tool_calls") if not prior.get("locked") else None,
        )
        say(blocks=brief_blocks(result, event["user"]), thread_ts=root,
            text="Tarteeb brief")
        _threads.save(key, channel=channel, tool_calls=result.get("tool_calls"),
                      brief=result.get("brief"), event_id=result.get("event_id"),
                      requester=event["user"])

    @app.event("message")
    def handle_message(event, say, client, logger):
        if event.get("bot_id") or event.get("subtype") in ("message_changed", "message_deleted"):
            return

        channel = event.get("channel")
        thread_ts = event.get("thread_ts")
        files = event.get("files") or []

        # A reply inside a thread Tarteeb is already running: treat it as a
        # follow-up on the previous analysis rather than a new question.
        if thread_ts and not files:
            key = _thread_key(channel, thread_ts)
            state = _threads.load(key)
            if not state or not state.get("tool_calls"):
                return                       # not our thread
            if state.get("locked"):
                say(text="This thread was approved and locked. Start a new request to change it.",
                    thread_ts=thread_ts)
                return
            text = (event.get("text") or "").strip()
            if not text or f"<@{_bot_id(client)}>" in text:
                return                       # a mention is handled by app_mention

            ctx = _fetch_context(client, channel, thread_ts=thread_ts,
                                 bot_user_id=_bot_id(client))
            result = handle_request(text, source="thread_followup",
                                    requester=event.get("user", "unknown"),
                                    context=ctx, prior_calls=state["tool_calls"])
            if result.get("status") == "ok" and not result.get("delta"):
                return                       # nothing was a follow-up; stay quiet
            say(blocks=brief_blocks(result, event.get("user", "unknown")),
                thread_ts=thread_ts, text="Tarteeb updated brief")
            _threads.save(key, tool_calls=result.get("tool_calls"),
                          brief=result.get("brief"), event_id=result.get("event_id"))
            return

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
            root = event.get("thread_ts") or event.get("ts")
            say(blocks=brief_blocks(result, event.get("user", "unknown")),
                thread_ts=root, text="Tarteeb brief")
            _threads.save(_thread_key(channel, root), channel=channel,
                          tool_calls=result.get("tool_calls"), brief=result.get("brief"),
                          event_id=result.get("event_id"),
                          requester=event.get("user", "unknown"))

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
