"""Anthropic tool-use schemas the router uses to extract structured inputs
for each deterministic engine, plus a clarifying-question escape hatch."""

TOOLS = [
    {
        "name": "run_schedule_analysis",
        "description": "Run critical path / network diagram analysis on a list of tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "duration": {"type": "number", "description": "duration in days"},
                            "predecessors": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "duration"],
                    },
                }
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "run_scoring_analysis",
        "description": "Run a weighted decision matrix over a set of options against weighted criteria.",
        "input_schema": {
            "type": "object",
            "properties": {
                "criteria": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "weight": {"type": "number", "description": "percentage weight, should sum to ~100 across criteria"},
                        },
                        "required": ["name", "weight"],
                    },
                },
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "scores": {
                                "type": "object",
                                "description": "map of criterion name -> raw score (0-100) for this option",
                                "additionalProperties": {"type": "number"},
                            },
                        },
                        "required": ["name", "scores"],
                    },
                },
            },
            "required": ["criteria", "options"],
        },
    },
    {
        "name": "run_cost_analysis",
        "description": "Run earned value management (EVM) analysis given PV, EV, AC and BAC.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pv": {"type": "number", "description": "planned value (BCWS)"},
                "ev": {"type": "number", "description": "earned value (BCWP)"},
                "ac": {"type": "number", "description": "actual cost (ACWP)"},
                "bac": {"type": "number", "description": "budget at completion"},
            },
            "required": ["pv", "ev", "ac", "bac"],
        },
    },
    {
        "name": "ask_clarifying_question",
        "description": "Use when there isn't enough structured data to confidently run any engine.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
]
