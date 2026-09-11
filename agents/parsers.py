"""
CSV -> structured tool-call parsers, shared by the CLI demo and the Slack
file-upload handler. Deliberately simple, forgiving formats so a teammate
can build one in a spreadsheet in under a minute during the demo.

tasks.csv        id,name,duration,predecessors      (predecessors ';'-joined)
scoring.csv      criterion,weight,<Option A>,<Option B>,...
cost.csv         field,value   with fields pv,ev,ac,bac (any order/case)
"""

from __future__ import annotations

import csv
import io
from typing import Optional


class ParseError(ValueError):
    pass


def _read_rows(content: str):
    return list(csv.reader(io.StringIO(content.strip())))


def parse_tasks_csv(content: str) -> dict:
    rows = _read_rows(content)
    if not rows:
        raise ParseError("Empty file")
    header = [h.strip().lower() for h in rows[0]]
    required = {"id", "duration"}
    if not required.issubset(set(header)):
        raise ParseError(f"tasks.csv needs at least columns {required}, got {header}")

    idx = {name: header.index(name) for name in header}
    tasks = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        preds_raw = row[idx["predecessors"]].strip() if "predecessors" in idx and idx["predecessors"] < len(row) else ""
        preds = [p.strip() for p in preds_raw.split(";") if p.strip()] if preds_raw else []
        tasks.append({
            "id": row[idx["id"]].strip(),
            "name": row[idx["name"]].strip() if "name" in idx and idx["name"] < len(row) else row[idx["id"]].strip(),
            "duration": float(row[idx["duration"]]),
            "predecessors": preds,
        })
    return {"name": "run_schedule_analysis", "input": {"tasks": tasks}}


def parse_scoring_csv(content: str) -> dict:
    rows = _read_rows(content)
    if len(rows) < 2:
        raise ParseError("scoring.csv needs a header row plus at least one criterion row")
    header = [h.strip() for h in rows[0]]
    header_lower = [h.lower() for h in header]
    if "criterion" not in header_lower or "weight" not in header_lower:
        raise ParseError(f"scoring.csv needs 'criterion' and 'weight' columns, got {header}")

    crit_idx = header_lower.index("criterion")
    weight_idx = header_lower.index("weight")
    option_cols = [(i, h) for i, h in enumerate(header) if i not in (crit_idx, weight_idx)]
    if not option_cols:
        raise ParseError("scoring.csv needs at least one option column after criterion/weight")

    criteria = []
    options = {name: {"name": name, "scores": {}} for _, name in option_cols}
    for row in rows[1:]:
        if not row or not row[crit_idx].strip():
            continue
        cname = row[crit_idx].strip()
        weight = float(str(row[weight_idx]).replace("%", "").strip())
        criteria.append({"name": cname, "weight": weight})
        for i, opt_name in option_cols:
            if i < len(row) and row[i].strip() != "":
                options[opt_name]["scores"][cname] = float(row[i])

    return {"name": "run_scoring_analysis", "input": {"criteria": criteria, "options": list(options.values())}}


def parse_cost_csv(content: str) -> dict:
    rows = _read_rows(content)
    values = {}
    for row in rows:
        if len(row) < 2:
            continue
        key = row[0].strip().lower()
        if key in ("pv", "ev", "ac", "bac"):
            values[key] = float(row[1])
    missing = {"pv", "ev", "ac", "bac"} - set(values)
    if missing:
        raise ParseError(f"cost.csv missing fields: {missing}")
    return {"name": "run_cost_analysis", "input": values}


def detect_and_parse(filename: str, content: str) -> dict:
    """Best-effort auto-detect based on header row, so a Slack file upload
    can be routed without the user telling us what kind of file it is."""
    rows = _read_rows(content)
    if not rows:
        raise ParseError("Empty file")
    header = {h.strip().lower() for h in rows[0]}

    if {"id", "duration"}.issubset(header):
        return parse_tasks_csv(content)
    if {"criterion", "weight"}.issubset(header):
        return parse_scoring_csv(content)
    if {"pv", "ev", "ac", "bac"}.issubset({r[0].strip().lower() for r in rows if r}):
        return parse_cost_csv(content)

    raise ParseError(
        f"Could not detect file type from header {sorted(header)}. "
        "Expected a tasks.csv (id,duration,...), scoring.csv (criterion,weight,...), "
        "or cost.csv (field,value rows for pv/ev/ac/bac)."
    )
