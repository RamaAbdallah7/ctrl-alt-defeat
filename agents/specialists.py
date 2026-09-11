"""
The Tarteeb specialist roster.

Each specialist is a named agent with one mandate, a fixed set of tools it
owns, and its own voice when it reports a finding. The router decides which
of them a request wakes; the Executive Orchestrator consolidates whoever
reported. Nothing here does arithmetic -- every number a specialist quotes
comes from a deterministic engine in engines/.

Keeping the roster in one place means the Slack surface, the web console,
the CLI demo and the audit trail all name the same agents the same way.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List


@dataclass(frozen=True)
class Specialist:
    key: str            # domain key used in specialist_outputs
    name: str           # what it is called in a brief
    role: str           # one-line job title
    mandate: str        # what it is responsible for
    tools: List[str]    # tool names the router can use to wake it
    summarize: Callable  # (result: dict) -> str, its own reported finding


def _schedule(r):
    path = " -> ".join(r["critical_path"])
    slack = [t for t in r["tasks"] if not t["is_critical"]]
    worst = max(slack, key=lambda t: t["total_float"]) if slack else None
    line = (f"The project runs {r['project_duration']:g} days. The critical path is "
            f"{path} -- every day lost on those tasks is a day lost on the project.")
    if worst:
        line += (f" The most flexible task is {worst['name']} with "
                 f"{worst['total_float']:g} days of total float.")
    return line


def _compression(r):
    if not r["periods_saved"]:
        return ("The schedule cannot be bought shorter: no activity on the critical path "
                "has crash data with room left to shorten.")
    paths = r.get("final_critical_paths") or [r["final_critical_path"]]
    if len(paths) > 1:
        tail = (f"After compressing, {len(paths)} paths are critical at once "
                f"({'; '.join(' -> '.join(p) for p in paths)}) -- every one of them now has to "
                f"hold, so there is no slack left anywhere to absorb a slip.")
    else:
        tail = f"After compressing, the critical path becomes {' -> '.join(paths[0])}."
    return (f"The schedule can be compressed from {r['baseline_duration']:g} to "
            f"{r['final_duration']:g} periods -- {r['periods_saved']:g} saved for "
            f"{r['total_crash_cost']:,.0f}, about {r['cost_per_period_saved']:,.0f} per period. "
            + tail)


def _fast_track(r):
    if not r["candidates"]:
        return "There are no sequential critical-path activities available to overlap."
    b = r["candidates"][0]
    return (f"The best overlap is '{b['predecessor_name']}' with '{b['successor_name']}', "
            f"worth up to {b['potential_saving']:g} periods. This buys time with risk rather "
            f"than money: {b['risk']}")


def _cost(r):
    line = (f"CPI is {r['cpi']:.2f} and SPI is {r['spi']:.2f}, so the project has earned "
            f"{r['ev']:,.0f} of value against {r['ac']:,.0f} spent. At the current burn rate "
            f"the estimate at completion is {r['eac']:,.0f} against a {r['bac']:,.0f} budget "
            f"({r['vac']:+,.0f}).")
    if r.get("tcpi_bac"):
        line += (f" To still land on budget the remaining work must run at a TCPI of "
                 f"{r['tcpi_bac']:.2f}.")
    if r.get("estimated_duration"):
        line += (f" On schedule performance the forecast is {r['estimated_duration']:.1f} "
                 f"against {r['planned_duration']:.0f} planned.")
    return line


def _investment(r):
    pay = f"year {r['payback_year']:.2f}" if r["payback_year"] is not None else "never, within the years given"
    return (f"At a {r['discount_rate']:.0%} discount rate the net present value is "
            f"{r['npv']:,.0f} on {r['total_discounted_cost']:,.0f} of discounted cost, an ROI of "
            f"{r['roi']:.1%}, paying back in {pay}.")


def _estimation(r):
    line = (f"The three-point expectation is {r['expected_total']:g} {r['unit']} with a standard "
            f"deviation of {r['standard_deviation']:g}; 95% of outcomes fall between "
            f"{r['range_95'][0]:g} and {r['range_95'][1]:g}.")
    if r["probability_within_target"] is not None:
        line += (f" The chance of coming in within {r['target']:g} is "
                 f"{r['probability_within_target']:.0%}.")
    return line


def _estimate_band(r):
    line = (f"That is a {r['type'].upper()} estimate, which carries a {r['low_percent']:+.0%} to "
            f"{r['high_percent']:+.0%} range -- {r['estimate']:,.0f} honestly means "
            f"{r['range_low']:,.0f} to {r['range_high']:,.0f}.")
    if r["budget_within_range"] is False:
        line += " The budget quoted sits outside that range."
    return line


def _scope(r):
    if r["hundred_percent_violations"]:
        v = r["hundred_percent_violations"][0]
        return (f"The breakdown does not add up: '{v['name']}' states {v['stated']:,.0f} but its "
                f"children total {v['children_total']:,.0f} ({v['difference']:+,.0f}). "
                f"{len(r['work_packages'])} work packages across {r['max_depth']} levels.")
    return (f"The breakdown is internally consistent: {len(r['work_packages'])} work packages "
            f"across {r['max_depth']} levels rolling up to {r['total']:,.0f}.")


def _scope_creep(r):
    if not (r["added"] or r["removed"] or r["changed"]):
        return "The current breakdown matches the approved baseline -- no scope change."
    bits = []
    if r["added"]:
        bits.append(f"{len(r['added'])} item(s) added ({', '.join(a['name'] for a in r['added'][:2])})")
    if r["removed"]:
        bits.append(f"{len(r['removed'])} removed")
    if r["changed"]:
        bits.append(f"{len(r['changed'])} re-estimated")
    growth = (f" Total moved {r['growth']:+,.0f} ({r['growth_percent']:+.1f}%) against baseline."
              if r["growth_percent"] is not None else "")
    return ("Against the approved baseline: " + ", ".join(bits) + "." + growth +
            " Anything added without an approved change request is scope creep.")


def _decision(r):
    top = r["ranked_options"][0]
    line = f"{top['option']} ranks first on the weighted criteria with {top['weighted_score']:g}."
    if len(r["ranked_options"]) > 1:
        second = r["ranked_options"][1]
        gap = top["weighted_score"] - second["weighted_score"]
        if gap < 5:
            line += (f" But {second['option']} scores {second['weighted_score']:g} -- a gap of "
                     f"{gap:g} points is inside the noise of the weights, so this is effectively "
                     f"a tie and should not be decided on the score alone.")
        else:
            line += f" {second['option']} follows at {second['weighted_score']:g}, {gap:g} points back."
    if r.get("warnings"):
        line += " " + " ".join(r["warnings"])
    return line


ROSTER = [
    Specialist(
        key="schedule", name="Critical Path Analyst", role="Schedule specialist",
        mandate="Works out when the project actually finishes, which tasks drive that date, "
                "and where the slack is.",
        tools=["run_schedule_analysis"], summarize=_schedule,
    ),
    Specialist(
        key="crashing", name="Schedule Recovery Analyst", role="Compression specialist",
        mandate="Finds the cheapest way to buy back time when the date has to move in.",
        tools=["run_crash_analysis"], summarize=_compression,
    ),
    Specialist(
        key="fast_track", name="Fast-Track Analyst", role="Compression specialist",
        mandate="Finds which sequential work could safely overlap when there is no budget "
                "to crash the schedule.",
        tools=["run_fast_track_analysis"], summarize=_fast_track,
    ),
    Specialist(
        key="cost", name="Earned Value Analyst", role="Cost-control specialist",
        mandate="Measures cost and schedule performance against the baseline and forecasts "
                "where the project lands.",
        tools=["run_cost_analysis"], summarize=_cost,
    ),
    Specialist(
        key="financial", name="Business Case Analyst", role="Investment specialist",
        mandate="Answers whether the project is worth doing at all -- NPV, ROI and payback.",
        tools=["run_financial_analysis"], summarize=_investment,
    ),
    Specialist(
        key="pert", name="Estimation Analyst", role="Estimating specialist",
        mandate="Turns uncertain three-point estimates into an expected figure, a spread, "
                "and the odds of hitting a target.",
        tools=["run_pert_analysis"], summarize=_estimation,
    ),
    Specialist(
        key="estimate", name="Estimate Assurance Analyst", role="Estimating specialist",
        mandate="Holds estimates to the accuracy their type actually supports, so an early "
                "figure is never treated as a firm one.",
        tools=["run_estimate_check"], summarize=_estimate_band,
    ),
    Specialist(
        key="wbs", name="Scope Architect", role="Scope specialist",
        mandate="Checks the work breakdown holds together and that the plan accounts for "
                "all of the work and none of it twice.",
        tools=["run_wbs_analysis"], summarize=_scope,
    ),
    Specialist(
        key="scope_creep", name="Baseline Guardian", role="Scope specialist",
        mandate="Watches the current plan against the approved baseline and names what changed "
                "without a change request.",
        tools=["run_scope_creep_analysis"], summarize=_scope_creep,
    ),
    Specialist(
        key="scoring", name="Options Analyst", role="Decision specialist",
        mandate="Runs the weighted decision matrix and says plainly when a 'winner' is really "
                "a tie.",
        tools=["run_scoring_analysis"], summarize=_decision,
    ),
]

BY_KEY = {s.key: s for s in ROSTER}
BY_TOOL = {tool: s for s in ROSTER for tool in s.tools}


def specialist_for_tool(tool_name: str):
    return BY_TOOL.get(tool_name)


def specialist_for_key(key: str):
    return BY_KEY.get(key)


def report(key: str, result: dict) -> str:
    """The named specialist's own finding, in its own voice."""
    s = BY_KEY.get(key)
    if s is None:
        return ""
    try:
        return s.summarize(result)
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        # never let a formatting slip take down a brief
        return "; ".join(result.get("flags", [])) or "Reported, but produced no readable summary."
