import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.parsers import parse_tasks_csv, parse_scoring_csv, parse_cost_csv, detect_and_parse

SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "demo", "sample_data")


def _load(name):
    with open(os.path.join(SAMPLE_DIR, name)) as f:
        return f.read()


def test_parse_tasks_csv():
    hint = parse_tasks_csv(_load("tasks.csv"))
    assert hint["name"] == "run_schedule_analysis"
    tasks = hint["input"]["tasks"]
    assert len(tasks) == 8
    f_task = next(t for t in tasks if t["id"] == "F")
    assert set(f_task["predecessors"]) == {"D", "E"}
    print("test_parse_tasks_csv PASSED")


def test_parse_scoring_csv():
    hint = parse_scoring_csv(_load("scoring.csv"))
    assert hint["name"] == "run_scoring_analysis"
    assert len(hint["input"]["criteria"]) == 5
    opt1 = next(o for o in hint["input"]["options"] if o["name"] == "Option #1")
    assert opt1["scores"]["Criteria 1"] == 100
    print("test_parse_scoring_csv PASSED")


def test_parse_cost_csv():
    hint = parse_cost_csv(_load("cost.csv"))
    assert hint["name"] == "run_cost_analysis"
    assert hint["input"]["bac"] == 120000
    print("test_parse_cost_csv PASSED")


def test_detect_and_parse():
    assert detect_and_parse("tasks.csv", _load("tasks.csv"))["name"] == "run_schedule_analysis"
    assert detect_and_parse("scoring.csv", _load("scoring.csv"))["name"] == "run_scoring_analysis"
    assert detect_and_parse("cost.csv", _load("cost.csv"))["name"] == "run_cost_analysis"
    print("test_detect_and_parse PASSED")


if __name__ == "__main__":
    test_parse_tasks_csv()
    test_parse_scoring_csv()
    test_parse_cost_csv()
    test_detect_and_parse()
    print("ALL PARSER TESTS PASSED")
