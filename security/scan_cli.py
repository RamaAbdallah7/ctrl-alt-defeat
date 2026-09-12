#!/usr/bin/env python3
"""
Secret scanner CLI.

  python security/scan_cli.py --staged      what you are about to commit
  python security/scan_cli.py --tree        the whole working tree
  python security/scan_cli.py --history     every commit (slow)
  python security/scan_cli.py FILE [FILE..]

Exits non-zero when something is found, so it works as a pre-commit hook or
a CI gate. Findings are printed redacted -- the output is safe to paste.
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.secret_scan import scan_text, scan_diff, format_findings

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".zip", ".pdf", ".ico", ".woff", ".woff2"}


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout


def scan_staged():
    return scan_diff(_git("diff", "--cached", "-U0"))


def scan_history():
    return scan_diff(_git("log", "--all", "-p", "-U0"))


def scan_tree(root="."):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in SKIP_EXT:
                continue
            path = os.path.join(dirpath, name)
            found.extend(scan_file(path))
    return found


def scan_file(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return scan_text(fh.read(), source=os.path.relpath(path))
    except (OSError, UnicodeDecodeError):
        return []


def main():
    ap = argparse.ArgumentParser(description="Find credentials before they leave the machine.")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--tree", action="store_true")
    ap.add_argument("--history", action="store_true")
    args = ap.parse_args()

    if args.staged:
        findings, what = scan_staged(), "staged changes"
    elif args.history:
        findings, what = scan_history(), "full git history"
    elif args.tree:
        findings, what = scan_tree(), "working tree"
    elif args.files:
        findings, what = [f for p in args.files for f in scan_file(p)], "the given files"
    else:
        findings, what = scan_staged(), "staged changes"

    print(f"Scanned {what}.")
    print(format_findings(findings))
    if findings:
        print()
        print("If one of these is real: rotate it first, then remove it. A key that")
        print("reached a commit, a log or a chat should be treated as already public.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
