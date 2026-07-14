"""Add missing B-900 shared step cases from suite 56195 to suite 106670.

The suite_converter already converted B-960 cases but missed B-900 cases.
This script finds all B-900/rev_B-900 Shared: cases in source suite 56195,
converts them to Easy BDD YAML format, and creates them in section 2884782
(Extended Firmware Resiliency) of suite 106670.
"""

import os
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
from easybdd.core.testrail_utils import build_testrail_preconditions
from easybdd.core.suite_converter import _sanitize

SOURCE_PROJECT  = 81
SOURCE_SUITE_ID = 56195
TARGET_SUITE_ID = 106670
TARGET_SECTION  = 2884782  # Extended Firmware Resiliency

DRY_RUN  = "--live"    not in sys.argv
UPDATE   = "--update"  in sys.argv  # re-generate already-existing cases


def _strip_prefix(title: str) -> str:
    for prefix in ("Feature:", "Shared:", "Given:", "Var:", "Test:", "Setup:", "Teardown:"):
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title.strip()


def _normalize(title: str) -> str:
    return re.sub(r"[\s_-]+", "_", title.lower()).strip("_")


def _get_field(case, field):
    import html
    val = case.get(field) or ""
    return html.unescape(str(val)).strip() if val else ""


def _parse_steps(body: str):
    from bdd_migrator import parse_step_block
    steps, _data = parse_step_block(body or "")
    return steps


def main():
    tr = TestRailService()

    print(f"Fetching source cases from suite {SOURCE_SUITE_ID}...")
    source_cases = tr.get_cases(SOURCE_PROJECT, SOURCE_SUITE_ID)
    print(f"  {len(source_cases)} source cases")

    print(f"Fetching target cases from suite {TARGET_SUITE_ID}...")
    target_cases = tr.get_cases(SOURCE_PROJECT, TARGET_SUITE_ID)
    print(f"  {len(target_cases)} target cases")

    # Build lookup: normalized title → existing target case id
    target_by_norm = {}
    for c in target_cases:
        if c["title"].startswith("Shared:"):
            target_by_norm[_normalize(_strip_prefix(c["title"]))] = c

    # Find B-900 / rev_B-900 source cases
    b900_source = [
        c for c in source_cases
        if c["title"].startswith("Shared:")
        and re.search(r"[Bb]-900|rev_[Bb]-900", c["title"])
    ]
    print(f"\nFound {len(b900_source)} B-900/rev_B-900 source cases")

    to_process = []
    for c in b900_source:
        norm = _normalize(_strip_prefix(c["title"]))
        existing = target_by_norm.get(norm)
        if existing is None:
            to_process.append((c, None))  # create
        elif UPDATE:
            to_process.append((c, existing))  # update

    action_label = "create/update" if UPDATE else "create"
    print(f"Cases to {action_label}: {len(to_process)}")
    if not to_process:
        hint = " (pass --update to regenerate existing cases)" if not UPDATE else ""
        print(f"Nothing to do.{hint}")
        return

    created = 0
    updated = 0
    skipped = 0
    errors  = 0

    for src, existing_target in to_process:
        title = src["title"]
        clean = _strip_prefix(title)
        # Convert spaces to underscores for Easy BDD title convention
        easy_title = "Shared: " + re.sub(r"\s+", "_", clean)

        full_src = tr.get_case(src["id"])
        body = _get_field(full_src, "custom_preconds")

        try:
            steps = _parse_steps(body)
        except Exception as exc:
            print(f"  [ERROR] parse failed for {title!r}: {exc}")
            errors += 1
            continue

        if not steps:
            print(f"  [SKIP] No steps parsed for {title!r}")
            skipped += 1
            continue

        new_preconds = build_testrail_preconditions(steps)

        if DRY_RUN:
            op = "update" if existing_target else "create"
            print(f"  [DRY] Would {op}: {easy_title!r} ({len(steps)} steps)")
            print(f"        Preview:\n{new_preconds[:300]}...")
        elif existing_target:
            try:
                tr.update_case(existing_target["id"], custom_preconds=new_preconds)
                print(f"  [UPDATED] [{existing_target['id']}] {easy_title!r} ({len(steps)} steps)")
                updated += 1
            except Exception as exc:
                print(f"  [ERROR] update failed for {easy_title!r}: {exc}")
                errors += 1
                continue
        else:
            try:
                result = tr.add_case(
                    TARGET_SECTION,
                    title=easy_title,
                    custom_preconds=new_preconds,
                )
                print(f"  [CREATED] [{result['id']}] {easy_title!r} ({len(steps)} steps)")
                created += 1
            except Exception as exc:
                print(f"  [ERROR] create failed for {easy_title!r}: {exc}")
                errors += 1
                continue

    if DRY_RUN:
        n = len(to_process) - skipped - errors
        print(f"\nDone — would process: {n}, skipped: {skipped}, errors: {errors}")
        print("\nThis was a DRY RUN. Pass --live to actually apply the changes.")
    else:
        print(f"\nDone — created: {created}, updated: {updated}, skipped: {skipped}, errors: {errors}")


if __name__ == "__main__":
    main()
