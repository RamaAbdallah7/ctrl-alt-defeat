# Slack setup (Socket Mode)

Socket Mode means the bot opens an outbound WebSocket to Slack — **no public
URL, no ngrok, no deployment**. You need two tokens: an app-level token
(`xapp-…`) and a bot token (`xoxb-…`).

Budget ~10 minutes. Do this on build day (or the night before against a
throwaway workspace to de-risk).

---

## 1. Create the app

1. <https://api.slack.com/apps> → **Create New App** → **From scratch**
2. Name it `Tarteeb`, pick your workspace.

## 2. App-level token (→ `SLACK_APP_TOKEN`)

1. **Settings → Basic Information → App-Level Tokens → Generate Token and Scopes**
2. Name `socket`, add scope **`connections:write`**, generate.
3. Copy the `xapp-…` value → this is `SLACK_APP_TOKEN`.

## 3. Socket Mode

**Settings → Socket Mode → Enable Socket Mode** → on.

## 4. Bot token scopes

**Features → OAuth & Permissions → Scopes → Bot Token Scopes**, add:

| scope | why |
|---|---|
| `app_mentions:read` | receive `@Tarteeb …` |
| `chat:write` | post briefs back |
| `commands` | the `/pm` slash command |
| `files:read` | download uploaded CSVs |
| `channels:history` | see messages/files in public channels |
| `groups:history` | same for private channels |

## 5. Slash command

**Features → Slash Commands → Create New Command**

- Command: `/pm`
- Request URL: anything non-empty (Socket Mode ignores it) — e.g. `https://example.com/slack`
- Short description: `Ask the PM copilot`
- Usage hint: `<question, or paste figures>`

## 6. Event subscriptions

**Features → Event Subscriptions → Enable Events** → on. Under
**Subscribe to bot events**, add:

- `app_mention`
- `message.channels`
- `message.groups` (for private channels)

## 7. Install

**Settings → Install App → Install to Workspace** → allow. Copy the
**Bot User OAuth Token** (`xoxb-…`) → this is `SLACK_BOT_TOKEN`.

If you change scopes later, reinstall.

## 8. Run

```bash
cp .env.example .env
# edit .env: SLACK_BOT_TOKEN, SLACK_APP_TOKEN, ANTHROPIC_API_KEY (GEMINI_API_KEY optional)
python slack_app/app.py
```

Expected startup line:

```
LLM providers ready (in order): anthropic, gemini
Tarteeb is running (Socket Mode). ...
```

## 9. Try it

Invite the bot to a channel: `/invite @Tarteeb`, then:

- `/pm compare Vendor A, B, C on cost (weight 50), quality (30), delivery (20)`
- `@Tarteeb how is Project X tracking — PV 42000, EV 35000, AC 41000, BAC 120000?`
- Drag `demo/sample_data/tasks.csv` into the channel.

Each reply has **Approve / Discuss / Reject** buttons; clicking one writes a
`human_decision` line to `audit_log/audit_trail.jsonl`.

---

## Troubleshooting

| symptom | fix |
|---|---|
| `Missing SLACK_BOT_TOKEN and/or SLACK_APP_TOKEN` | `.env` not filled / not in repo root |
| `not_authed` / `invalid_auth` | wrong token in wrong var; `xoxb-`=bot, `xapp-`=app |
| slash command "dispatch_failed" | Socket Mode not enabled, or app not reinstalled after adding `commands` |
| bot silent on file upload | missing `files:read` or `message.channels`; bot not in channel |
| bot silent on @mention | missing `app_mentions:read`; reinstall after scope change |
| brief says "offline mode" | no `ANTHROPIC_API_KEY`/`GEMINI_API_KEY`, or both providers erroring — check stderr |
