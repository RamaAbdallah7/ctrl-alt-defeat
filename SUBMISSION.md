# Hackathon submission — draft

Fill the blanks live; the prose is ready to go.

---

## Project title

**DIR'A-PM — the project-management copilot that lives in your Slack channel**

(Team: CTRL+ALT+DEFEAT)

---

## Written description

Project teams already make their scheduling and budget decisions in one
place — their Slack channel — but the *analysis* behind those decisions
lives somewhere else: a critical-path chart in MS Project, a weighted
decision matrix in one person's spreadsheet, an earned-value calculation
nobody has redone in three weeks. So the conversation happens without the
math, or stalls while someone goes and opens a tool.

DIR'A-PM puts the analysis where the conversation already is. You `/pm` a
question, @mention the bot, or drop a CSV into the channel. A router agent
reads the request, decides which analyses apply, and extracts the numbers.
Deterministic engines — not the language model — compute the critical path
and float, the weighted decision matrix, and the cost/schedule performance
indices. An Executive Orchestrator agent consolidates every engine's output
into a single brief posted back into the thread: summary, key findings,
risks and conflicts, missing information, and 2–3 recommended next steps.

Every brief carries **Approve / Discuss / Reject** buttons, and every step —
the request, what was extracted, what each engine returned, the brief, and
the human's decision — is written to an append-only audit trail. The AI
advises; a human always decides, and the decision is logged.

It's meaningfully better *because* it's in Slack: it reads the CSV someone
just dropped, the figures someone just pasted, and answers in the thread
everyone is already watching — no one leaves the conversation, and the
decision checkpoint is built into the message.

The math engines are reusable libraries validated against known-correct
reference figures; the router, the orchestrator, the multi-provider LLM
layer (Anthropic with a Gemini fallback so a rate limit can't kill the
demo), and the entire Slack integration were built during the event.

**Stack:** Python, Slack Bolt (Socket Mode), Anthropic `claude-sonnet-5`
tool-use for routing + brief-writing, Google Gemini as fallback,
deterministic NumPy-free engines for all PM math.

---

## Two-minute demo video — script

| time | on screen | say |
|---|---|---|
| 0:00–0:15 | Slack channel `#project-x` with a few teammates chatting | "This is where our project team already works. The scheduling and budget decisions happen here — but the analysis behind them doesn't." |
| 0:15–0:35 | type `/pm` with a vendor comparison in plain words | "I ask the PM copilot to compare three vendors on cost, quality and delivery — in plain English, in the channel." |
| 0:35–0:50 | brief appears: top option, the near-tie risk, missing-data note, Approve/Discuss/Reject | "A router agent picked the weighted-decision-matrix engine, extracted the numbers, and a deterministic engine did the math — not the LLM. The orchestrator flags that the top two options are effectively tied." |
| 0:50–1:10 | drag `tasks.csv` into the channel | "Now someone drops the project schedule as a CSV. Same copilot — it auto-detects the file, runs critical-path, and posts the critical path and float back into the thread." |
| 1:10–1:30 | `@DIR'A-PM` with budget figures; consolidated brief with schedule + cost + vendor | "And when I give it budget figures too, one brief consolidates all three specialists — and catches that we're over budget *and* behind schedule on the critical path." |
| 1:30–1:45 | click **Approve**; confirmation posts | "The AI never decides. A human approves, discusses, or rejects — right in the message." |
| 1:45–2:00 | terminal: `python demo/cli_demo.py audit` scrolling the JSONL | "Every step — what was asked, what each engine returned, the brief, the human's decision — is in an append-only audit trail. Advice you can trace. That's DIR'A-PM." |

---

## Submission checklist

- [ ] Title (above)
- [ ] Written description (above)
- [ ] Public GitHub repo — https://github.com/RamaAbdallah7/ctrl-alt-defeat
- [ ] 2-minute video — link: ______
- [ ] Social post tagging event partners — link: ______
- [ ] Portal submission marked complete
