"""
Secret detection for source, diffs and chat text.

Written because a real key was pasted into a chat during this project, which
is the ordinary way credentials leak -- not an attacker, just a hurry.

Two design points that matter:

  * Placeholders must not fire. `.env.example` exists to be committed and is
    full of things shaped like secrets. A scanner that cries wolf on
    `sk-ant-your-key` gets switched off within a day, and then it protects
    nothing.
  * Entropy backs up the patterns. A provider prefix catches known formats;
    Shannon entropy over a long opaque string catches the ones with no
    recognisable prefix, which is most internal tokens.

`scan_text` returns findings with the secret itself redacted, so the scanner's
own output is safe to paste into a ticket or a CI log.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import List, Optional

# Known provider formats. Ordered most specific first.
PATTERNS = [
    # Google keys are AIza + 35, but a scanner should err wide: a missed key
    # costs more than a redundant warning on something already placeholder-filtered.
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), "Google / Gemini API key"),
    ("google_oauth_token", re.compile(r"\bAQ\.[A-Za-z0-9_\-]{20,}\b"), "Google short-lived auth token"),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{24,}\b"), "Anthropic API key"),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), "OpenAI-style API key"),
    ("slack_bot_token", re.compile(r"\bxoxb-\d{8,}-\d{8,}-[A-Za-z0-9]{16,}\b"), "Slack bot token"),
    ("slack_app_token", re.compile(r"\bxapp-\d-[A-Z0-9]{8,}-\d{8,}-[a-f0-9]{32,}\b"), "Slack app token"),
    ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "GitHub personal access token"),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b"), "GitHub fine-grained PAT"),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "AWS access key id"),
    ("azure_client_secret", re.compile(r"\b[A-Za-z0-9~_\-.]{3}8Q~[A-Za-z0-9~_\-.]{34}\b"), "Azure client secret"),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"), "Private key block"),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), "JSON Web Token"),
]

# An explicit, greppable opt-out for deliberate fixtures. Without one, the
# scanner's own test suite cannot be committed, and a tool that blocks its own
# tests gets bypassed with --no-verify as a habit -- which is worse than the
# occasional fixture.
ALLOWLIST = re.compile(r"pragma:\s*allowlist\s+secret", re.IGNORECASE)

# Anything that looks like a secret but is obviously a stand-in.
PLACEHOLDER = re.compile(
    r"your[-_]?(key|token|secret)|replace[-_]?with|example|placeholder|dummy|sample|"
    # x{6,} rather than xxx+ -- three x's appear inside real random strings
    r"x{6,}|\.\.\.|<[^>]+>|changeme|redacted|\*{4,}|fake",
    re.IGNORECASE,
)

# assignment to a secret-ish name, used for the entropy pass
ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(?P<name>[A-Za-z0-9_.\-]*(?:secret|token|passwd|password|api[_-]?key|access[_-]?key|
       client[_-]?secret|private[_-]?key|credential)[A-Za-z0-9_.\-]*)
    \s*[:=]\s*
    ['"]?(?P<value>[A-Za-z0-9_\-./+=~]{16,})['"]?
    """,
)

ENTROPY_THRESHOLD = 3.6          # bits per character
MIN_ENTROPY_LENGTH = 24


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def redact(secret: str) -> str:
    """Keep just enough to recognise which key it was."""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * 8}{secret[-4:]} ({len(secret)} chars)"


@dataclass
class Finding:
    kind: str
    description: str
    line: int
    redacted: str
    entropy: float
    source: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _is_placeholder(value: str, line_text: str) -> bool:
    return bool(PLACEHOLDER.search(value) or PLACEHOLDER.search(line_text))


def scan_text(text: str, source: str = None, use_entropy: bool = True) -> List[Finding]:
    findings: List[Finding] = []
    seen = set()

    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOWLIST.search(line):
            continue
        for kind, pattern, description in PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                if _is_placeholder(value, line):
                    continue
                key = (kind, value)
                if key in seen:
                    continue
                seen.add(key)
                findings.append(Finding(kind, description, lineno, redact(value),
                                        round(shannon_entropy(value), 2), source))

        if not use_entropy:
            continue
        for match in ASSIGNMENT.finditer(line):
            value = match.group("value")
            if len(value) < MIN_ENTROPY_LENGTH or _is_placeholder(value, line):
                continue
            ent = shannon_entropy(value)
            if ent < ENTROPY_THRESHOLD:
                continue
            if any(value in f.redacted or f.line == lineno for f in findings):
                continue
            if ("high_entropy", value) in seen:
                continue
            seen.add(("high_entropy", value))
            findings.append(Finding(
                "high_entropy_assignment",
                f"High-entropy value assigned to '{match.group('name')}'",
                lineno, redact(value), round(ent, 2), source,
            ))

    return findings


def scan_diff(diff: str) -> List[Finding]:
    """Only added lines matter -- a secret already in history is a different problem."""
    added = []
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added.append(line[1:])
        else:
            added.append("")          # keep line numbers aligned with the diff
    return scan_text("\n".join(added), source="diff")


def format_findings(findings: List[Finding]) -> str:
    if not findings:
        return "No secrets detected."
    out = [f"{len(findings)} possible secret(s) detected:"]
    for f in findings:
        where = f"{f.source}:{f.line}" if f.source else f"line {f.line}"
        out.append(f"  {where}  {f.description}  {f.redacted}  entropy {f.entropy}")
    return "\n".join(out)
