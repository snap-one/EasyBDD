"""Replace mybdd helper function names in stored Easy BDD YAML in suite 106670.

Fixes cases that were migrated before _translate_code() learned to convert:
  str2dict(...)  ->  json.loads(...)
  get_text(...)  ->  str(...)

These appear inside eval.exec code: lines and must be valid Python for the
runner's exec() context.
"""

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from easy_bdd.services.testrail_service import TestRailService

TARGET_PROJECT  = 81
TARGET_SUITE_ID = 106670

DRY_RUN = "--live" not in sys.argv

_REPLACEMENTS = [
    (re.compile(r"\bgv\.str2dict\b"), "json.loads"),
    (re.compile(r"\bstr2dict\b"),     "json.loads"),
    (re.compile(r"\bgv\.get_text\b"), "str"),
    (re.compile(r"\bget_text\b"),     "str"),
]


def _needs_fix(preconds: str) -> bool:
    return bool(re.search(r"\b(str2dict|get_text)\b", preconds))


def _fix_preconds(preconds: str) -> str:
    for pattern, replacement in _REPLACEMENTS:
        preconds = pattern.sub(replacement, preconds)
    return preconds


def main():
    tr = TestRailService()

    print(f"Fetching cases from suite {TARGET_SUITE_ID}...")
    cases = tr.get_cases(TARGET_PROJECT, TARGET_SUITE_ID)
    print(f"  {len(cases)} cases")

    to_fix = []
    for c in cases:
        full = tr.get_case(c["id"])
        preconds = html.unescape(full.get("custom_preconds") or "")
        if preconds and _needs_fix(preconds):
            to_fix.append((c, preconds))

    print(f"Cases to fix: {len(to_fix)}")
    if not to_fix:
        print("Nothing to do.")
        return

    fixed = 0
    errors = 0

    for c, preconds in to_fix:
        new_preconds = _fix_preconds(preconds)
        title = c["title"]

        # Show what changed
        old_lines = preconds.splitlines()
        new_lines = new_preconds.splitlines()
        changed = [(o, n) for o, n in zip(old_lines, new_lines) if o != n]

        if DRY_RUN:
            print(f"\n  [DRY] [{c['id']}] {title}")
            for o, n in changed:
                print(f"    - {o.strip()}")
                print(f"    + {n.strip()}")
        else:
            try:
                tr.update_case(c["id"], custom_preconds=new_preconds)
                print(f"  [FIXED] [{c['id']}] {title} ({len(changed)} line(s) changed)")
                fixed += 1
            except Exception as exc:
                print(f"  [ERROR] [{c['id']}] {title}: {exc}")
                errors += 1

    if DRY_RUN:
        print(f"\nDone — would fix: {len(to_fix)}, errors: 0")
        print("This was a DRY RUN. Pass --live to apply.")
    else:
        print(f"\nDone — fixed: {fixed}, errors: {errors}")


if __name__ == "__main__":
    main()
