# Build day runbook — Sat 12 Sep 2026

Build window: **11:15–15:30** (4h15m). Submissions **15:30–16:00**.
Optional local demos **16:00–16:45** (not judged).

## Eligibility — read first

The rules: *"the project being submitted and its core functionality must be
built during the event… Teams should be prepared to explain which parts of
their project were created during the hackathon."* Templates, reusable
components, libraries, prompts, and starter code are explicitly allowed.

**Treat this repo's pre-day contents as building blocks, and build the core
live.** Concretely, on build day you should actually:

- wire the Router + Executive Orchestrator (`agents/orchestrator.py`) —
  rework the prompts and the routing/consolidation logic live, don't just
  run what's here
- build the Slack integration end-to-end against a live workspace
- record the demo

Keep `## What was built during the hackathon` in `README.md` updated as you
go, and keep your commits inside the build window. Log timestamps below.

### Pre-day building blocks (allowed to reuse)

| Piece | State coming in |
|---|---|
| `engines/cpm.py`, `scoring.py`, `evm.py` | deterministic PM math, unit-tested against known-correct reference numbers from ITE-401 coursework (reference values only, no course code) |
| `agents/parsers.py` | CSV → structured-input parsers |
| `agents/llm.py` | Anthropic→Gemini provider fallback layer |
| `agents/audit.py` | append-only JSONL audit trail |
| `slack_app/*` | Bolt Socket-Mode skeleton — **never run against a live workspace yet** |
| `tests/*`, `demo/*` | unit tests, offline CLI demo, sample CSVs |

### Built live on build day (fill in)

- [ ] …

---

## T-minus (night before, optional, de-risks the morning)

- [ ] `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`
- [ ] `python demo/cli_demo.py all` runs and prints a brief (offline mode OK)
- [ ] all four `tests/test_*.py` green
- [ ] a throwaway Slack workspace created (so build-day is just tokens)
- [x] **rotate** the GitHub PAT and Gemini key that were shared in chat
      A second Gemini key was pasted into a chat on 12 Sep and must also be
      rotated. `security/` now scans for this: the pre-commit hook blocks a
      commit containing a credential, and `security/scan_cli.py --history`
      checks what is already in the repo (currently clean).

## 11:15 — kickoff

- [ ] `git checkout -b build-day` (or work on `main`); first commit **now**, timestamped
- [ ] read the starter-kit + sponsor credits on the portal — is there an
      Anthropic / OpenAI credit? Put it in `.env`

## 11:20–12:30 — core: router + orchestrator (live)

- [ ] rewrite `ROUTER_SYSTEM_PROMPT` / `ORCHESTRATOR_SYSTEM_PROMPT` for the
      demo scenario you'll show
- [ ] `python demo/cli_demo.py chat "…"` until routing + brief look right
      with a real API key
- [ ] commit

## 12:30–14:00 — Slack integration (live)

- [ ] follow `SLACK_SETUP.md` end-to-end
- [ ] `python slack_app/app.py`, invite bot to `#dira-pm-demo`
- [ ] verify all three entry points: `/pm`, `@mention`, CSV upload
- [ ] verify Approve/Discuss/Reject writes to `audit_log/audit_trail.jsonl`
- [ ] commit

## 14:00–14:45 — demo scenario + polish

- [ ] build one coherent "Project X" story: a schedule CSV, a vendor
      comparison, a budget update — so the consolidated brief shows all
      three specialists + a real risk/conflict
- [ ] screenshot the audit log for the video
- [ ] commit

## 14:45–15:15 — record the 2-minute video

Script in `SUBMISSION.md`. One take of the Slack flow + 15s of the audit log.

## 15:15–15:30 — submit

- [ ] `git push` (make the repo public if it isn't)
- [ ] portal: title, description (from `SUBMISSION.md`), repo URL, video URL
- [ ] social post tagging the event partners (OpenAI + CopilotKit,
      OpenRouter, Exa, Auth0, Ambiguous AI, Trigger.dev, Mozilla, Google
      Cloud Run) — check the portal for exact handles
- [ ] confirm submission shows as complete

---

## Commit log (fill in)

| time | commit | what |
|---|---|---|
| | | |
