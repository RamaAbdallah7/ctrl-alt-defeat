"""
Tarteeb orchestrator.

Architecture (mirrors the Tarteeb poster, scoped to project management):

  user input (chat / slash command / file)
        |
        v
  [Router]  -- LLM + tool-use --> decides which specialist engine(s)
        |       apply and extracts structured inputs for them (or asks
        |       one clarifying question if the data isn't there)
        v
  [Specialist engines] -- deterministic Python, not LLM math:
        - Schedule / Critical Path (engines/cpm.py)
        - Weighted Scoring (engines/scoring.py)
        - Cost / EVM (engines/evm.py)
        |
        v
  [Executive Orchestrator] -- LLM --> consolidates every specialist's
        output into one brief: summary, key findings, risks & conflicts,
        missing information, recommended next step for the human.
        |
        v
  Human decision (Slack buttons / reply) -- the human always decides.
        |
        v
  [Audit trail] -- every step logged to audit_log/audit_trail.jsonl

The LLM calls go through agents/llm.py, which tries Anthropic first and
Google Gemini as a fallback. If NO provider is reachable, the router falls
back to routing off explicit structured input only (no free-text NLU) and
the orchestrator falls back to a templated (non-LLM) brief. This keeps the
demo alive even without API access -- structured/file-upload flows still
work end to end.
"""

from __future__ import annotations

import json
from typing import Optional

from engines.cpm import compute_critical_path, CPMError
from engines.scoring import compute_weighted_scores, ScoringError
from engines.evm import compute_evm, EVMError
from engines.finance import compute_financials, FinanceError
from engines.pert import compute_pert, PERTError
from engines.compression import crash_schedule, fast_track_candidates, CompressionError
from engines.wbs import analyze_wbs, detect_scope_creep, WBSError
from engines.estimating import classify_estimate, EstimateError
from agents.prompts import ROUTER_SYSTEM_PROMPT, ORCHESTRATOR_SYSTEM_PROMPT
from agents.tool_schemas import TOOLS
from agents.audit import log_event
from agents.specialists import BY_KEY, specialist_for_tool, report as specialist_report
from agents import llm


ENGINE_RUNNERS = {
    "run_schedule_analysis": lambda inp: ("schedule", _safe(compute_critical_path, inp["tasks"])),
    "run_scoring_analysis": lambda inp: ("scoring", _safe(compute_weighted_scores, inp["criteria"], inp["options"])),
    "run_cost_analysis": lambda inp: ("cost", _safe(
        compute_evm, inp["pv"], inp["ev"], inp["ac"], inp["bac"], inp.get("planned_duration"))),
    "run_financial_analysis": lambda inp: ("financial", _safe(
        compute_financials, inp["costs"], inp["benefits"], inp["discount_rate"],
        inp.get("rounding", "exact"), inp.get("start_year", 0))),
    "run_pert_analysis": lambda inp: ("pert", _safe(
        compute_pert, inp["activities"], inp.get("target"), inp.get("unit", "days"))),
    "run_crash_analysis": lambda inp: ("crashing", _safe(
        crash_schedule, inp["tasks"], inp.get("target_duration"), inp.get("max_spend"))),
    "run_fast_track_analysis": lambda inp: ("fast_track", _safe(
        fast_track_candidates, inp["tasks"], inp.get("overlap_fraction", 0.5))),
    "run_wbs_analysis": lambda inp: ("wbs", _safe(
        analyze_wbs, inp["items"], inp.get("value_label", "cost"))),
    "run_scope_creep_analysis": lambda inp: ("scope_creep", _safe(
        detect_scope_creep, inp["baseline"], inp["current"], inp.get("value_label", "cost"))),
    "run_estimate_check": lambda inp: ("estimate", _safe(
        classify_estimate, inp["estimate"], inp["estimate_type"], inp.get("budget"))),
}


def _safe(fn, *args):
    try:
        return {"ok": True, "result": fn(*args)}
    except (CPMError, ScoringError, EVMError, FinanceError, PERTError,
            CompressionError, WBSError, EstimateError) as e:
        return {"ok": False, "error": str(e)}
    except (KeyError, TypeError, ValueError) as e:
        # a provider handed us malformed structured input
        return {"ok": False, "error": f"Could not read the extracted inputs: {e}"}


def route_request(user_text: str, structured_hint: Optional[dict] = None) -> dict:
    """
    Returns {"tool_calls": [{"name":..., "input":...}, ...],
             "clarifying_question": str|None,
             "provider": str}

    structured_hint: if the caller already knows the shape of the data (e.g.
    a parsed CSV upload), pass it directly and we skip the LLM router call
    entirely -- deterministic and free.
    """
    if structured_hint is not None:
        return {"tool_calls": [structured_hint], "clarifying_question": None, "provider": "structured"}

    routed = llm.route_with_tools(ROUTER_SYSTEM_PROMPT, TOOLS, user_text)
    if routed is not None:
        # a provider answered but extracted nothing actionable -> ask rather than
        # return an empty brief
        if not routed.get("tool_calls") and not routed.get("clarifying_question"):
            routed["clarifying_question"] = (
                "I couldn't find enough to work with. Tell me the tasks and "
                "durations, the options and criteria, or the PV/EV/AC/BAC figures "
                "you'd like analyzed."
            )
        return routed

    return {
        "tool_calls": [],
        "clarifying_question": (
            "I can't reach a language model right now, so I can only analyze "
            "structured input directly -- send me clear figures, or upload a "
            "tasks / scoring / cost CSV (see demo/sample_data for the format)."
        ),
        "provider": "offline",
    }


def run_specialists(tool_calls: list) -> dict:
    """Executes each requested engine and returns {domain: {ok, result|error}}."""
    outputs = {}
    for call in tool_calls:
        name = call["name"]
        runner = ENGINE_RUNNERS.get(name)
        if runner is None:
            continue
        domain, output = runner(call.get("input", {}))
        agent = specialist_for_tool(name)
        outputs[domain] = {
            "input": call.get("input", {}),
            "agent": agent.name if agent else domain,
            "agent_role": agent.role if agent else None,
            "agent_mandate": agent.mandate if agent else None,
            **output,
        }
    return outputs


def _templated_brief(specialist_outputs: dict) -> str:
    """
    No-LLM fallback brief. Each named specialist reports its own finding in
    its own voice (agents/specialists.py), so the offline path reads like the
    same team as the LLM path rather than like a different product.
    """
    lines = []
    for domain, out in specialist_outputs.items():
        agent = BY_KEY.get(domain)
        label = out.get("agent") or (agent.name if agent else domain)
        if not out["ok"]:
            lines.append(f"{label}: could not report -- {out['error']}")
            continue
        finding = specialist_report(domain, out["result"])
        if finding:
            lines.append(f"{label}: {finding}")

    if not lines:
        return "No specialist produced usable output."

    reported = len(lines)
    header = (f"{reported} specialist{'s' if reported != 1 else ''} reported.")
    lines.insert(0, header)
    lines.append(
        "\nRECOMMENDED NEXT STEP: review the figures above and choose one of "
        "proceed / request more data / escalate. A human decision is required "
        "either way -- this brief was generated in offline mode."
    )
    return "\n".join(lines)


def write_executive_brief(user_text: str, specialist_outputs: dict) -> str:
    if not specialist_outputs:
        return _templated_brief(specialist_outputs)

    payload = json.dumps(
        {domain: {"agent": out.get("agent"), "input": out["input"], "ok": out["ok"],
                  "result": out.get("result"), "error": out.get("error")}
         for domain, out in specialist_outputs.items()},
        default=str,
    )
    prompt = (
        f"Original request:\n{user_text}\n\n"
        f"Specialist agent outputs (JSON):\n{payload}"
    )
    brief = llm.complete_text(ORCHESTRATOR_SYSTEM_PROMPT, prompt, max_tokens=700)
    return brief if brief else _templated_brief(specialist_outputs)


def handle_request(user_text: str, source: str, requester: str, structured_hint: Optional[dict] = None) -> dict:
    """
    Full pipeline: route -> run specialists -> write executive brief -> audit log.
    Returns a dict ready for formatting into a Slack message (or CLI output).
    """
    routing = route_request(user_text, structured_hint)

    if routing["clarifying_question"] and not routing["tool_calls"]:
        event_id = log_event(
            source=source, requester=requester, user_text=user_text,
            provider=routing.get("provider"),
            outcome="clarifying_question", clarifying_question=routing["clarifying_question"],
        )
        return {"event_id": event_id, "status": "needs_info", "question": routing["clarifying_question"]}

    specialist_outputs = run_specialists(routing["tool_calls"])
    brief = write_executive_brief(user_text, specialist_outputs)

    event_id = log_event(
        source=source, requester=requester, user_text=user_text,
        provider=routing.get("provider"),
        tool_calls=routing["tool_calls"], specialist_outputs=specialist_outputs,
        brief=brief, outcome="brief_generated",
    )

    return {
        "event_id": event_id,
        "status": "ok",
        "provider": routing.get("provider"),
        "specialist_outputs": specialist_outputs,
        "brief": brief,
    }
