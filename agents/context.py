"""
Channel context.

The difference between a bot that lives in Slack and a bot that is merely
delivered through Slack is whether it reads the room. A self-contained
request -- "run CPM on these ten tasks" -- could arrive by email. A request
that only makes sense because of what was said twenty messages ago could not.

This module turns raw channel history into something the router can use:

  * the recent conversation, oldest first, with the bot's own messages
    dropped so it does not reason about its own output as if it were input
  * the files people dropped, so "the cost sheet Sara posted" resolves to an
    actual CSV rather than a clarifying question
  * the figures already stated in the channel, so "those numbers" resolves
  * who is in the conversation, so findings can be attributed by name

Nothing here calls an LLM. It assembles evidence; the router decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MAX_MESSAGES = 30
MAX_CHARS = 6000

# "40,000" / "$1.2m" / "12%" / "3 days" -- figures worth resolving a reference to
# Commas only where a thousands separator belongs, so "120,000, we've spent"
# yields "120,000" and not "120,000," -- a captured figure with punctuation
# stuck to it fails to match anything downstream.
NUMBER = re.compile(
    r"(?<![\w.])(?:\$|USD\s*|AED\s*)?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    r"(?:\s*(?:%|k\b|m\b|bn\b|days?\b|weeks?\b|months?\b))?",
    re.IGNORECASE,
)
FILE_HINT = re.compile(r"\b([\w\-. ]+\.(?:csv|xlsx?|json))\b", re.IGNORECASE)


@dataclass
class ContextMessage:
    author: str                 # display name where known, else the raw id
    text: str
    ts: str
    author_id: Optional[str] = None
    is_bot: bool = False
    files: List[dict] = field(default_factory=list)

    def mentions_file(self) -> List[str]:
        return [m.group(1) for m in FILE_HINT.finditer(self.text or "")]


@dataclass
class ChannelContext:
    messages: List[ContextMessage] = field(default_factory=list)
    channel: Optional[str] = None
    thread_ts: Optional[str] = None

    # ------------------------------------------------------------- assembly

    @property
    def participants(self) -> List[str]:
        seen, out = set(), []
        for m in self.messages:
            if m.is_bot or m.author in seen:
                continue
            seen.add(m.author)
            out.append(m.author)
        return out

    def files(self) -> List[dict]:
        """Every file shared in the window, newest last, with who shared it."""
        out = []
        for m in self.messages:
            for f in m.files or []:
                out.append({"name": f.get("name"), "author": m.author, "ts": m.ts,
                            "id": f.get("id"), "url": f.get("url_private_download")})
        return out

    def latest_file(self, pattern: str = None) -> Optional[dict]:
        """The most recent shared file, optionally matching a name fragment."""
        files = self.files()
        if pattern:
            frag = pattern.lower()
            files = [f for f in files if frag in (f.get("name") or "").lower()]
        return files[-1] if files else None

    def figures(self) -> List[dict]:
        """Numbers already stated in the channel, with who said them."""
        out = []
        for m in self.messages:
            if m.is_bot:
                continue
            for match in NUMBER.finditer(m.text or ""):
                value = match.group(0).strip()
                if len(value.strip("$ ")) < 2:      # skip bare single digits
                    continue
                out.append({"value": value, "author": m.author, "ts": m.ts,
                            "sentence": _sentence_around(m.text, match.start())})
        return out

    # ------------------------------------------------------------ rendering

    def render(self, max_messages: int = MAX_MESSAGES, max_chars: int = MAX_CHARS) -> str:
        """
        The transcript as the router sees it. Oldest first, because the router
        needs to know what superseded what.
        """
        msgs = [m for m in self.messages if not m.is_bot][-max_messages:]
        lines = []
        for m in msgs:
            attach = ""
            if m.files:
                attach = "  [shared: " + ", ".join(f.get("name", "file") for f in m.files) + "]"
            lines.append(f"{m.author}: {(m.text or '').strip()}{attach}")
        text = "\n".join(lines)
        if len(text) > max_chars:
            text = "...(earlier messages trimmed)...\n" + text[-max_chars:]
        return text

    def as_prompt_block(self) -> str:
        if not self.messages:
            return ""
        parts = [
            "RECENT CHANNEL CONTEXT (oldest first). The person may be referring to "
            "something here rather than restating it. Use it to fill gaps -- but never "
            "invent a number that does not appear in the conversation or the request.",
            "",
            self.render(),
        ]
        files = self.files()
        if files:
            parts += ["", "FILES SHARED RECENTLY:"]
            parts += [f"  - {f['name']} (shared by {f['author']})" for f in files]
        return "\n".join(parts)

    def is_empty(self) -> bool:
        return not [m for m in self.messages if not m.is_bot]


def _sentence_around(text: str, index: int) -> str:
    start = max(text.rfind(".", 0, index), text.rfind("\n", 0, index)) + 1
    end = min([x for x in (text.find(".", index), text.find("\n", index), len(text)) if x != -1])
    return text[start:end].strip()[:160]


def from_slack_history(messages: List[dict], bot_user_id: str = None,
                       names: Dict[str, str] = None) -> ChannelContext:
    """
    Build context from a Slack conversations.history / replies payload.
    `names` maps user id -> display name (from users.info), so findings can be
    attributed to a person rather than to U04AB12CD.
    """
    names = names or {}
    out = []
    for m in reversed(messages or []):        # Slack returns newest first
        uid = m.get("user") or m.get("bot_id") or "unknown"
        is_bot = bool(m.get("bot_id")) or (bot_user_id is not None and uid == bot_user_id)
        out.append(ContextMessage(
            author=names.get(uid, uid),
            author_id=uid,
            text=m.get("text") or "",
            ts=m.get("ts") or "",
            is_bot=is_bot,
            files=m.get("files") or [],
        ))
    return ChannelContext(messages=out)
