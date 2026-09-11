# CTRL+ALT+DEFEAT — Tarteeb

**A multi-agent project-management copilot that lives in your team's chat.**

Runs in **Slack** and **Microsoft Teams** from the same agent core.

Hackathon entry for **Agents, Everywhere** (AI Tinkerers — Abu Dhabi),
Mohamed bin Zayed University of Artificial Intelligence, Masdar City —
12 September 2026.

> The challenge: *build an agent for a place people already work, talk, or
> live, then make it meaningfully more useful because of that context.*

The context here is the PM team's own channel — the same place they already
argue about schedules and budgets. Post a question, paste some numbers, or
drop a CSV, and a router wakes whichever of **ten named specialist agents**
apply. Deterministic engines run the actual PM math — critical path and
float, weighted decision matrix, earned value, NPV/ROI/payback, PERT,
schedule crashing, work-breakdown checks — while an Executive Orchestrator
hands back **one** consolidated brief: findings, risks, conflicts, what's
missing, and next-step options.

**The human always makes the final call.** The bot advises and logs; it
never decides.

---

## Architecture

```
 Slack (/pm · @mention · CSV)      Microsoft Teams (message · @mention · CSV)
        │                                    │
        └──────────────┬─────────────────────┘
                       ▼
   ┌─────────┐   LLM + tool use (Gemini or Anthropic, either can lead):
   │ Router  │   picks the specialist(s), extracts structured inputs,
   └─────────┘   or asks ONE clarifying question if data is missing
                       │
                       ▼
   ┌────────────────────────────────────────────────────────┐
   │  Ten specialist agents over deterministic engines        │
   │   cpm.py          Critical Path Analyst                  │
   │   compression.py  Schedule Recovery + Fast-Track Analyst │
   │   evm.py          Earned Value Analyst                   │
   │   finance.py      Business Case Analyst                  │
   │   pert.py         Estimation Analyst                     │
   │   estimating.py   Estimate Assurance Analyst             │
   │   wbs.py          Scope Architect + Baseline Guardian    │
   │   scoring.py      Options Analyst                        │
   └────────────────────────────────────────────────────────┘
                       │
                       ▼
   ┌────────────────────────────────────────────────────────┐
   │  channels/  one BriefView, two renderers                 │
   │   slack_blocks.py  -> Block Kit                          │
   │   teams_cards.py   -> Adaptive Card                      │
   └────────────────────────────────────────────────────────┘
        │
        ▼
   ┌──────────────┐   LLM: consolidates every specialist's output into
   │ Executive     │   ONE brief — summary, key findings, risks &
   │ Orchestrator  │   conflicts, missing info, recommended next step
   └──────────────┘
        │
        ▼
   Slack message with  Approve / Discuss / Reject  buttons
        │
        ▼
   agents/audit.py → audit_log/audit_trail.jsonl   (every step logged)
```

**Math is never done by the LLM.** The router turns messy human language
into structured JSON; every calculation runs in plain, unit-tested Python
in `engines/`. The numbers stay trustworthy even though the interface is
conversational.

Adding a fourth specialist (Risk, Legal, …) is one new engine file + one
new tool schema in `agents/tool_schemas.py` — the router and orchestrator
don't change.

### Resilience

`agents/llm.py` tries **Anthropic** (`claude-sonnet-5`) first and falls
back to **Google Gemini** if Anthropic errors or rate-limits. If *no*
provider is reachable, structured commands and CSV uploads still run
end-to-end and the brief falls back to a templated summary — a live demo
shouldn't die because of a rate limit.

---

## Three ways in (all in one place)

1. **Slash command** — `/pm we need to pick between three vendors on cost, quality and delivery time`
2. **@mention, conversational** — `@Tarteeb how's Project X tracking against budget?`
3. **File upload** — drop a `tasks.csv` / `scoring.csv` / `cost.csv` (see `demo/sample_data/`) into a channel the bot is in; it auto-detects the type

---

## Quick start (no Slack needed)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...          # optional; offline mode works without it

python demo/cli_demo.py all        # all three engines on sample data → one brief
python demo/cli_demo.py schedule   # critical path only
python demo/cli_demo.py scoring    # weighted scoring only
python demo/cli_demo.py cost       # EVM only
python demo/cli_demo.py chat "we're comparing three cloud vendors on cost and uptime"
python demo/cli_demo.py audit      # print the append-only audit trail
```

Run the tests:

```bash
python tests/test_cpm.py       # CPM on a hand-checkable network
python tests/test_scoring.py   # validated against a known weighted-scoring example (72/58/50/72)
python tests/test_evm.py       # EVM against hand-calculated CPI/SPI/EAC
python tests/test_parsers.py   # CSV → structured-input parsers
```

---

## Slack setup

Socket Mode — no public URL / ngrok needed. Full walkthrough in
[`SLACK_SETUP.md`](SLACK_SETUP.md). Short version:

```bash
cp .env.example .env      # fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_API_KEY
python slack_app/app.py
```

---

## Repo layout

```
engines/     deterministic PM math (CPM, weighted scoring, EVM)
agents/      router, executive orchestrator, LLM provider layer, prompts,
             tool schemas, audit log, CSV parsers
slack_app/   Slack Bolt app (Socket Mode), handlers, Block Kit formatting
demo/        CLI demo + sample CSVs
tests/       unit tests for every engine and parser
audit_log/   audit_trail.jsonl written at runtime (gitignored)
```

---

## What was built during the hackathon

_Fill this in as you go on build day — judges specifically ask which parts
were built during the event. Keep the running log in
[`BUILD_DAY.md`](BUILD_DAY.md)._

## Team

CTRL+ALT+DEFEAT — Rama Abdallah
