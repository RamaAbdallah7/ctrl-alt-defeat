#!/usr/bin/env python3
"""
Tarteeb Slack app entrypoint. Runs in Socket Mode, so no public URL /
ngrok tunnel is needed during the hackathon -- just two tokens.

Setup (see README.md for the full walkthrough):
  1. Create a Slack app at https://api.slack.com/apps -> "From scratch"
  2. Enable Socket Mode, generate an app-level token (xapp-...) with
     connections:write scope
  3. Add bot token scopes: app_mentions:read, chat:write, commands,
     files:read, channels:history, groups:history
  4. Create the /pm slash command
  5. Subscribe to bot events: app_mention, message.channels
  6. Install the app to your workspace, copy the Bot User OAuth Token (xoxb-...)
  7. Copy .env.example to .env and fill in SLACK_BOT_TOKEN, SLACK_APP_TOKEN,
     ANTHROPIC_API_KEY
  8. python3 slack_app/app.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from slack_app.handlers import register_handlers
from agents import llm


def main():
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        print("Missing SLACK_BOT_TOKEN and/or SLACK_APP_TOKEN. Copy .env.example to .env and fill them in.")
        sys.exit(1)

    providers = llm.providers_available()
    if providers:
        print(f"LLM providers ready (in order): {', '.join(providers)}")
    else:
        print("WARNING: no LLM provider reachable (ANTHROPIC_API_KEY / GEMINI_API_KEY unset) -- "
              "conversational (@mention free text) routing and the executive-brief writer will "
              "fall back to offline/templated mode. Slash-command and file-upload flows with "
              "structured data still work fully.")

    app = App(token=bot_token)
    register_handlers(app)

    handler = SocketModeHandler(app, app_token)
    print("Tarteeb is running (Socket Mode). Try /pm in your workspace, "
          "@-mention the bot, or drop a tasks/scoring/cost CSV in a channel it's in.")
    handler.start()


if __name__ == "__main__":
    main()
