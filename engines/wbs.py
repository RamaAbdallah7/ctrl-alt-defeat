"""
Work Breakdown Structure / scope engine (Chapter 05, Project Scope
Management).

A WBS is "a deliverable-oriented grouping of the work involved in a
project that defines its total scope", built by decomposition, with a
work package as the task at the lowest level.

This engine checks the things that actually go wrong with a WBS and that
a project manager would otherwise have to eyeball:

  * the 100%% rule -- a parent's children must account for the parent, no
    more and no less. Under-rolling means work is missing from the plan;
    over-rolling means it is double-counted.
  * orphans -- items whose stated parent does not exist
  * cycles -- an item that is its own ancestor
  * work packages -- the leaves, which are what actually gets estimated
    and scheduled
  * decomposition depth -- leaves left at level 1 are usually not
    decomposed enough to estimate honestly

`detect_scope_creep` compares a current WBS against an approved baseline
and reports what was added, removed, or re-estimated -- the uncontrolled
change the chapter calls scope creep.
"""

from __future__ import annotations


class WBSError(ValueError):
    pass


def _index(items: list) -> dict:
    nodes = {}
    for row in items:
        iid = str(row["id"])
        if iid in nodes:
            raise WBSError(f"Duplicate WBS id '{iid}'")
        nodes[iid] = {
            "id": iid,
            "name": row.get("name", iid),
            "parent": str(row["parent"]) if row.get("parent") not in (None, "") else None,
            "value": float(row["value"]) if row.get("value") is not None else None,
            "children": [],
        }
    return nodes


def analyze_wbs(items: list, value_label: str = "cost", tolerance: float = 0.01) -> dict:
    """
    items: [{"id": "1.1", "name": "...", "parent": "1", "value": 40000}, ...]
           `value` is whatever is being rolled up -- cost, hours, story points.
           Parents may omit `value`, in which case the roll-up fills it in.
    """
    if not items:
        raise WBSError("No WBS items provided")

    nodes = _index(items)

    orphans = []
    for n in nodes.values():
        if n["parent"] is None:
            continue
        if n["parent"] not in nodes:
            orphans.append({"id": n["id"], "name": n["name"], "missing_parent": n["parent"]})
        else:
            nodes[n["parent"]]["children"].append(n["id"])

    # cycle / depth detection
    def depth_of(iid, seen=None):
        seen = seen or set()
        if iid in seen:
            raise WBSError(f"Cycle in the WBS involving '{iid}' -- an item is its own ancestor")
        p = nodes[iid]["parent"]
        if p is None or p not in nodes:
            return 1
        return 1 + depth_of(p, seen | {iid})

    for iid in nodes:
        nodes[iid]["level"] = depth_of(iid)

    roots = [n["id"] for n in nodes.values() if n["parent"] is None or n["parent"] not in nodes]
    leaves = [n["id"] for n in nodes.values() if not n["children"]]

    # bottom-up roll-up
    rolled = {}

    def rollup(iid):
        if iid in rolled:
            return rolled[iid]
        n = nodes[iid]
        if not n["children"]:
            rolled[iid] = n["value"] if n["value"] is not None else 0.0
        else:
            rolled[iid] = sum(rollup(c) for c in n["children"])
        return rolled[iid]

    for r in roots:
        rollup(r)

    # 100% rule
    violations = []
    for n in nodes.values():
        if not n["children"] or n["value"] is None:
            continue
        child_total = sum(rolled[c] for c in n["children"])
        diff = child_total - n["value"]
        if abs(diff) > max(tolerance, abs(n["value"]) * tolerance):
            violations.append({
                "id": n["id"],
                "name": n["name"],
                "stated": round(n["value"], 2),
                "children_total": round(child_total, 2),
                "difference": round(diff, 2),
                "issue": "children exceed the parent -- work is double-counted or the parent is understated"
                         if diff > 0 else
                         "children fall short of the parent -- work is missing from the breakdown",
            })

    shallow = [
        {"id": nodes[l]["id"], "name": nodes[l]["name"]}
        for l in leaves if nodes[l]["level"] <= 1 and len(nodes) > 1
    ]

    flags = []
    if orphans:
        flags.append(f"{len(orphans)} item(s) reference a parent that does not exist -- the WBS is not connected.")
    for v in violations:
        flags.append(
            f"100% rule broken at '{v['name']}': children total {v['children_total']:,.2f} "
            f"against a stated {v['stated']:,.2f} ({v['difference']:+,.2f}) -- {v['issue']}."
        )
    if shallow:
        flags.append(
            f"{len(shallow)} top-level item(s) were never decomposed "
            f"({', '.join(s['name'] for s in shallow[:3])}) -- a work package that large is "
            f"usually estimated badly."
        )
    if not violations and not orphans:
        flags.append(f"WBS is internally consistent: {len(leaves)} work packages roll up cleanly.")

    return {
        "value_label": value_label,
        "item_count": len(nodes),
        "roots": roots,
        "work_packages": [
            {"id": nodes[l]["id"], "name": nodes[l]["name"],
             "level": nodes[l]["level"], "value": rolled[l]}
            for l in sorted(leaves, key=lambda x: nodes[x]["id"])
        ],
        "rollup": {iid: round(v, 2) for iid, v in sorted(rolled.items())},
        "total": round(sum(rolled[r] for r in roots), 2),
        "max_depth": max(n["level"] for n in nodes.values()),
        "orphans": orphans,
        "hundred_percent_violations": violations,
        "undecomposed": shallow,
        "flags": flags,
    }


def detect_scope_creep(baseline: list, current: list, value_label: str = "cost") -> dict:
    """Compare an approved WBS baseline against the current one."""
    if not baseline or not current:
        raise WBSError("Both a baseline and a current WBS are required")

    b = {str(r["id"]): r for r in baseline}
    c = {str(r["id"]): r for r in current}

    added = [{"id": i, "name": c[i].get("name", i), "value": c[i].get("value")} for i in c if i not in b]
    removed = [{"id": i, "name": b[i].get("name", i), "value": b[i].get("value")} for i in b if i not in c]
    changed = []
    for i in c:
        if i not in b:
            continue
        bv, cv = b[i].get("value"), c[i].get("value")
        if bv is None or cv is None:
            continue
        if abs(float(cv) - float(bv)) > 1e-9:
            changed.append({
                "id": i, "name": c[i].get("name", i),
                "from": float(bv), "to": float(cv),
                "delta": round(float(cv) - float(bv), 2),
            })

    b_total = sum(float(r["value"]) for r in baseline if r.get("value") is not None)
    c_total = sum(float(r["value"]) for r in current if r.get("value") is not None)
    growth = c_total - b_total
    growth_pct = (growth / b_total * 100) if b_total else None

    flags = []
    if added:
        flags.append(
            f"{len(added)} item(s) were added after baseline "
            f"({', '.join(a['name'] for a in added[:3])}{'...' if len(added) > 3 else ''}) -- "
            f"each needs an approved change request, or this is scope creep."
        )
    if removed:
        flags.append(f"{len(removed)} baselined item(s) are gone from the current WBS -- descoped, or dropped by accident?")
    if changed:
        flags.append(f"{len(changed)} item(s) were re-estimated against baseline.")
    if growth_pct is not None and abs(growth_pct) > 1e-9:
        flags.append(f"Total {value_label} moved {growth:+,.2f} against baseline ({growth_pct:+.1f}%).")
    if not (added or removed or changed):
        flags.append("Current WBS matches the approved baseline -- no scope change detected.")

    return {
        "value_label": value_label,
        "baseline_total": round(b_total, 2),
        "current_total": round(c_total, 2),
        "growth": round(growth, 2),
        "growth_percent": round(growth_pct, 2) if growth_pct is not None else None,
        "added": added,
        "removed": removed,
        "changed": changed,
        "flags": flags,
    }
