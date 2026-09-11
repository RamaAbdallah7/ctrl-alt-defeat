# Web demos

Self-contained HTML — open the file in a browser, no build, no server.

| File | What it is |
|---|---|
| `proposal-room.html` | Interactive demo of the whole DIR'A-PM idea. Fill in a project proposal (or pick one of three scenarios), watch a router split it across four specialist agents, and see every teammate get a task packet scoped to their role. Live recompute as you edit; War room + Team board views; audit trail. On claude.ai it also declares the `sample` capability so the "draft with the orchestrator" buttons call an LLM. |
| `slack-brief-mockup.html` | Static mockup of what the bot posts back into a Slack channel — the Executive Brief card with Approve / Discuss / Reject and the audit trail. |

Both are illustrative front-ends. The real analysis engines live in `engines/`; the
router + orchestrator in `agents/`; the Slack app in `slack_app/`.
