"""
BriefView -> Microsoft Teams Adaptive Card (schema 1.4, which is what the
Teams client renders reliably).

Two Teams-specific things worth knowing, because they are the usual causes
of a card that "works in the designer" but not in Teams:

  * Teams has no button styles beyond positive/destructive on Action.Submit,
    so severity is carried by a coloured TextBlock as well as the button.
  * Action.Submit sends back whatever is in `data`, so the event id rides
    along there -- that is how a decision is tied to the brief it decided.
"""

from __future__ import annotations

from channels.brief import BriefView, DECISIONS

CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"

_ACTION_STYLE = {"good": "positive", "danger": "destructive", "default": "default"}


def render(view: BriefView) -> dict:
    """Returns the Adaptive Card payload (wrap with `attachment()` to send)."""
    body = []

    if view.status == "needs_info":
        body.append(_text(view.title, size="Medium", weight="Bolder", color="Accent"))
        body.append(_text(view.body, wrap=True))
        return _card(body, [])

    if view.status == "error":
        body.append(_text("Something went wrong", weight="Bolder", color="Attention"))
        body.append(_text(view.body, wrap=True))
        return _card(body, [])

    body.append(_text(view.title, size="Large", weight="Bolder"))
    if view.context:
        body.append(_text(view.context, size="Small", isSubtle=True, wrap=True))
    body.append(_text(view.body, wrap=True, spacing="Medium"))

    if view.findings:
        body.append({"type": "TextBlock", "text": "Specialist findings", "weight": "Bolder",
                     "size": "Small", "spacing": "Medium", "separator": True})
        for f in view.findings:
            label = f.agent if f.ok else f"{f.agent} (failed)"
            body.append({
                "type": "Container",
                "spacing": "Small",
                "items": [
                    _text(label, weight="Bolder", size="Small",
                          color="Attention" if not f.ok else "Default"),
                    _text(f.text, wrap=True, size="Small", isSubtle=True),
                ],
            })

    if view.footer:
        body.append(_text(view.footer, size="Small", isSubtle=True,
                          wrap=True, spacing="Medium", separator=True))

    actions = []
    if view.wants_decision:
        actions = [
            {
                "type": "Action.Submit",
                "title": d["label"],
                "style": _ACTION_STYLE.get(d["style"], "default"),
                "data": {
                    "action": d["id"],
                    "event_id": view.event_id,
                },
            }
            for d in DECISIONS
        ]

    return _card(body, actions)


def attachment(view: BriefView) -> dict:
    """The card wrapped as a Bot Framework attachment, ready to send."""
    return {"contentType": CARD_CONTENT_TYPE, "content": render(view)}


def _card(body: list, actions: list) -> dict:
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def _text(text, **kw):
    block = {"type": "TextBlock", "text": text}
    block.update(kw)
    return block
