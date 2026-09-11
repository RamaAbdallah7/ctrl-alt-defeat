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
                                "type": "array",
                                "description": "this option's raw score (0-100) against each criterion",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "criterion": {"type": "string", "description": "must match a criterion name exactly"},
                                        "score": {"type": "number", "description": "raw score, 0-100"},
                                    },
                                    "required": ["criterion", "score"],
                                },
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
                "planned_duration": {"type": "number", "description": "optional planned project length, enables a schedule forecast"},
            },
            "required": ["pv", "ev", "ac", "bac"],
        },
    },
    {
        "name": "run_financial_analysis",
        "description": (
            "Project selection / business case: net present value (NPV), return on investment "
            "(ROI) and payback period from a stream of yearly costs and benefits at a discount "
            "rate. Use when the message asks whether a project is worth doing, compares "
            "investments financially, or supplies costs and benefits over several years."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "costs": {"type": "array", "items": {"type": "number"},
                          "description": "cost per year, first entry is the first year given"},
                "benefits": {"type": "array", "items": {"type": "number"},
                             "description": "benefit per year, aligned with costs"},
                "discount_rate": {"type": "number", "description": "e.g. 0.08 for 8%"},
                "start_year": {"type": "integer",
                               "description": "0 if the first year is an undiscounted year 0, 1 if it is 'Year 1' and discounted once"},
            },
            "required": ["costs", "benefits", "discount_rate"],
        },
    },
    {
        "name": "run_pert_analysis",
        "description": (
            "Three-point / PERT estimating. Needs optimistic, most likely and pessimistic "
            "estimates per activity. Use when estimates are given as ranges or 'best case / "
            "worst case', when the message asks how confident we are in a date or a total, or "
            "asks the probability of hitting a deadline."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "activities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "optimistic": {"type": "number"},
                            "most_likely": {"type": "number"},
                            "pessimistic": {"type": "number"},
                        },
                        "required": ["optimistic", "most_likely", "pessimistic"],
                    },
                },
                "target": {"type": "number", "description": "optional deadline or cap to compute a probability against"},
                "unit": {"type": "string", "description": "days, weeks, dollars..."},
            },
            "required": ["activities"],
        },
    },
    {
        "name": "run_crash_analysis",
        "description": (
            "Schedule crashing: find the cheapest way to shorten the project. Needs the task "
            "list plus, for the tasks that can be shortened, a crash_duration and the normal_cost "
            "and crash_cost. Use when the message asks how to hit an earlier date, what it would "
            "cost to speed up, or mentions being behind schedule with a fixed deadline."
        ),
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
                            "duration": {"type": "number"},
                            "predecessors": {"type": "array", "items": {"type": "string"}},
                            "crash_duration": {"type": "number", "description": "shortest achievable duration"},
                            "normal_cost": {"type": "number"},
                            "crash_cost": {"type": "number", "description": "cost at the crashed duration"},
                        },
                        "required": ["id", "duration"],
                    },
                },
                "target_duration": {"type": "number"},
                "max_spend": {"type": "number"},
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "run_fast_track_analysis",
        "description": (
            "Fast tracking: which sequential critical-path activities could be overlapped to "
            "save time, and what the rework risk is. Use when the schedule must shorten but "
            "there is no budget to crash it."
        ),
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
                            "duration": {"type": "number"},
                            "predecessors": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["id", "duration"],
                    },
                },
                "overlap_fraction": {"type": "number", "description": "how much of the successor could start early, 0-1 (default 0.5)"},
            },
            "required": ["tasks"],
        },
    },
    {
        "name": "run_wbs_analysis",
        "description": (
            "Work breakdown structure check: rolls costs/hours up the tree and reports 100%-rule "
            "violations, orphaned items and work packages that were never decomposed. Use when "
            "the message supplies a WBS, a deliverable breakdown, or asks whether the plan adds up."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "parent": {"type": "string", "description": "parent id, omit for a root"},
                            "value": {"type": "number", "description": "cost or hours for this item"},
                        },
                        "required": ["id"],
                    },
                },
                "value_label": {"type": "string", "description": "cost, hours, story points..."},
            },
            "required": ["items"],
        },
    },
    {
        "name": "run_scope_creep_analysis",
        "description": (
            "Compare the current work breakdown against the approved baseline and report what "
            "was added, removed or re-estimated. Use when the message mentions scope changes, "
            "new requirements, or asks whether the project has grown since it was approved."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "baseline": {"type": "array", "items": {"type": "object",
                             "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "value": {"type": "number"}},
                             "required": ["id"]}},
                "current": {"type": "array", "items": {"type": "object",
                            "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "value": {"type": "number"}},
                            "required": ["id"]}},
                "value_label": {"type": "string"},
            },
            "required": ["baseline", "current"],
        },
    },
    {
        "name": "run_estimate_check",
        "description": (
            "Classify a cost estimate by type (rough order of magnitude, budgetary, definitive) "
            "and return the accuracy range it actually implies, optionally checking a budget "
            "against it. Use when someone quotes an estimate, asks how firm a number is, or "
            "treats an early figure as if it were precise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "estimate": {"type": "number"},
                "estimate_type": {"type": "string", "enum": ["rom", "budgetary", "definitive"]},
                "budget": {"type": "number"},
            },
            "required": ["estimate", "estimate_type"],
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
