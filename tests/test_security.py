"""Secret detection and credential lifecycle."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from security.secret_scan import scan_text, scan_diff, redact, shannon_entropy
from security.credentials import (assess, cross_reference, transition,
                                  can_transition, CredentialError)


# ------------------------------------------------------------------ scanning

def test_known_provider_formats_are_classified_not_just_flagged():
    text = "\n".join([
        "GEMINI_API_KEY=AIzaSyC8kPqR3mNvX2wL9tYbH4jD6fA1sZ7eQ",  # pragma: allowlist secret
        "gh = ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",  # pragma: allowlist secret
        "-----BEGIN RSA PRIVATE KEY-----",  # pragma: allowlist secret
    ])
    kinds = {f.kind for f in scan_text(text)}
    assert {"google_api_key", "github_pat", "private_key_block"} <= kinds


def test_the_token_format_that_was_actually_pasted_is_caught():
    """Regression: a real AQ.-prefixed Google token reached a chat log."""
    f = scan_text("token = AQ.Sy7nQwErTyUiOpAsDfGhJkLzXcVbNmQwErTyUiOpAs")  # pragma: allowlist secret
    assert any(x.kind == "google_oauth_token" for x in f)


def test_placeholders_never_fire():
    """A scanner that cries wolf on .env.example gets switched off."""
    text = "\n".join([
        "ANTHROPIC_API_KEY=sk-ant-your-key",
        "SLACK_BOT_TOKEN=xoxb-your-bot-token",
        "MICROSOFT_APP_ID=REPLACE_WITH_MICROSOFT_APP_ID",
        "password=changeme",
        "key=<your-key-here>",
    ])
    assert scan_text(text) == []


def test_the_repo_s_own_env_example_is_clean():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, ".env.example")) as fh:
        assert scan_text(fh.read(), source=".env.example") == []


def test_high_entropy_assignment_catches_unknown_formats():
    f = scan_text('internal_service_token = "f3Kq9Lm2Xp7Rv4Tz8Nb1Hd6Yw0Cs5Ja"')  # pragma: allowlist secret
    assert any(x.kind == "high_entropy_assignment" for x in f)


def test_ordinary_prose_and_low_entropy_values_do_not_fire():
    text = 'note = "the quick brown fox jumps over the lazy dog again and again"\n' \
           'api_key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaa"'
    assert scan_text(text) == []


def test_findings_are_redacted_so_the_output_is_safe_to_paste():
    f = scan_text("k=AIzaSyC8kPqR3mNvX2wL9tYbH4jD6fA1sZ7eQ")[0]  # pragma: allowlist secret
    assert "AIzaSyC8kPqR3mNvX2wL9tYbH4jD6fA1sZ7eQ" not in f.redacted  # pragma: allowlist secret
    assert f.redacted.startswith("AIza") and "*" in f.redacted


def test_diff_scan_only_looks_at_added_lines():
    diff = ("--- a/x\n+++ b/x\n"
            "-GEMINI_API_KEY=AIzaSyC8kPqR3mNvX2wL9tYbH4jD6fA1sZ7eQ\n"  # pragma: allowlist secret
            "+GEMINI_API_KEY=\n")
    assert scan_diff(diff) == [], "a secret being REMOVED must not block the commit"


def test_entropy_is_actually_measured():
    assert shannon_entropy("aaaaaaaa") < 1.0
    assert shannon_entropy("f3Kq9Lm2Xp7Rv4Tz8Nb1Hd6Yw0Cs5Ja") > 4.0  # pragma: allowlist secret


# --------------------------------------------------------------- lifecycle

def test_illegal_transitions_are_refused():
    assert not can_transition("expired", "active")
    with pytest.raises(CredentialError, match="cannot go expired -> active"):
        transition({"name": "k", "state": "expired"}, "active")


def test_revoked_is_terminal():
    for target in ("active", "rotated", "issued", "expiring"):
        assert not can_transition("revoked", target)


def test_legal_transition_records_who_and_why():
    out = transition({"name": "k", "state": "active"}, "rotated",
                     reason="leaked in chat", today="2026-09-12")
    assert out["state"] == "rotated"
    assert out["history"][-1] == {"from": "active", "to": "rotated",
                                  "reason": "leaked in chat", "on": "2026-09-12"}


def test_state_is_derived_from_the_calendar_not_the_record():
    """The stored state is what goes stale, so dates win."""
    r = assess([{"id": "k", "name": "k", "state": "active", "expires": "2026-08-01"}],
               today="2026-09-12")
    c = r["credentials"][0]
    assert c["recorded_state"] == "active" and c["state"] == "expired"
    assert c["state_drifted"]


def test_expiring_window_is_respected():
    r = assess([{"id": "k", "name": "k", "state": "active", "expires": "2026-09-20"}],
               today="2026-09-12")
    assert r["credentials"][0]["state"] == "expiring"


def test_open_task_using_an_unusable_credential_is_high_severity():
    r = cross_reference(
        [{"id": "old", "name": "old key", "state": "rotated", "expires": "2027-01-01"}],
        [{"id": "T-1", "name": "sync", "uses": ["old"], "status": "open"}],
        today="2026-09-12")
    p = [x for x in r["task_problems"] if x["task"] == "T-1"]
    assert p and p[0]["severity"] == "high"


def test_reference_to_an_untracked_credential_is_reported():
    r = cross_reference(
        [{"id": "a", "name": "a", "state": "active", "expires": "2027-01-01"}],
        [{"id": "T-9", "name": "job", "uses": ["ghost"], "status": "open"}],
        today="2026-09-12")
    assert any("not \nin the register" in p["message"].replace("\n", "") or
               "not in the register" in p["message"] for p in r["task_problems"])


def test_closed_tasks_are_not_flagged():
    r = cross_reference(
        [{"id": "old", "name": "old", "state": "revoked", "expires": "2027-01-01"}],
        [{"id": "T-2", "name": "done", "uses": ["old"], "status": "closed"}],
        today="2026-09-12")
    assert r["task_problems"] == []


def test_unowned_credential_is_flagged():
    r = assess([{"id": "k", "name": "k", "state": "active", "expires": "2027-01-01"}],
               today="2026-09-12")
    assert any("no owner" in a["message"] for a in r["alerts"])
