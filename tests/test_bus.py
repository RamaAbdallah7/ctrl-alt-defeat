"""The distributed-systems properties: ordering, dedupe, concurrency, quorum."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from bus.bus import EventBus
from bus.events import (Event, LamportClock, TASK_CLOSE_PROPOSED, TASK_CLOSED,
                        TASK_CLOSE_BLOCKED, ESCALATION_RAISED, REVIEW_ENDORSED,
                        REVIEW_VETOED, HUMAN_DECISION)
from bus.store import EventStore, ConcurrencyError
from agents.negotiation import wire


def types(bus):
    return [e.type for e in bus.store.all()]


# ------------------------------------------------------------------ ordering

def test_out_of_order_events_are_buffered_until_the_gap_fills():
    """Deliver seq 3 before seq 2 and a veto can land after the task closed."""
    bus = EventBus()
    seen = []
    bus.subscribe("watcher", lambda e: seen.append(e.seq) or [])

    store = bus.store
    s = "task/X"
    e1 = Event(type="a", stream=s); e2 = Event(type="b", stream=s); e3 = Event(type="c", stream=s)
    store.append(e1); store.append(e2); store.append(e3)

    bus._dispatch(e3)          # arrives first
    assert seen == [], "seq 3 must not be delivered before seq 1 and 2"
    bus._dispatch(e1)
    assert seen == [1]
    bus._dispatch(e2)
    assert seen == [1, 2, 3], "the buffered event must follow once the gap closes"


def test_duplicate_delivery_is_collapsed():
    bus = EventBus()
    seen = []
    bus.subscribe("watcher", lambda e: seen.append(e.id) or [])
    e = bus.store.append(Event(type="a", stream="s"))
    bus._dispatch(e); bus._dispatch(e); bus._dispatch(e)
    assert len(seen) == 1, "at-least-once delivery must have exactly-once effect"


def test_idempotency_key_prevents_a_second_append():
    store = EventStore()
    a = store.append(Event(type="x", stream="s", idempotency_key="k1"))
    b = store.append(Event(type="x", stream="s", idempotency_key="k1"))
    assert a is b and store.version("s") == 1


def test_lamport_clock_orders_across_streams():
    c = LamportClock()
    assert c.tick() == 1
    assert c.observe(7) == 8        # take the max and move past it
    assert c.tick() == 9


# --------------------------------------------------------------- concurrency

def test_two_humans_answering_at_once_resolves_to_one_winner():
    store = EventStore()
    v = store.version("dec/1")
    store.append(Event(type=HUMAN_DECISION, stream="dec/1", actor="khadeja"), expected_version=v)
    with pytest.raises(ConcurrencyError) as exc:
        store.append(Event(type=HUMAN_DECISION, stream="dec/1", actor="rama"), expected_version=v)
    assert exc.value.winner.actor == "khadeja", "the loser must be told who won"
    assert store.version("dec/1") == 1


def test_appends_without_expected_version_do_not_race():
    store = EventStore()
    store.append(Event(type="fact", stream="s"))
    store.append(Event(type="fact", stream="s"))
    assert store.version("s") == 2


# ---------------------------------------------------------------- negotiation

def test_open_high_risk_vetoes_a_closure_and_escalates():
    bus = EventBus()
    wire(bus, risks_by_task={"T1": [{"name": "SQLi", "severity": 20, "status": "open"}]})
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T1",
                      actor="Scheduler", payload={"task_id": "T1", "reason": "done"}))
    t = types(bus)
    assert REVIEW_VETOED in t and ESCALATION_RAISED in t
    assert TASK_CLOSED not in t, "a vetoed task must never auto-close"


def test_clean_task_closes_without_a_human():
    bus = EventBus()
    wire(bus, risks_by_task={"T2": [{"name": "typo", "severity": 2, "status": "open"}]})
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T2",
                      actor="Scheduler", payload={"task_id": "T2", "reason": "done"}))
    assert TASK_CLOSED in types(bus)
    assert ESCALATION_RAISED not in types(bus)


def test_mitigated_risk_does_not_veto():
    bus = EventBus()
    wire(bus, risks_by_task={"T3": [{"name": "XSS", "severity": 25, "status": "mitigated"}]})
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T3",
                      actor="Scheduler", payload={"task_id": "T3", "reason": "done"}))
    assert TASK_CLOSED in types(bus)


def test_a_silent_reviewer_blocks_rather_than_defaults_to_yes():
    """The rule most systems get wrong: no answer is not consent."""
    bus = EventBus()
    wire(bus, risks_by_task={"T4": []}, reviewers=("Risk", "Legal"))   # Legal never subscribes
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T4",
                      actor="Scheduler", payload={"task_id": "T4", "reason": "done"}))
    t = types(bus)
    assert REVIEW_ENDORSED in t
    assert TASK_CLOSED not in t, "quorum was not met, so nothing may close"


def test_human_override_closes_and_records_who_and_why():
    bus = EventBus()
    wire(bus, risks_by_task={"T5": [{"name": "RCE", "severity": 25, "status": "open"}]})
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T5",
                      actor="Scheduler", payload={"task_id": "T5", "reason": "done"}))
    bus.publish(Event(type=HUMAN_DECISION, stream="task/T5", actor="Khadeja",
                      payload={"task_id": "T5", "decision": "override", "reason": "accepted for v1"}))
    closed = [e for e in bus.store.all() if e.type == TASK_CLOSED][0]
    assert closed.payload["overridden_by"] == "Khadeja"
    assert closed.payload["reason"] == "accepted for v1"


def test_human_upholding_the_veto_leaves_the_task_open():
    bus = EventBus()
    wire(bus, risks_by_task={"T6": [{"name": "RCE", "severity": 25, "status": "open"}]})
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T6",
                      actor="Scheduler", payload={"task_id": "T6", "reason": "done"}))
    bus.publish(Event(type=HUMAN_DECISION, stream="task/T6", actor="Khadeja",
                      payload={"task_id": "T6", "decision": "uphold", "reason": "fix it first"}))
    t = types(bus)
    assert TASK_CLOSE_BLOCKED in t and TASK_CLOSED not in t


# ----------------------------------------------------------------- resilience

def test_a_throwing_agent_is_dead_lettered_not_fatal():
    bus = EventBus()
    def broken(_e):
        raise RuntimeError("agent crashed")
    bus.subscribe("broken", broken)
    ok = []
    bus.subscribe("healthy", lambda e: ok.append(e.type) or [])
    bus.publish(Event(type="a", stream="s"))
    assert bus.dead_letters and bus.dead_letters[0]["subscriber"] == "broken"
    assert ok == ["a"], "one broken agent must not stop the others"


def test_causation_and_correlation_link_the_chain():
    bus = EventBus()
    wire(bus, risks_by_task={"T7": [{"name": "RCE", "severity": 25, "status": "open"}]})
    root = bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T7",
                             actor="Scheduler", payload={"task_id": "T7", "reason": "done"}))
    veto = [e for e in bus.store.all() if e.type == REVIEW_VETOED][0]
    esc = [e for e in bus.store.all() if e.type == ESCALATION_RAISED][0]
    assert veto.causation_id == root.id
    assert esc.causation_id == veto.id
    assert len(bus.store.by_correlation(root.id)) >= 3


def test_event_log_is_hash_chained_and_verifiable():
    bus = EventBus()
    wire(bus, risks_by_task={"T8": []})
    bus.publish(Event(type=TASK_CLOSE_PROPOSED, stream="task/T8",
                      actor="Scheduler", payload={"task_id": "T8", "reason": "done"}))
    assert bus.store.verify()["ok"]
    bus.store.all()[1].payload["task_id"] = "T-other"     # tamper
    v = bus.store.verify()
    assert not v["ok"] and v["broken_at"] == 2


def test_a_subscriber_that_filters_types_keeps_receiving_the_stream():
    """
    Regression: the ordering cursor used to advance only over events the
    subscriber wanted, so every filtered-out event left a permanent gap and
    the subscriber stopped receiving that stream for good.
    """
    bus = EventBus()
    got = []
    bus.subscribe("picky", lambda e: got.append(e.type) or [], types=["wanted"])
    bus.publish(Event(type="wanted", stream="s"))
    bus.publish(Event(type="ignored", stream="s"))
    bus.publish(Event(type="wanted", stream="s"))
    assert got == ["wanted", "wanted"], "the event after a filtered one must still arrive"
