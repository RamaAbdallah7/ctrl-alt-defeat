#!/usr/bin/env python3
"""
Local demo of the full Tarteeb pipeline -- no Slack app, no credentials
required for the deterministic parts. Great for recording the hackathon
demo video's "here's the engine working" beat, or for testing before the
Slack app is wired up.

Usage:
    python3 demo/cli_demo.py schedule   # CPM on sample_data/tasks.csv
    python3 demo/cli_demo.py scoring    # weighted scoring on sample_data/scoring.csv
    python3 demo/cli_demo.py cost       # EVM on sample_data/cost.csv
    python3 demo/cli_demo.py all        # run all three and show one consolidated brief
    python3 demo/cli_demo.py chat "we need to pick between three vendors..."
        # free-text conversational path (needs an LLM provider: Anthropic or Gemini)
    python3 demo/cli_demo.py audit      # print the append-only audit trail
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.orchestrator import handle_request, run_specialists, write_executive_brief
from agents.parsers import parse_tasks_csv, parse_scoring_csv, parse_cost_csv
from agents.audit import read_recent

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_data")


def _load(name):
    with open(os.path.join(SAMPLE_DIR, name)) as f:
        return f.read()


def cmd_schedule():
    hint = parse_tasks_csv(_load("tasks.csv"))
    result = handle_request("Analyze this project schedule.", source="cli", requester="demo", structured_hint=hint)
    _print(result)


def cmd_scoring():
    hint = parse_scoring_csv(_load("scoring.csv"))
    result = handle_request("Which option should we pick?", source="cli", requester="demo", structured_hint=hint)
    _print(result)


def cmd_cost():
    hint = parse_cost_csv(_load("cost.csv"))
    result = handle_request("How is the project tracking against budget?", source="cli", requester="demo", structured_hint=hint)
    _print(result)


def cmd_all():
    """Run all three engines together and produce ONE consolidated executive
    brief -- this is the 'multi-agent, one place' beat of the demo."""
    tool_calls = [
        parse_tasks_csv(_load("tasks.csv")),
        parse_scoring_csv(_load("scoring.csv")),
        parse_cost_csv(_load("cost.csv")),
    ]
    specialist_outputs = run_specialists(tool_calls)
    brief = write_executive_brief(
        "Give me the full picture on Project X: schedule, vendor choice, and budget health.",
        specialist_outputs,
    )
    print("=" * 70)
    print("SPECIALIST OUTPUTS")
    print("=" * 70)
    print(json.dumps(specialist_outputs, indent=2, default=str))
    print()
    print("=" * 70)
    print("EXECUTIVE BRIEF (Tarteeb orchestrator)")
    print("=" * 70)
    print(brief)


def cmd_chat(text):
    result = handle_request(text, source="cli", requester="demo")
    _print(result)


def cmd_audit():
    """Show the append-only audit trail -- the 'every step is traceable' beat."""
    events = read_recent(20)
    if not events:
        print("No audit events yet. Run `schedule`, `scoring`, `cost`, `all`, or `chat` first.")
        return
    for e in events:
        print(f"{e.get('ts', '?')}  {e.get('event_id', '?')}  "
              f"{e.get('source', '?')}/{e.get('provider', '-')}  -> {e.get('outcome', '?')}")
        if e.get("clarifying_question"):
            print(f"    Q: {e['clarifying_question']}")
        if e.get("decision"):
            print(f"    decision: {e['decision']} (for {e.get('decision_for_event')})")


def _print(result):
    print("=" * 70)
    print(json.dumps(result, indent=2, default=str))
    print("=" * 70)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "schedule":
        cmd_schedule()
    elif cmd == "scoring":
        cmd_scoring()
    elif cmd == "cost":
        cmd_cost()
    elif cmd == "all":
        cmd_all()
    elif cmd == "chat":
        cmd_chat(" ".join(sys.argv[2:]) or "Tell me about project status.")
    elif cmd == "audit":
        cmd_audit()
    else:
        print(__doc__)
        sys.exit(1)
