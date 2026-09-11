"""
Schedule compression engine (Chapter 06, "Using the Critical Path to
Shorten a Project Schedule").

Two techniques, both driven off the CPM engine:

CRASHING -- buy time with money. Each activity may carry a crash duration
and a crash cost; the crash cost per period is

    (crash cost - normal cost) / (normal duration - crash duration)

The course's rule is "obtain the greatest amount of schedule compression
for the least incremental cost", i.e. repeatedly shorten the cheapest
activity that is *on the critical path*, recomputing the critical path
each time because it moves as you compress. That is exactly what
`crash_schedule` does.

One honest caveat, which the engine reports rather than hides: when two
critical paths run in parallel, shortening one alone buys nothing, so the
engine detects that case and crashes the cheapest candidate on each
parallel critical path together. It is a greedy heuristic, not a proven
optimum -- for the network sizes a project manager reasons about in a
channel, greedy and optimal almost always agree, and the per-step log
below makes the reasoning auditable either way.

FAST TRACKING -- buy time with risk, by overlapping activities that were
planned in sequence. `fast_track_candidates` ranks the finish-to-start
links on the critical path by how much time overlapping them could save,
and states the risk, because doing work before its predecessor finishes
is what causes rework.
"""

from __future__ import annotations

from engines.cpm import compute_critical_path, CPMError


class CompressionError(ValueError):
    pass


def _duration_of(tasks: list) -> tuple:
    r = compute_critical_path(tasks)
    return r["project_duration"], r, {t["id"] for t in r["tasks"] if t["is_critical"]}


def _critical_paths(result: dict) -> list:
    """Enumerate the distinct critical chains through the network."""
    by_id = {t["id"]: t for t in result["tasks"]}
    crit = {tid for tid, t in by_id.items() if t["is_critical"]}
    starts = [tid for tid in crit if not (set(by_id[tid]["predecessors"]) & crit)]

    paths, stack = [], [[s] for s in starts]
    while stack:
        path = stack.pop()
        last = path[-1]
        nxt = [tid for tid in crit
               if last in by_id[tid]["predecessors"]]
        if not nxt:
            paths.append(path)
        else:
            for n in nxt:
                stack.append(path + [n])
    return paths


def crash_schedule(tasks: list, target_duration: float = None, max_spend: float = None) -> dict:
    """
    tasks: the CPM task list, each optionally carrying
           {"crash_duration": float, "crash_cost": float, "normal_cost": float}
           Activities without crash data are treated as not crashable.

    target_duration: compress until the project reaches this (or until no
                     further compression is possible).
    max_spend: stop once cumulative crash cost would exceed this.

    Returns the baseline, the per-step log, and the compressed schedule.
    """
    if not tasks:
        raise CompressionError("No tasks provided")

    work = []
    crashable = {}
    for row in tasks:
        t = dict(row)
        t["duration"] = float(t["duration"])
        work.append(t)
        tid = str(t["id"])
        if "crash_duration" in row and row["crash_duration"] is not None:
            cd = float(row["crash_duration"])
            nc = float(row.get("normal_cost", 0.0))
            cc = float(row.get("crash_cost", 0.0))
            room = t["duration"] - cd
            if room > 0:
                crashable[tid] = {
                    "crash_duration": cd,
                    "cost_per_period": (cc - nc) / room,
                    "normal_duration": t["duration"],
                }
            elif room < 0:
                raise CompressionError(
                    f"Task '{tid}' has a crash duration ({cd:g}) longer than its normal duration ({t['duration']:g})"
                )

    baseline_duration, baseline_result, _ = _duration_of(work)
    if target_duration is not None and float(target_duration) > baseline_duration:
        raise CompressionError(
            f"Target duration {float(target_duration):g} is longer than the current "
            f"schedule ({baseline_duration:g}) -- nothing to compress"
        )

    by_id = {str(t["id"]): t for t in work}
    steps, total_cost = [], 0.0
    guard = 0

    while True:
        guard += 1
        if guard > 1000:
            break
        duration, result, crit_ids = _duration_of(work)
        if target_duration is not None and duration <= float(target_duration):
            break

        candidates = [
            tid for tid in crit_ids
            if tid in crashable and by_id[tid]["duration"] > crashable[tid]["crash_duration"]
        ]
        if not candidates:
            break

        # Which single crash actually shortens the project?
        effective = []
        for tid in candidates:
            by_id[tid]["duration"] -= 1
            d2, _, _ = _duration_of(work)
            by_id[tid]["duration"] += 1
            if d2 < duration:
                effective.append(tid)

        if effective:
            chosen = [min(effective, key=lambda t: crashable[t]["cost_per_period"])]
        else:
            # parallel critical paths: crash the cheapest candidate on each
            chosen = []
            for path in _critical_paths(result):
                on_path = [t for t in path if t in candidates]
                if on_path:
                    pick = min(on_path, key=lambda t: crashable[t]["cost_per_period"])
                    if pick not in chosen:
                        chosen.append(pick)
            if not chosen:
                break

        step_cost = sum(crashable[t]["cost_per_period"] for t in chosen)
        if max_spend is not None and total_cost + step_cost > float(max_spend):
            steps.append({
                "stopped": f"Next step would cost {step_cost:,.2f}, taking the total past the "
                           f"{float(max_spend):,.2f} limit."
            })
            break

        for tid in chosen:
            by_id[tid]["duration"] -= 1
        new_duration, _, _ = _duration_of(work)

        if new_duration >= duration:
            # This step bought nothing: a path with no crash room left is now
            # binding. Roll the crashes back rather than charging for time we
            # did not get, and stop.
            for tid in chosen:
                by_id[tid]["duration"] += 1
            steps.append({
                "stopped": "Stopped: the remaining critical path has no crashable activity, "
                           "so further spending would buy no time. Nothing was charged for this step.",
            })
            break

        total_cost += step_cost
        steps.append({
            "crashed": [
                {"id": t, "name": by_id[t].get("name", t),
                 "from": by_id[t]["duration"] + 1, "to": by_id[t]["duration"],
                 "cost_per_period": round(crashable[t]["cost_per_period"], 2)}
                for t in chosen
            ],
            "step_cost": round(step_cost, 2),
            "cumulative_cost": round(total_cost, 2),
            "duration_before": duration,
            "duration_after": new_duration,
        })

    final_duration, final_result, _ = _duration_of(work)
    saved = baseline_duration - final_duration

    flags = []
    if saved == 0:
        flags.append("The schedule could not be compressed -- no critical activity has crash data with room to shorten.")
    else:
        flags.append(
            f"Compressed {saved:g} period(s), from {baseline_duration:g} to {final_duration:g}, "
            f"for {total_cost:,.2f} in additional cost "
            f"({total_cost / saved:,.2f} per period bought)."
        )
    if target_duration is not None and final_duration > float(target_duration):
        flags.append(
            f"Target of {float(target_duration):g} was NOT reached -- {final_duration:g} is the "
            f"shortest achievable with the crash data supplied. Reaching the target needs "
            f"scope reduction or fast tracking, not more money."
        )

    return {
        "baseline_duration": baseline_duration,
        "baseline_critical_path": baseline_result["critical_path"],
        "final_duration": final_duration,
        "final_critical_path": final_result["critical_path"],
        "periods_saved": saved,
        "total_crash_cost": round(total_cost, 2),
        "cost_per_period_saved": round(total_cost / saved, 2) if saved else None,
        "steps": steps,
        "compressed_tasks": [
            {"id": str(t["id"]), "name": t.get("name", t["id"]), "duration": t["duration"]}
            for t in work
        ],
        "flags": flags,
    }


def fast_track_candidates(tasks: list, overlap_fraction: float = 0.5) -> dict:
    """
    Rank the finish-to-start links on the critical path by how much
    overlapping them could save. overlap_fraction is how much of the
    successor could plausibly start early (0.5 = start it halfway through
    its predecessor).
    """
    if not (0 < float(overlap_fraction) <= 1):
        raise CompressionError("overlap_fraction must be between 0 and 1")

    result = compute_critical_path(tasks)
    by_id = {t["id"]: t for t in result["tasks"]}
    crit = [t for t in result["tasks"] if t["is_critical"]]

    candidates = []
    for t in crit:
        for p in t["predecessors"]:
            if p in by_id and by_id[p]["is_critical"]:
                pred = by_id[p]
                saving = min(pred["duration"], t["duration"]) * float(overlap_fraction)
                candidates.append({
                    "predecessor": p,
                    "predecessor_name": pred["name"],
                    "successor": t["id"],
                    "successor_name": t["name"],
                    "potential_saving": round(saving, 2),
                    "risk": f"Starting '{t['name']}' before '{pred['name']}' finishes means working "
                            f"from unfinished input -- the classic cause of rework. Only overlap "
                            f"if the first {int((1 - float(overlap_fraction)) * 100)}% of "
                            f"'{pred['name']}' produces what '{t['name']}' actually needs.",
                })

    candidates.sort(key=lambda c: c["potential_saving"], reverse=True)

    flags = []
    if not candidates:
        flags.append("No finish-to-start links on the critical path to overlap -- fast tracking has nothing to work with here.")
    else:
        best = candidates[0]
        flags.append(
            f"Best fast-track candidate: overlap '{best['predecessor_name']}' and "
            f"'{best['successor_name']}' to save up to {best['potential_saving']:g} period(s). "
            f"Fast tracking buys time with risk, not money."
        )

    return {
        "project_duration": result["project_duration"],
        "critical_path": result["critical_path"],
        "overlap_fraction": float(overlap_fraction),
        "candidates": candidates,
        "flags": flags,
    }
