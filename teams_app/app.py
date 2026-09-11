#!/usr/bin/env python3
"""
Tarteeb Teams entrypoint -- an aiohttp server exposing /api/messages.

Unlike Slack's Socket Mode, Teams has no outbound-socket option: the Bot
Framework calls *you*, so this endpoint has to be reachable over HTTPS.
For a demo, `devtunnel host -p 3978 --allow-anonymous` (or ngrok) in front
of this process is the whole story -- see TEAMS_SETUP.md.

  python teams_app/app.py
"""

import os
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from aiohttp import web
from aiohttp.web import Request, Response, json_response
from botbuilder.core import TurnContext
from botbuilder.core.integration import aiohttp_error_middleware
from botbuilder.integration.aiohttp import CloudAdapter, ConfigurationBotFrameworkAuthentication
from botbuilder.schema import Activity, ActivityTypes

from agents import llm
from teams_app.bot import TarteebBot

PORT = int(os.environ.get("PORT", 3978))


class Config:
    """Bot Framework reads these names off the object it is handed."""
    APP_ID = os.environ.get("MICROSOFT_APP_ID", "")
    APP_PASSWORD = os.environ.get("MICROSOFT_APP_PASSWORD", "")
    APP_TYPE = os.environ.get("MICROSOFT_APP_TYPE", "MultiTenant")
    APP_TENANTID = os.environ.get("MICROSOFT_APP_TENANT_ID", "")


ADAPTER = CloudAdapter(ConfigurationBotFrameworkAuthentication(Config()))
BOT = TarteebBot()


async def on_error(context: TurnContext, error: Exception):
    print(f"[teams] unhandled error: {error}", file=sys.stderr)
    traceback.print_exc()
    await context.send_activity(
        "Something went wrong handling that. The error is in the bot's logs; "
        "the audit trail records what did run."
    )


ADAPTER.on_turn_error = on_error


async def messages(req: Request) -> Response:
    if "application/json" not in req.headers.get("Content-Type", ""):
        return Response(status=415, text="Expected application/json")
    body = await req.json()
    activity = Activity().deserialize(body)
    auth_header = req.headers.get("Authorization", "")
    response = await ADAPTER.process_activity(auth_header, activity, BOT.on_turn)
    if response:
        return json_response(data=response.body, status=response.status)
    return Response(status=201)


async def health(_req: Request) -> Response:
    return json_response({
        "service": "tarteeb-teams",
        "time": datetime.utcnow().isoformat() + "Z",
        "app_id_configured": bool(Config.APP_ID),
        "llm_providers": llm.providers_available(),
    })


def main():
    if not Config.APP_ID or not Config.APP_PASSWORD:
        print(
            "MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD are not set.\n"
            "The server will start and /health will answer, but Teams cannot "
            "authenticate to it. See TEAMS_SETUP.md.",
            file=sys.stderr,
        )

    providers = llm.providers_available()
    print(f"LLM providers ready: {', '.join(providers) if providers else 'none (offline mode)'}")

    app = web.Application(middlewares=[aiohttp_error_middleware])
    app.router.add_post("/api/messages", messages)
    app.router.add_get("/health", health)

    print(f"Tarteeb (Teams) listening on http://localhost:{PORT}/api/messages")
    print("Expose it over HTTPS and paste that URL as the bot's messaging endpoint.")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
