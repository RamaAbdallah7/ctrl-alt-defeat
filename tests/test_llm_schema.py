"""The Gemini bridge: schema sanitising and staying in step with the engines."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import llm
from agents.tool_schemas import TOOLS
from agents.orchestrator import ENGINE_RUNNERS


def test_sanitiser_strips_keywords_gemini_rejects():
    dirty = {
        "type": "object",
        "additionalProperties": {"type": "number"},
        "properties": {
            "a": {"type": "string", "$ref": "#/defs/x"},
            "b": {"type": "array", "items": {"type": "object",
                                             "additionalProperties": True,
                                             "properties": {"c": {"type": "number"}}}},
        },
    }
    clean = llm._sanitise_schema(dirty)
    flat = repr(clean)
    for banned in ("additionalProperties", "$ref"):
        assert banned not in flat
    # everything legitimate survives
    assert clean["properties"]["a"]["type"] == "string"
    assert clean["properties"]["b"]["items"]["properties"]["c"]["type"] == "number"


def test_no_tool_schema_uses_a_keyword_gemini_rejects():
    """Guards the whole tool list, not just the one that used to break."""
    flat = repr(TOOLS)
    for banned in llm._SCHEMA_DROP:
        assert banned not in flat, f"{banned} would be rejected by Gemini"


def test_json_fallback_prompt_names_every_engine():
    """A hand-written prompt silently drops engines as the roster grows."""
    suffix = llm._json_router_suffix(TOOLS)
    for name in ENGINE_RUNNERS:
        assert name in suffix, f"{name} missing from the JSON fallback prompt"


def test_every_tool_becomes_a_gemini_function_declaration():
    tools = llm._gemini_tools(TOOLS)
    decls = tools[0].function_declarations
    assert {d.name for d in decls} == {t["name"] for t in TOOLS}
