#!/usr/bin/env python3
"""
Live provider check for Tarteeb.

Runs a real request through the real router against whichever LLM provider
is configured, and prints which specialists it woke and what they reported.
This is the one thing the offline demo cannot prove.

  python demo/live_check.py                 # run the built-in free-text request
  python demo/live_check.py "your question" # route your own

Reads credentials from .env (gitignored). Nothing is printed that would
reveal a key.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents import llm
from agents.orchestrator import handle_request
from agents.specialists import BY_KEY

DEFAULT = (
    "We're comparing three vendors for the registration project. Vendor A costs 80, "
    "quality 90, delivery 60. Vendor B costs 95, quality 70, delivery 85. Vendor C "
    "costs 60, quality 95, delivery 90. Weight cost 40%, quality 35%, delivery 25%. "
    "Also, we've spent 41,000 of a 120,000 budget and earned 35,000 of value against "
    "a planned 42,000 on a 12-month plan -- how are we doing?"
)


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else DEFAULT

    def mask(name):
        v = os.environ.get(name) or ""
        return f"set ({len(v)} chars)" if v.strip() else "not set"

    print("=" * 70)
    print("PROVIDER STATUS")
    print("=" * 70)
    print(f"  GEMINI_API_KEY      {mask('GEMINI_API_KEY')}")
    print(f"  ANTHROPIC_API_KEY   {mask('ANTHROPIC_API_KEY')}")
    print(f"  provider order      {os.environ.get('TARTEEB_LLM_PROVIDERS', 'anthropic,gemini')}")
    print(f"  gemini model        {llm.GEMINI_MODEL}")

    live = llm.providers_available()
    print(f"  reachable           {', '.join(live) if live else 'NONE -- offline mode only'}")
    if not live:
        print("\n  Put your key in .env as GEMINI_API_KEY=... and run this again.")
        return 1

    print()
    print("=" * 70)
    print("REQUEST")
    print("=" * 70)
    print(f"  {text[:200]}{'...' if len(text) > 200 else ''}")

    result = handle_request(text, source="live_check", requester="cli")

    print()
    print("=" * 70)
    print("ROUTING")
    print("=" * 70)
    print(f"  provider used       {result.get('provider')}")
    if result["status"] == "needs_info":
        print(f"  asked a question    {result['question']}")
        print("\n  The router ran, but decided it needed more data. That is a valid outcome.")
        return 0

    outs = result["specialist_outputs"]
    print(f"  specialists woken   {len(outs)} of 10")
    for k, o in outs.items():
        agent = BY_KEY.get(k)
        status = "ok" if o["ok"] else f"FAILED: {o.get('error')}"
        print(f"    - {(agent.name if agent else k):<28} {status}")

    print()
    print("=" * 70)
    print("EXECUTIVE BRIEF (written by the live model)")
    print("=" * 70)
    print(result["brief"])
    print()
    print(f"audit event: {result['event_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
