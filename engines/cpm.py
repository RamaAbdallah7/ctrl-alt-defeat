"""
Critical Path Method (CPM) engine.

Deterministic scheduling math -- no LLM involved. Given a list of tasks with
durations and finish-to-start predecessor relationships, computes the
forward pass (Early Start / Early Finish), backward pass (Late Start / Late
Finish), total float, free float, the critical path, and overall project
duration -- the same quantities MS Project's "Schedule" table shows
(Table 6-1 / Figure 6-2 style exercises).

Units are whatever the caller uses for duration (days, by convention here,
to match the course's Network Diagram exercise).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


class CPMError(ValueError):
    pass


@dataclass
class Task:
    id: str
    name: str
    duration: float
    predecessors: List[str] = field(default_factory=list)

    # computed
    es: float = 0.0
    ef: float = 0.0
    ls: float = 0.0
    lf: float = 0.0
    total_float: float = 0.0
    free_float: float = 0.0
    is_critical: bool = False


def _topological_order(tasks: Dict[str, Task]) -> List[str]:
    """Kahn's algorithm; raises CPMError on a cycle or unknown predecessor."""
    indegree = {tid: 0 for tid in tasks}
    successors: Dict[str, List[str]] = {tid: [] for tid in tasks}

    for tid, t in tasks.items():
        for p in t.predecessors:
            if p not in tasks:
                raise CPMError(f"Task '{tid}' lists unknown predecessor '{p}'")
            successors[p].append(tid)
            indegree[tid] += 1

    queue = [tid for tid, d in indegree.items() if d == 0]
    order: List[str] = []
    while queue:
        # stable order for deterministic output
        queue.sort()
        n = queue.pop(0)
        order.append(n)
        for m in successors[n]:
            indegree[m] -= 1
            if indegree[m] == 0:
                queue.append(m)

    if len(order) != len(tasks):
        raise CPMError("Cycle detected in task dependencies -- cannot schedule")

    return order


def compute_critical_path(task_list: List[dict]) -> dict:
    """
    task_list: [{"id": "A", "name": "...", "duration": 3, "predecessors": []}, ...]

    Returns a dict with per-task schedule fields plus project-level summary
    (duration, critical_path, tasks_by_float).
    """
    if not task_list:
        raise CPMError("No tasks provided")

    tasks: Dict[str, Task] = {}
    for row in task_list:
        tid = str(row["id"])
        if tid in tasks:
            raise CPMError(f"Duplicate task id '{tid}'")
        tasks[tid] = Task(
            id=tid,
            name=row.get("name", tid),
            duration=float(row["duration"]),
            predecessors=[str(p) for p in row.get("predecessors", [])],
        )

    order = _topological_order(tasks)

    # Forward pass: ES = max(EF of predecessors) else 0; EF = ES + duration
    for tid in order:
        t = tasks[tid]
        preds = [tasks[p] for p in t.predecessors]
        t.es = max((p.ef for p in preds), default=0.0)
        t.ef = t.es + t.duration

    project_duration = max((t.ef for t in tasks.values()), default=0.0)

    successors: Dict[str, List[str]] = {tid: [] for tid in tasks}
    for tid, t in tasks.items():
        for p in t.predecessors:
            successors[p].append(tid)

    # Backward pass: LF = min(LS of successors) else project_duration; LS = LF - duration
    for tid in reversed(order):
        t = tasks[tid]
        succs = [tasks[s] for s in successors[tid]]
        t.lf = min((s.ls for s in succs), default=project_duration)
        t.ls = t.lf - t.duration

    for t in tasks.values():
        t.total_float = round(t.ls - t.es, 6)
        # free float = min(ES of successors) - EF, or project_duration - EF if no successors
        succs = [tasks[s] for s in successors[t.id]]
        if succs:
            t.free_float = round(min(s.es for s in succs) - t.ef, 6)
        else:
            t.free_float = round(project_duration - t.ef, 6)
        t.is_critical = abs(t.total_float) < 1e-9

    critical_path = [tid for tid in order if tasks[tid].is_critical]

    return {
        "project_duration": project_duration,
        "critical_path": critical_path,
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "duration": t.duration,
                "predecessors": t.predecessors,
                "early_start": t.es,
                "early_finish": t.ef,
                "late_start": t.ls,
                "late_finish": t.lf,
                "total_float": t.total_float,
                "free_float": t.free_float,
                "is_critical": t.is_critical,
            }
            for t in (tasks[tid] for tid in order)
        ],
    }
