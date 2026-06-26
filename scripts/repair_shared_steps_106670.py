"""Repair S106670 cases that have empty '- shared_step:' entries.

Root cause: build_testrail_preconditions dropped string params (e.g. shared_step: "Slug")
before the fix in commit <tbd>. This script re-parses the source suite 56195 (BDD: MoIP)
and updates the affected cases in S106670 with correctly-formed preconditions.
"""

import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# bdd_migrator is in frontend/
_FRONTEND = Path(__file__).parent.parent / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))

from easybdd.services.testrail_service import TestRailService
from easybdd.core.testrail_utils import build_testrail_preconditions
from easybdd.core.suite_converter import _sanitize

SOURCE_PROJECT  = 81
SOURCE_SUITE_ID = 56195   # BDD: MoIP (mybdd format)
TARGET_SUITE_ID = 106670  # EASY_BDD: MoIP Smoke Test Suite

DRY_RUN = "--live" not in sys.argv  # default: dry-run; pass --live to actually update


def _strip_prefix(title: str) -> str:
    for prefix in ("Feature:", "Shared:", "Given:", "Var:", "Test:", "Setup:", "Teardown:"):
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title.strip()


def _get_field(case, field):
    import html
    val = case.get(field) or ""
    return html.unescape(str(val)).strip() if val else ""


def _parse_steps(body: str):
    from bdd_migrator import parse_step_block
    steps, _data = parse_step_block(body or "")
    return steps


def _needs_repair(preconds: str) -> bool:
    """Return True if the case preconditions have any known artifact pattern."""
    for line in preconds.splitlines():
        stripped = line.strip()
        # Empty shared_step reference (name was dropped)
        if stripped == "- shared_step:":
            return True
        # Python dict repr written instead of YAML (data row artifact)
        if stripped.startswith("- {'") or stripped.startswith('- {"'):
            return True
    return False


def main():
    tr = TestRailService()

    print(f"Fetching source cases from suite {SOURCE_SUITE_ID}...")
    source_cases = tr.get_cases(SOURCE_PROJECT, SOURCE_SUITE_ID)
    print(f"  {len(source_cases)} source cases")

    print(f"Fetching target cases from suite {TARGET_SUITE_ID}...")
    target_cases = tr.get_cases(SOURCE_PROJECT, TARGET_SUITE_ID)
    print(f"  {len(target_cases)} target cases")

    def _normalize(title: str) -> str:
        """Normalize title for matching: lowercase, spaces/underscores both → _."""
        import re
        return re.sub(r"[\s_]+", "_", title.lower()).strip("_")

    # Build lookup: normalized_clean_title → source case
    source_by_title = {}
    for c in source_cases:
        role_title = _strip_prefix(c["title"])
        source_by_title[_normalize(role_title)] = c

    repaired = 0
    skipped  = 0
    errors   = 0

    for target_case in target_cases:
        title = target_case["title"]
        role_prefix = title.split(":")[0] + ":" if ":" in title else ""
        if role_prefix not in ("Feature:", "Shared:"):
            continue

        # Fetch full case to get preconditions
        full_target = tr.get_case(target_case["id"])
        preconds = full_target.get("custom_preconds") or ""
        if not _needs_repair(preconds):
            skipped += 1
            continue

        clean_title = _strip_prefix(title)
        source_case = source_by_title.get(_normalize(clean_title))
        if not source_case:
            print(f"  [WARN] No source case found for: {title!r}")
            errors += 1
            continue

        # Fetch full source case body
        full_source = tr.get_case(source_case["id"])
        source_body = _get_field(full_source, "custom_preconds")

        # Re-parse source steps with bdd_migrator (now fixed)
        try:
            steps = _parse_steps(source_body)
        except Exception as exc:
            print(f"  [ERROR] parse failed for {title!r}: {exc}")
            errors += 1
            continue

        if not steps:
            print(f"  [SKIP] No steps parsed for {title!r}")
            skipped += 1
            continue

        if role_prefix == "Feature:":
            # Feature: cases use flush-left numbered format
            new_preconds = build_testrail_preconditions(steps)
        else:
            # Shared: cases in S106670 were also repaired to flush-left format
            new_preconds = build_testrail_preconditions(steps)

        if DRY_RUN:
            print(f"  [DRY] Would update [{target_case['id']}] {title!r}")
            print(f"        Steps: {len(steps)}")
            # Show the diff for shared_step lines
            old_lines = [l for l in preconds.splitlines() if "shared_step" in l]
            new_lines = [l for l in new_preconds.splitlines() if "shared_step" in l]
            for o, n in zip(old_lines, new_lines):
                if o != n:
                    print(f"        - {o!r}")
                    print(f"        + {n!r}")
        else:
            try:
                tr.update_case(target_case["id"], custom_preconds=new_preconds)
                print(f"  [FIXED] [{target_case['id']}] {title!r} ({len(steps)} steps)")
            except Exception as exc:
                print(f"  [ERROR] update failed for {title!r}: {exc}")
                errors += 1
                continue

        repaired += 1

    print(f"\nDone — repaired: {repaired}, skipped: {skipped}, errors: {errors}")
    if DRY_RUN:
        print("\nThis was a DRY RUN. Pass --live to actually update the cases.")


if __name__ == "__main__":
    main()
