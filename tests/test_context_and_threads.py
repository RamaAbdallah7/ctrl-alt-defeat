"""
Environment-dependent reasoning: the bot reads the channel, resolves
references, and treats a thread reply as a follow-up rather than a new
question.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from agents.context import ChannelContext, ContextMessage, from_slack_history
from agents.thread_state import ThreadStore, apply_delta, describe_changes
from agents import orchestrator

# Slack returns newest first; the triggering question is therefore first.
HISTORY = [
    {"user": "U_KH", "text": "@Tarteeb how are we doing on those numbers?", "ts": "1700000005"},
    {"bot_id": "B_TARTEEB", "text": "an earlier brief I posted", "ts": "1700000004"},
    {"user": "U_SARA", "text": "earned value is about 35,000 against a planned 42,000", "ts": "1700000003"},
    {"user": "U_AHMED", "text": "budget is 120,000, we've spent 41,000 so far", "ts": "1700000002"},
    {"user": "U_SARA", "text": "vendor cost sheet attached", "ts": "1700000001",
     "files": [{"name": "vendor_costs.csv", "id": "F1"}]},
]
NAMES = {"U_KH": "Khadeja", "U_SARA": "Sara", "U_AHMED": "Ahmed"}


# ------------------------------------------------------------------- context

def test_history_is_ordered_oldest_first_so_later_supersedes_earlier():
    ctx = from_slack_history(HISTORY, names=NAMES)
    rendered = ctx.render()
    assert rendered.index("vendor cost sheet") < rendered.index("how are we doing")


def test_the_bots_own_messages_are_excluded():
    """Otherwise it reasons about its own output as if it were input."""
    ctx = from_slack_history(HISTORY, names=NAMES)
    assert "an earlier brief I posted" not in ctx.render()
    assert "Tarteeb" not in ctx.participants


def test_user_ids_are_resolved_to_names():
    ctx = from_slack_history(HISTORY, names=NAMES)
    assert set(ctx.participants) == {"Khadeja", "Sara", "Ahmed"}
    assert "U_SARA" not in ctx.render()


def test_a_reference_to_a_posted_file_resolves():
    """'the vendor cost sheet Sara posted' must find an actual file."""
    ctx = from_slack_history(HISTORY, names=NAMES)
    f = ctx.latest_file("vendor")
    assert f["name"] == "vendor_costs.csv" and f["author"] == "Sara"


def test_figures_stated_in_the_channel_are_extracted_with_attribution():
    ctx = from_slack_history(HISTORY, names=NAMES)
    figures = ctx.figures()
    values = {f["value"].replace("$", "").strip() for f in figures}
    assert {"35,000", "42,000", "120,000", "41,000"} <= values
    assert any(f["author"] == "Ahmed" and "120,000" in f["value"] for f in figures)


def test_prompt_block_tells_the_router_not_to_invent():
    ctx = from_slack_history(HISTORY, names=NAMES)
    block = ctx.as_prompt_block()
    assert "never" in block.lower() and "invent" in block.lower()
    assert "vendor_costs.csv" in block


def test_empty_context_produces_no_prompt_block():
    assert ChannelContext().as_prompt_block() == ""
    assert ChannelContext(messages=[ContextMessage("bot", "hi", "1", is_bot=True)]).is_empty()


def test_long_history_is_trimmed_not_dropped():
    msgs = [ContextMessage("A", "x" * 300, str(i)) for i in range(60)]
    rendered = ChannelContext(messages=msgs).render(max_messages=30, max_chars=2000)
    assert len(rendered) <= 2100 and "trimmed" in rendered


# -------------------------------------------------------------------- deltas

PRIOR = [
    {"name": "run_cost_analysis",
     "input": {"pv": 42000, "ev": 35000, "ac": 41000, "bac": 120000}},
    {"name": "run_schedule_analysis",
     "input": {"tasks": [
         {"id": "A", "name": "A", "duration": 1, "predecessors": []},
         {"id": "E", "name": "Backend", "duration": 5, "predecessors": ["A"]},
         {"id": "J", "name": "Go-live", "duration": 3, "predecessors": ["E"]}]}},
]


@pytest.mark.parametrize("text,expect", [
    ("what if we cut the timeline by 3 days", "target duration"),
    ("what if the vendor slips 2 weeks", "slip of 14"),
    ("what if task E takes 8 days", "E duration 5 -> 8"),
    ("what if AC is 55,000", "AC 41,000 -> 55,000"),
])
def test_follow_ups_are_applied_as_deltas(text, expect):
    _, changes = apply_delta(PRIOR, text)
    assert changes and expect in describe_changes(changes)


def test_an_unrecognised_follow_up_changes_nothing():
    """Guessing is worse than asking -- the caller falls back to a full route."""
    calls, changes = apply_delta(PRIOR, "hmm, interesting")
    assert changes == []
    assert calls == PRIOR


def test_a_delta_does_not_mutate_the_prior_state():
    before = PRIOR[1]["input"]["tasks"][1]["duration"]
    apply_delta(PRIOR, "what if task E takes 9 days")
    assert PRIOR[1]["input"]["tasks"][1]["duration"] == before


# -------------------------------------------------------------- thread store

def test_thread_state_round_trips():
    s = ThreadStore(":memory:")
    s.save("C1/1.1", channel="C1", tool_calls=PRIOR, brief="b", event_id="e", requester="U")
    got = s.load("C1/1.1")
    assert got["tool_calls"] == PRIOR and got["requester"] == "U" and not got["locked"]


def test_partial_save_does_not_wipe_other_fields():
    s = ThreadStore(":memory:")
    s.save("C1/1.1", channel="C1", tool_calls=PRIOR, brief="first")
    s.save("C1/1.1", brief="second")
    got = s.load("C1/1.1")
    assert got["brief"] == "second" and got["tool_calls"] == PRIOR


def test_locking_a_thread_is_visible():
    s = ThreadStore(":memory:")
    s.save("C1/1.1", tool_calls=PRIOR)
    assert not s.is_locked("C1/1.1")
    s.lock("C1/1.1")
    assert s.is_locked("C1/1.1")


def test_re_uploading_a_changed_file_returns_the_previous_version():
    s = ThreadStore(":memory:")
    assert s.remember_file("C1/1", "tasks.csv", "d1", {"v": 1}) is None
    prev = s.remember_file("C1/1", "tasks.csv", "d2", {"v": 2})
    assert prev == {"v": 1}, "a re-upload must expose what it replaced, for diffing"


def test_re_uploading_an_identical_file_reports_no_previous():
    s = ThreadStore(":memory:")
    s.remember_file("C1/1", "tasks.csv", "same", {"v": 1})
    assert s.remember_file("C1/1", "tasks.csv", "same", {"v": 1}) is None


# ------------------------------------------------------- orchestrator wiring

def test_handle_request_prefers_a_delta_over_re_routing(monkeypatch):
    """A follow-up must not go back to the LLM when it is a understood delta."""
    called = {"route": 0}
    monkeypatch.setattr(orchestrator, "route_request",
                        lambda *a, **k: called.__setitem__("route", called["route"] + 1) or
                        {"tool_calls": [], "clarifying_question": "?", "provider": "x"})
    out = orchestrator.handle_request("what if AC is 55,000", source="t", requester="U",
                                      prior_calls=PRIOR)
    assert called["route"] == 0, "an understood delta must not re-route"
    assert out["provider"] == "thread-delta"
    assert "AC 41,000 -> 55,000" in out["brief"]


def test_handle_request_falls_back_to_routing_when_the_delta_is_not_understood(monkeypatch):
    monkeypatch.setattr(orchestrator, "route_request",
                        lambda *a, **k: {"tool_calls": [], "clarifying_question": "say more",
                                         "provider": "stub"})
    out = orchestrator.handle_request("hmm", source="t", requester="U", prior_calls=PRIOR)
    assert out["status"] == "needs_info"


def test_context_is_passed_into_the_router(monkeypatch):
    seen = {}
    def fake_route(system, tools, prompt):
        seen["prompt"] = prompt
        return {"tool_calls": [], "clarifying_question": "q", "provider": "stub"}
    monkeypatch.setattr(orchestrator.llm, "route_with_tools", fake_route)
    ctx = from_slack_history(HISTORY, names=NAMES)
    orchestrator.route_request("how are we doing on those numbers?", context=ctx)
    assert "RECENT CHANNEL CONTEXT" in seen["prompt"]
    assert "120,000" in seen["prompt"], "the channel's figures must reach the router"
    assert "THE REQUEST:" in seen["prompt"]
