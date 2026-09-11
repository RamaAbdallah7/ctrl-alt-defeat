"""Validate scoring engine against the textbook Weighted Decision Matrix example."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engines.scoring import compute_weighted_scores


def test_textbook_example():
    criteria = [
        {"name": "Criteria 1", "weight": 30},
        {"name": "Criteria 2", "weight": 20},
        {"name": "Criteria 3", "weight": 30},
        {"name": "Criteria 4", "weight": 10},
        {"name": "Criteria 5", "weight": 10},
    ]
    options = [
        {"name": "Option #1", "scores": {"Criteria 1": 100, "Criteria 2": 90, "Criteria 3": 40, "Criteria 4": 70, "Criteria 5": 50}},
        {"name": "Option #2", "scores": {"Criteria 1": 100, "Criteria 2": 100, "Criteria 3": 20, "Criteria 4": 10, "Criteria 5": 10}},
        {"name": "Option #3", "scores": {"Criteria 1": 80, "Criteria 2": 95, "Criteria 3": 10, "Criteria 4": 20, "Criteria 5": 20}},
        {"name": "Option #4", "scores": {"Criteria 1": 10, "Criteria 2": 95, "Criteria 3": 100, "Criteria 4": 100, "Criteria 5": 100}},
    ]
    result = compute_weighted_scores(criteria, options)
    scores_by_name = {r["option"]: r["weighted_score"] for r in result["ranked_options"]}

    expected = {"Option #1": 72, "Option #2": 58, "Option #3": 50, "Option #4": 72}
    for name, exp in expected.items():
        assert abs(scores_by_name[name] - exp) < 0.01, f"{name}: got {scores_by_name[name]}, expected {exp}"

    assert result["ranked_options"][0]["rank"] == 1
    print("test_textbook_example PASSED:", scores_by_name)


def test_missing_score_is_flagged():
    criteria = [{"name": "Cost", "weight": 50}, {"name": "Quality", "weight": 50}]
    options = [{"name": "Vendor A", "scores": {"Cost": 80}}]  # missing Quality
    result = compute_weighted_scores(criteria, options)
    assert any("missing a score" in w for w in result["warnings"])
    print("test_missing_score_is_flagged PASSED:", result["warnings"])


if __name__ == "__main__":
    test_textbook_example()
    test_missing_score_is_flagged()
    print("ALL SCORING TESTS PASSED")
