# Microsoft Teams setup

Teams has **no Socket Mode equivalent**. The Bot Framework calls your bot, so
unlike the Slack path this one needs a public HTTPS URL. Budget ~25 minutes,
and read the blocker below *before* you start.

## Read this first - the one thing that can stop you

Sideloading a custom app needs your Microsoft 365 tenant to allow it. Many
university and corporate tenants have it switched off, and only a Teams
administrator can turn it on. Check now:

**Teams → Apps → Manage your apps → Upload an app.** If *"Upload a custom app"*
is missing or greyed out, you cannot sideload into that tenant, and no amount
of code will change it. Two ways round it:

- a free **Microsoft 365 Developer Program** tenant, where you are the admin, or
- the **Bot Framework Emulator**, which talks to the bot locally with no tenant
  at all. Good enough to demo the whole flow, and it needs no Azure resources.

The Slack path (`SLACK_SETUP.md`) has none of this, which is why it is the
better bet if you are short on time.

---

## 1. Register the bot

<https://portal.azure.com> → **Azure Bot** → Create.

| field | value |
|---|---|
| Bot handle | `tarteeb` |
| Type of App | **Multi Tenant** |
| Creation type | Create new Microsoft App ID |

Then **Configuration → Microsoft App ID** → copy it, and
**Manage → Certificates & secrets → New client secret** → copy the *value*
(it is shown once).

Put both in `.env`:

```
MICROSOFT_APP_ID=<the app id>
MICROSOFT_APP_PASSWORD=<the secret value>
MICROSOFT_APP_TYPE=MultiTenant
```

Under **Channels**, add **Microsoft Teams**.

## 2. Run the bot

```bash
.venv/bin/python teams_app/app.py
```

It listens on `http://localhost:3978/api/messages`, and `GET /health` reports
whether credentials and an LLM provider are configured.

## 3. Expose it over HTTPS

```bash
devtunnel host -p 3978 --allow-anonymous
```

(or `ngrok http 3978`). Copy the HTTPS URL, then set the Azure Bot's
**Configuration → Messaging endpoint** to:

```
https://<your-tunnel>/api/messages
```

The tunnel URL changes each restart - update the endpoint when it does. This
is the single most common reason a Teams bot goes silent.

## 4. Install into Teams

1. Edit `teams_app/manifest/manifest.json`: replace **both**
   `REPLACE_WITH_MICROSOFT_APP_ID` values with your app id.
2. Rebuild the package:
   ```bash
   cd teams_app/manifest && zip -r ../tarteeb-teams-app.zip manifest.json color.png outline.png
   ```
3. Teams → **Apps → Manage your apps → Upload an app → Upload a custom app**,
   and pick `teams_app/tarteeb-teams-app.zip`.

## 5. Use it

- **1:1** - message the bot directly.
- **In a channel** - add it to the team, then `@Tarteeb how is the budget tracking?`
- **A CSV** - upload a tasks / scoring / cost CSV to a **channel** (see
  `demo/sample_data/`). Personal-chat uploads arrive as a consent card rather
  than a link, which the demo does not implement.
- Every brief carries **Approve / Discuss further / Reject**, and the press is
  written to `audit_log/audit_trail.jsonl`.

## Testing without a tenant

The Bot Framework Emulator needs no Azure registration and no tunnel:

1. Install it: <https://github.com/microsoft/BotFramework-Emulator/releases>
2. Leave `MICROSOFT_APP_ID` and `MICROSOFT_APP_PASSWORD` blank in `.env`.
3. Run `.venv/bin/python teams_app/app.py`.
4. Open the emulator → `http://localhost:3978/api/messages`, leave the id and
   password empty, connect.

Adaptive Cards and the decision buttons render there, so the whole flow can be
demonstrated on a laptop with no tenant and no tunnel.

## Troubleshooting

| symptom | cause |
|---|---|
| Bot never replies in Teams | Messaging endpoint points at a dead tunnel |
| `401 Unauthorized` in the logs | `MICROSOFT_APP_ID` / `MICROSOFT_APP_PASSWORD` wrong or unset |
| "Upload a custom app" missing | Tenant forbids sideloading - use a dev tenant or the emulator |
| Card shows but buttons do nothing | An old manifest; `supportsFiles` and bot scopes must match section 4 |
| CSV ignored in a 1:1 chat | Expected - upload to a channel instead |
