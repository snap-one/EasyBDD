"""Fix variable references that were split incorrectly in suite 106670.

The migrator's dollar-sign regex stops at hyphens, so a source reference like
  $unit_id_B-900-MOIP-4K-RX_D46A9121077B
becomes
  ${unit_id_B}-900-MOIP-4K-RX_D46A9121077B   (WRONG)
instead of
  ${unit_id_B-900-MOIP-4K-RX_D46A9121077B}   (CORRECT)

Strategy:
  1. Load all variable names from Var: cases in the suite.
  2. For every case, scan each line for ${prefix}-suffix patterns.
  3. If prefix+'-'+suffix (or more of the remaining text) matches a known variable, merge.
"""

import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from easybdd.services.testrail_service import TestRailService

TARGET_PROJECT  = 81
TARGET_SUITE_ID = 106670

DRY_RUN = "--live" not in sys.argv

# Matches ${prefix} immediately followed by -more-text (up to quote/whitespace/end)
_SPLIT_VAR = re.compile(r"\$\{([^}]+)\}-([\w][\w.-]*)")


def _load_variables(tr, cases):
    """Return a set of all variable names defined in Var: cases."""
    var_names = set()
    for c in cases:
        if not c["title"].startswith("Var:"):
            continue
        full = tr.get_case(c["id"])
        preconds = html.unescape(full.get("custom_preconds") or "")
        for line in preconds.splitlines():
            m = re.match(r"^\s*(\S+)\s*:", line)
            if m:
                var_names.add(m.group(1))
    return var_names


def _fix_line(line: str, var_names: set) -> str:
    """Merge ${prefix}-suffix into ${prefix-suffix} when the merged name is known."""
    def replacer(m):
        prefix = m.group(1)
        suffix = m.group(2)
        # Try increasingly long merges: prefix-suffix (the full match),
        # but also handle cases where suffix itself contains further hyphens
        # that could belong to more literal text. We greedily try the longest
        # known variable that starts with prefix+'-'.
        candidate = f"{prefix}-{suffix}"
        if candidate in var_names:
            return "${" + candidate + "}"
        # Check if any known var starts with prefix+'-' and the line contains it
        prefix_dash = prefix + "-"
        for v in var_names:
            if v.startswith(prefix_dash) and line[m.start():].startswith(
                "${" + prefix + "}-" + v[len(prefix_dash):]
            ):
                return "${" + v + "}"
        return m.group(0)  # no match found, leave unchanged

    return _SPLIT_VAR.sub(replacer, line)


def _fix_preconds(preconds: str, var_names: set) -> tuple[str, int]:
    lines = preconds.splitlines()
    out = []
    fixed = 0
    for line in lines:
        new = _fix_line(line, var_names)
        if new != line:
            fixed += 1
        out.append(new)
    return "\n".join(out), fixed


def main():
    tr = TestRailService()

    print(f"Fetching cases from suite {TARGET_SUITE_ID}...")
    cases = tr.get_cases(TARGET_PROJECT, TARGET_SUITE_ID)
    print(f"  {len(cases)} cases")

    print("Loading variable names from Var: cases...")
    var_names = _load_variables(tr, cases)
    print(f"  {len(var_names)} variable names loaded")

    to_fix = []
    for c in cases:
        if c["title"].startswith("Var:"):
            continue
        full = tr.get_case(c["id"])
        preconds = html.unescape(full.get("custom_preconds") or "")
        if not preconds:
            continue
        if _SPLIT_VAR.search(preconds):
            # Quick check: does any split candidate merge to a known var?
            new, count = _fix_preconds(preconds, var_names)
            if count:
                to_fix.append((c, preconds, new, count))

    print(f"Cases to fix: {len(to_fix)}")
    if not to_fix:
        print("Nothing to do.")
        return

    fixed = 0
    errors = 0

    for c, old_preconds, new_preconds, count in to_fix:
        title = c["title"]
        old_lines = old_preconds.splitlines()
        new_lines = new_preconds.splitlines()
        changed = [(o, n) for o, n in zip(old_lines, new_lines) if o != n]

        if DRY_RUN:
            print(f"\n  [DRY] [{c['id']}] {title} ({count} line(s))")
            for o, n in changed[:3]:
                print(f"    - {o.strip()}")
                print(f"    + {n.strip()}")
            if len(changed) > 3:
                print(f"    ... and {len(changed) - 3} more")
        else:
            try:
                tr.update_case(c["id"], custom_preconds=new_preconds)
                print(f"  [FIXED] [{c['id']}] {title} ({count} line(s))")
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
