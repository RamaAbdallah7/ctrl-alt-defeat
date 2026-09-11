"""
Multi-provider LLM layer.

The app only ever needs two things from a language model:

  1. route_with_tools(...)  -- turn a messy human request into structured
     engine calls (or one clarifying question)
  2. complete_text(...)     -- write the consolidated executive brief

Both are attempted against providers in priority order:

  Anthropic  (claude-sonnet-5)   -- primary; best tool-use routing
  Google Gemini                  -- fallback if Anthropic errors / rate-limits
  (none)                         -- caller uses its own deterministic fallback

Design rules:
  * Nothing here raises on a provider outage. A failed provider is logged to
    stderr and we move to the next one. If every provider fails, we return
    None and the caller drops to templated/offline mode -- a hackathon demo
    must never die because of a network blip.
  * The provider order and model ids are env-configurable (TARTEEB_MODEL,
    TARTEEB_GEMINI_MODEL, TARTEEB_LLM_PROVIDERS).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

ANTHROPIC_MODEL = os.environ.get("TARTEEB_MODEL", "claude-sonnet-5")
GEMINI_MODEL = os.environ.get("TARTEEB_GEMINI_MODEL", "gemini-2.5-flash")

# comma-separated, in priority order; unknown names are ignored
_PROVIDER_ORDER = [
    p.strip().lower()
    for p in os.environ.get("TARTEEB_LLM_PROVIDERS", "anthropic,gemini").split(",")
    if p.strip()
]


def _warn(msg: str) -> None:
    print(f"[llm] {msg}", file=sys.stderr)


# --------------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------------

_anthropic_client = None
_anthropic_dead = False


def _anthropic():
    global _anthropic_client, _anthropic_dead
    if _anthropic_dead:
        return None
    if _anthropic_client is not None:
        return _anthropic_client
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        _anthropic_dead = True
        return None
    try:
        import anthropic

        _anthropic_client = anthropic.Anthropic(api_key=key)
        return _anthropic_client
    except Exception as e:  # pragma: no cover - import/config failure
        _warn(f"anthropic client unavailable: {e}")
        _anthropic_dead = True
        return None


def _anthropic_route(system: str, tools: list, user_text: str) -> Optional[dict]:
    client = _anthropic()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1500,
            system=system,
            tools=tools,
            messages=[{"role": "user", "content": user_text}],
        )
    except Exception as e:
        _warn(f"anthropic routing failed: {e}")
        return None

    tool_calls, clarifying = [], None
    for block in resp.content:
        if block.type == "tool_use":
            if block.name == "ask_clarifying_question":
                clarifying = block.input.get("question")
            else:
                tool_calls.append({"name": block.name, "input": block.input})
    return {"tool_calls": tool_calls, "clarifying_question": clarifying, "provider": "anthropic"}


def _anthropic_text(system: str, prompt: str, max_tokens: int) -> Optional[str]:
    client = _anthropic()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        _warn(f"anthropic completion failed: {e}")
        return None
    return "".join(b.text for b in resp.content if b.type == "text").strip() or None


# --------------------------------------------------------------------------
# Google Gemini (fallback)
#
# Gemini's function-calling schema handling is stricter than Anthropic's
# (e.g. no additionalProperties), so instead of porting the tool schemas we
# ask Gemini to return a single JSON object in a fixed shape and map it back
# to the same {tool_calls, clarifying_question} contract. Slower path, but
# it only runs when the primary provider is down.
# --------------------------------------------------------------------------

_gemini_client = None
_gemini_dead = False

_GEMINI_ROUTER_SUFFIX = """

---
You do not have function-calling here. Respond with ONE JSON object and nothing
else (no markdown fences). Shape:

{
  "engine_calls": [
    {"name": "run_schedule_analysis", "input": {"tasks": [{"id": "A", "name": "...", "duration": 3, "predecessors": []}]}},
    {"name": "run_scoring_analysis", "input": {"criteria": [{"name": "Cost", "weight": 30}], "options": [{"name": "Vendor A", "scores": {"Cost": 80}}]}},
    {"name": "run_cost_analysis", "input": {"pv": 0, "ev": 0, "ac": 0, "bac": 0}}
  ],
  "clarifying_question": null
}

Include only the engine_calls the request actually supplies data for. If there
is not enough data for any engine, use an empty engine_calls list and put ONE
short question in clarifying_question. Never invent numbers.
"""


def _gemini():
    global _gemini_client, _gemini_dead
    if _gemini_dead:
        return None
    if _gemini_client is not None:
        return _gemini_client
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        _gemini_dead = True
        return None
    try:
        from google import genai

        _gemini_client = genai.Client(api_key=key)
        return _gemini_client
    except Exception as e:  # pragma: no cover
        _warn(f"gemini client unavailable: {e}")
        _gemini_dead = True
        return None


def _gemini_generate(prompt: str, system: Optional[str] = None) -> Optional[str]:
    client = _gemini()
    if client is None:
        return None
    try:
        from google.genai import types

        cfg = types.GenerateContentConfig(system_instruction=system) if system else None
        resp = client.models.generate_content(
            model=GEMINI_MODEL, contents=prompt, config=cfg
        )
        return (resp.text or "").strip() or None
    except Exception as e:
        _warn(f"gemini generate failed: {e}")
        return None


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _gemini_route(system: str, tools: list, user_text: str) -> Optional[dict]:
    raw = _gemini_generate(user_text, system=system + _GEMINI_ROUTER_SUFFIX)
    if raw is None:
        return None
    parsed = _extract_json(raw)
    if parsed is None:
        _warn("gemini routing returned unparseable JSON")
        return None
    calls = [
        {"name": c["name"], "input": c.get("input", {})}
        for c in parsed.get("engine_calls", [])
        if isinstance(c, dict) and c.get("name")
    ]
    return {
        "tool_calls": calls,
        "clarifying_question": parsed.get("clarifying_question"),
        "provider": "gemini",
    }


def _gemini_text(system: str, prompt: str, max_tokens: int) -> Optional[str]:
    return _gemini_generate(prompt, system=system)


# --------------------------------------------------------------------------
# Public API -- try each configured provider in order
# --------------------------------------------------------------------------

_ROUTERS = {"anthropic": _anthropic_route, "gemini": _gemini_route}
_COMPLETERS = {"anthropic": _anthropic_text, "gemini": _gemini_text}


def providers_available() -> list:
    """Which providers currently have credentials + a usable client."""
    out = []
    if _anthropic() is not None:
        out.append("anthropic")
    if _gemini() is not None:
        out.append("gemini")
    return out


def route_with_tools(system: str, tools: list, user_text: str) -> Optional[dict]:
    for name in _PROVIDER_ORDER:
        router = _ROUTERS.get(name)
        if router is None:
            continue
        result = router(system, tools, user_text)
        if result is not None:
            return result
    return None


def complete_text(system: str, prompt: str, max_tokens: int = 700) -> Optional[str]:
    for name in _PROVIDER_ORDER:
        completer = _COMPLETERS.get(name)
        if completer is None:
            continue
        result = completer(system, prompt, max_tokens)
        if result is not None:
            return result
    return None
