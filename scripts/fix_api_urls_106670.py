"""Fix api.request steps in suite 106670 that have relative URLs (missing ${url} prefix).

Every api.request step should use: url: '${url}/path/...'
Cases where url: starts with '/' or doesn't start with '${url}' need to be fixed.
"""

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

_FRONTEND = Path(__file__).parent.parent / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from easybdd.services.testrail_service import TestRailService

TARGET_PROJECT  = 81
TARGET_SUITE_ID = 106670

DRY_RUN = "--live" not in sys.argv


def _fix_preconds(preconds: str) -> tuple[str, int]:
    """Rewrite relative url: lines to use ${url} prefix. Returns (new_preconds, count_fixed).

    Only touches url: lines whose value is a bare relative path starting with '/'.
    Leaves alone: lines already containing '${...}', absolute http(s)://, wss://, etc.
    """
    lines = preconds.splitlines()
    fixed = 0
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("url:") and "${url}" not in stripped:
            m = re.match(r"^(\s*url:\s*)(.*)", line)
            if m:
                val = m.group(2).strip().strip("'\"")
                # Only fix genuine relative paths (start with /)
                if val.startswith("/"):
                    indent = m.group(1)
                    line = f"{indent}'" + "${url}" + f"{val}'"
                    fixed += 1
        out.append(line)
    return "\n".join(out), fixed


def main():
    tr = TestRailService()

    print(f"Fetching cases from suite {TARGET_SUITE_ID}...")
    cases = tr.get_cases(TARGET_PROJECT, TARGET_SUITE_ID)
    print(f"  {len(cases)} cases")

    to_fix = []
    print("Scanning for url: lines missing the ${url} prefix...")
    for c in cases:
        # Var: cases define variables like url: http://..., don't touch them
        if c["title"].startswith("Var:"):
            continue
        full = tr.get_case(c["id"])
        preconds = html.unescape(full.get("custom_preconds") or "")
        if not preconds:
            continue
        has_bad = any(
            l.strip().startswith("url:")
            and "${url}" not in l
            and re.search(r"url:\s*['\"]?/", l)
            for l in preconds.splitlines()
        )
        if has_bad:
            to_fix.append((c, full, preconds))

    print(f"Cases to fix: {len(to_fix)}")
    if not to_fix:
        print("Nothing to do.")
        return

    repaired = 0
    errors = 0

    for c, full, preconds in to_fix:
        new_preconds, count = _fix_preconds(preconds)
        title = c["title"]

        if DRY_RUN:
            print(f"\n  [DRY] [{c['id']}] {title} ({count} url lines fixed)")
            # Show diff of changed lines
            old_lines = preconds.splitlines()
            new_lines = new_preconds.splitlines()
            for o, n in zip(old_lines, new_lines):
                if o != n:
                    print(f"    - {o.strip()}")
                    print(f"    + {n.strip()}")
        else:
            try:
                tr.update_case(c["id"], custom_preconds=new_preconds)
                print(f"  [FIXED] [{c['id']}] {title} ({count} url lines)")
                repaired += 1
            except Exception as exc:
                print(f"  [ERROR] [{c['id']}] {title}: {exc}")
                errors += 1

    if DRY_RUN:
        print(f"\nDone — would fix: {len(to_fix)}, errors: {errors}")
        print("\nThis was a DRY RUN. Pass --live to actually update the cases.")
    else:
        print(f"\nDone — fixed: {repaired}, errors: {errors}")


if __name__ == "__main__":
    main()
