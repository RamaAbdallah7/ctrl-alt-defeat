"""Both chat surfaces must render the same brief, and neither may leak into the other."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json

from channels import brief as brief_model
from channels import slack_blocks, teams_cards
from channels.brief import DECISIONS

RESULT = {
    "status": "ok",
    "event_id": "evt-1",
    "provider": "gemini",
    "brief": "SUMMARY: the project is behind.\nRECOMMENDED NEXT STEP: decide.",
    "specialist_outputs": {
        "cost": {
            "input": {}, "ok": True,
            "agent": "Earned Value Analyst", "agent_role": "Cost-control specialist",
            "result": {"pv": 42000, "ev": 35000, "ac": 41000, "bac": 120000,
                       "cpi": 0.8537, "spi": 0.8333, "eac": 140571.43, "vac": -20571.43,
                       "tcpi_bac": 1.0759, "estimated_duration": 14.4,
                       "planned_duration": 12, "flags": []},
        },
    },
}

NEEDS_INFO = {"status": "needs_info", "question": "What are the task durations?"}


def test_one_view_feeds_both_surfaces():
    view = brief_model.from_result(RESULT, requester="U123")
    assert view.status == "ok"
    assert view.wants_decision
    assert [f.agent for f in view.findings] == ["Earned Value Analyst"]

    blocks = slack_blocks.render(view)
    card = teams_cards.render(view)

    # the brief body reaches both
    assert any("behind" in json.dumps(b) for b in blocks)
    assert "behind" in json.dumps(card)

    # both offer the same three decisions
    slack_actions = [e for b in blocks if b["type"] == "actions" for e in b["elements"]]
    assert [a["action_id"] for a in slack_actions] == [d["id"] for d in DECISIONS]
    assert [a["data"]["action"] for a in card["actions"]] == [d["id"] for d in DECISIONS]

    # and both carry the event id, so a decision can be tied back to its brief
    assert all(a["value"] == "evt-1" for a in slack_actions)
    assert all(a["data"]["event_id"] == "evt-1" for a in card["actions"])


def test_neither_surface_leaks_into_the_other():
    view = brief_model.from_result(RESULT, requester="U123")
    card = json.dumps(teams_cards.render(view))
    blocks = json.dumps(slack_blocks.render(view))

    # Slack's mrkdwn user syntax and Block Kit types must not reach Teams
    for slackism in ("<@U123>", "mrkdwn", "block_id", "action_id"):
        assert slackism not in card, f"{slackism} leaked into the Adaptive Card"
    # ...and Adaptive Card vocabulary must not reach Slack
    for teamsism in ("Action.Submit", "AdaptiveCard", "TextBlock"):
        assert teamsism not in blocks, f"{teamsism} leaked into Block Kit"


def test_adaptive_card_is_well_formed():
    card = teams_cards.render(brief_model.from_result(RESULT, requester="U1"))
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.4"
    assert card["body"] and all("type" in b for b in card["body"])
    styles = {a.get("style") for a in card["actions"]}
    assert styles == {"positive", "default", "destructive"}


def test_needs_info_asks_on_both_and_offers_no_decision():
    view = brief_model.from_result(NEEDS_INFO, requester="U1")
    assert not view.wants_decision
    assert "durations" in json.dumps(slack_blocks.render(view))
    card = teams_cards.render(view)
    assert "durations" in json.dumps(card)
    assert "actions" not in card, "a question must not carry Approve/Reject"


def test_offline_brief_is_not_printed_twice():
    """The templated brief already names each specialist; don't repeat them."""
    offline = dict(RESULT, brief="1 specialist reported.\nEarned Value Analyst: CPI is 0.85.")
    view = brief_model.from_result(offline, requester="U1")
    assert view.findings == []


def test_slack_shim_still_works():
    from slack_app.formatting import brief_blocks, error_blocks
    assert brief_blocks(RESULT, "U1")[0]["type"] == "header"
    assert "warning" in json.dumps(error_blocks("boom"))
