"""
Resource loading engine.

A schedule that is feasible on paper is often impossible in practice,
because the same person is on two tasks at once. CPM alone cannot see this:
it assumes unlimited resources. This engine takes the schedule's computed
dates and the assignments, and finds where a person is committed beyond
their capacity.

  * over-allocation: a person's committed units exceed their capacity on a
    given day
  * a levelling hint: the over-allocated task with the most total float is
    the cheapest one to move, because moving it does not touch the finish date
  * critical-path exposure: an over-allocated person on the critical path is
    a schedule risk, not just an admin problem
"""

from __future__ import annotations

from engines.cpm import compute_critical_path, CPMError


class ResourceError(ValueError):
    pass


def analyze_resources(tasks: list, capacity: dict = None) -> dict:
    """
    tasks: the CPM task list, each optionally carrying
           {"assignee": "Rama", "units": 1.0}
           `units` is the share of that person's day the task needs (1.0 = full time).
    capacity: {"Rama": 1.0, ...} -- defaults to 1.0 (one full-time day) each.
    """
    if not tasks:
        raise ResourceError("No tasks provided")

    sched = compute_critical_path(tasks)
    by_id = {t["id"]: t for t in sched["tasks"]}
    assign = {str(t["id"]): t for t in tasks}

    capacity = dict(capacity or {})
    people = {}
    for tid, t in by_id.items():
        who = assign.get(tid, {}).get("assignee")
        if not who:
            continue
        units = float(assign[tid].get("units", 1.0))
        if units <= 0:
            raise ResourceError(f"Task '{tid}' has non-positive units ({units})")
        people.setdefault(who, []).append({
            "id": tid, "name": t["name"], "units": units,
            "start": t["early_start"], "finish": t["early_finish"],
            "total_float": t["total_float"], "is_critical": t["is_critical"],
        })

    if not people:
        raise ResourceError(
            "No task carries an assignee -- add {\"assignee\": \"...\"} to the tasks "
            "you want loaded."
        )

    horizon = int(sched["project_duration"])
    report, conflicts = [], []

    for who, items in sorted(people.items()):
        cap = float(capacity.get(who, 1.0))
        # day-by-day load; a task spanning [start, finish) occupies those days
        daily = []
        for day in range(horizon):
            on = [i for i in items if i["start"] <= day < i["finish"]]
            load = sum(i["units"] for i in on)
            daily.append({"day": day, "load": round(load, 4),
                          "tasks": [i["id"] for i in on]})

        over = [d for d in daily if d["load"] > cap + 1e-9]
        peak = max((d["load"] for d in daily), default=0.0)
        committed = sum(i["units"] * (i["finish"] - i["start"]) for i in items)

        entry = {
            "person": who,
            "capacity": cap,
            "peak_load": round(peak, 4),
            "over_allocated_days": [d["day"] for d in over],
            "committed_days": round(committed, 2),
            "utilisation": round(committed / (cap * horizon), 4) if horizon else None,
            "tasks": items,
        }
        report.append(entry)

        if over:
            clash_ids = sorted({tid for d in over for tid in d["tasks"]})
            movable = [by_id[t] for t in clash_ids if not by_id[t]["is_critical"]]
            best = max(movable, key=lambda t: t["total_float"]) if movable else None
            conflicts.append({
                "person": who,
                "days": [d["day"] for d in over],
                "peak_load": round(peak, 4),
                "capacity": cap,
                "tasks": clash_ids,
                "on_critical_path": [t for t in clash_ids if by_id[t]["is_critical"]],
                "levelling_hint": (
                    f"Move '{best['name']}' ({best['id']}) -- it holds {best['total_float']:g} "
                    f"days of total float, so delaying it does not move the finish date."
                    if best else
                    "Every clashing task is on the critical path, so levelling cannot fix this "
                    "without moving the finish date or adding a person."
                ),
            })

    flags = []
    if not conflicts:
        flags.append(
            f"No over-allocation: {len(report)} person(s) stay within capacity across all "
            f"{horizon} days."
        )
    else:
        for c in conflicts:
            flags.append(
                f"{c['person']} is over-allocated on {len(c['days'])} day(s) "
                f"(peak {c['peak_load']:g} against a capacity of {c['capacity']:g}) "
                f"across {', '.join(c['tasks'])}. {c['levelling_hint']}"
            )
        crit = [c for c in conflicts if c["on_critical_path"]]
        if crit:
            flags.append(
                f"{len(crit)} of these clashes touch the critical path -- that is a schedule "
                f"risk, not just a staffing one."
            )

    idle = [r["person"] for r in report if r["utilisation"] is not None and r["utilisation"] < 0.4]
    if idle and conflicts:
        flags.append(
            f"Meanwhile {', '.join(idle)} sit under 40% utilisation -- the work may be "
            f"reassignable rather than delayed."
        )

    return {
        "project_duration": sched["project_duration"],
        "critical_path": sched["critical_path"],
        "people": report,
        "conflicts": conflicts,
        "has_over_allocation": bool(conflicts),
        "flags": flags,
    }
