"""Sync Easy BDD TestRail suites to local YAML test files.

Reads Feature:, Shared:, and Var: cases from a TestRail suite (or run) and
writes runnable local YAML files so the same tests can be executed via
`python -m easybdd run` without a TestRail connection.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .testrail_runner import (
    _classify,
    _coerce,
    _extract_inline_data,
    _fix_step_list_indent,
    _html_to_text,
    _strip_prefix,
    _yaml_safe_load_lenient,
)


def _slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", name).lower().strip("_")


def _filename_safe(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_\- ]", "", title)
    slug = re.sub(r"\s+", "_", slug.strip()).lower()
    return slug[:80] or "test"


def _case_id(case: Dict) -> Optional[int]:
    """Return the TestRail case ID whether the object came from get_cases or get_tests."""
    for field in ("case_id", "id"):
        val = case.get(field)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
    return None


class SyncResult:
    def __init__(self) -> None:
        self.written: List[str] = []
        self.skipped: List[Tuple[str, str]] = []
        self.errors: List[Tuple[str, str]] = []

    @property
    def error_count(self) -> int:
        return len(self.errors)

    def print_summary(self) -> None:
        print(f"\nSync complete:")
        print(f"  Written : {len(self.written)}")
        print(f"  Skipped : {len(self.skipped)}")
        print(f"  Errors  : {len(self.errors)}")
        if self.errors:
            print("\nErrors:")
            for title, err in self.errors:
                print(f"  [{title}] {err}")


class TestrailSyncer:
    """Fetch Easy BDD TestRail cases and write equivalent local YAML files."""

    def __init__(self, tr_service: Any) -> None:
        self._tr = tr_service

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def sync(
        self,
        project_id: int,
        source_suite_id: Optional[int] = None,
        source_run_id: Optional[int] = None,
        output_dir: Optional[Path] = None,
        suite_tag: Optional[str] = None,
        dry_run: bool = False,
        verbose: bool = True,
    ) -> SyncResult:
        result = SyncResult()

        # Fetch cases from suite or run
        if source_run_id:
            tests = self._tr.get_tests(source_run_id)
            suite_name = f"run_{source_run_id}"
        else:
            tests = self._tr.get_cases(project_id, source_suite_id)
            try:
                info = self._tr.get_suite(source_suite_id)
                suite_name = info.get("name", f"suite_{source_suite_id}")
            except Exception:
                suite_name = f"suite_{source_suite_id}"

        if not tests:
            print("  No cases found.")
            return result

        # Auto-derive output directory from suite name
        if output_dir is None:
            output_dir = Path("tests") / "cases" / _slugify(suite_name)

        tag = suite_tag or _slugify(suite_name)

        # Classify
        classified = [
            {
                **t,
                "role": _classify(t.get("title", "")),
                "clean_title": _strip_prefix(t.get("title", "")),
            }
            for t in tests
        ]

        var_cases     = [c for c in classified if c["role"] == "var"]
        keyword_cases = [c for c in classified if c["role"] == "keyword"]
        feature_cases = [c for c in classified if c["role"] == "inline"]

        print(f"  Var: {len(var_cases)}  Shared: {len(keyword_cases)}  Feature: {len(feature_cases)}")

        # Extract variables from all Var: cases — these become the variables: block
        shared_variables = self._extract_vars(var_cases)
        if shared_variables and verbose:
            print(f"  Variables ({len(shared_variables)}): {', '.join(list(shared_variables)[:8])}")

        if dry_run:
            print(f"\n  [DRY RUN] Would write to: {output_dir}/")
            for case in feature_cases:
                print(f"    {_filename_safe(case['clean_title'])}.yaml")
            if keyword_cases:
                print(f"    shared_steps.yaml")
            print()
            return result

        output_dir.mkdir(parents=True, exist_ok=True)

        # Write shared_steps.yaml
        if keyword_cases:
            shared_path = output_dir / "shared_steps.yaml"
            self._write_shared_steps(keyword_cases, shared_path, result)

        # Write one YAML file per Feature: case
        seen_names: set = set()
        for case in feature_cases:
            title = case["clean_title"]
            filename = _filename_safe(title)
            if filename in seen_names:
                idx = 2
                while f"{filename}_{idx}" in seen_names:
                    idx += 1
                filename = f"{filename}_{idx}"
            seen_names.add(filename)

            case_path = output_dir / f"{filename}.yaml"
            self._write_feature_case(
                case, case_path, shared_variables, tag, result, verbose
            )

        return result

    # ------------------------------------------------------------------
    # Var: case parsing
    # ------------------------------------------------------------------

    def _extract_vars(self, var_cases: List[Dict]) -> Dict[str, Any]:
        variables: Dict[str, Any] = {}
        for case in var_cases:
            body = _html_to_text(case.get("custom_preconds") or "")
            if not body:
                cid = _case_id(case)
                if cid:
                    try:
                        full = self._tr.get_case(cid)
                        body = _html_to_text(full.get("custom_preconds") or "")
                    except Exception:
                        pass
            if not body:
                continue
            # Skip step-list bodies — they contain steps, not key/value pairs
            try:
                parsed = _yaml_safe_load_lenient(body)
                if isinstance(parsed, list):
                    continue
            except Exception:
                if any(ln.lstrip().startswith("- ") for ln in body.splitlines()):
                    continue
            for line in body.splitlines():
                line = line.strip()
                if ":" in line and not line.startswith(("-", "#")):
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if key:
                        variables[key] = _coerce(value)
        return variables

    # ------------------------------------------------------------------
    # Shared: case writing
    # ------------------------------------------------------------------

    def _write_shared_steps(
        self,
        cases: List[Dict],
        path: Path,
        result: SyncResult,
    ) -> None:
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            except Exception:
                pass

        for case in cases:
            name = case.get("clean_title", "").strip()
            if not name:
                continue
            slug = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")

            body = _html_to_text(case.get("custom_preconds") or "")
            if not body:
                cid = _case_id(case)
                if cid:
                    try:
                        full = self._tr.get_case(cid)
                        body = _html_to_text(full.get("custom_preconds") or "")
                    except Exception:
                        pass
            if not body:
                result.skipped.append((name, "no body"))
                continue

            body = _fix_step_list_indent(body)
            try:
                parsed = _yaml_safe_load_lenient(body)
            except Exception as exc:
                result.errors.append((name, str(exc)))
                continue

            if isinstance(parsed, list):
                existing[slug] = {"steps": [s for s in parsed if isinstance(s, dict)]}
            elif isinstance(parsed, dict) and "steps" in parsed:
                existing[slug] = parsed
            else:
                result.skipped.append((name, "unrecognised body format"))
                continue

            result.written.append(f"shared:{slug}")

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(existing, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        print(f"  Wrote: {path}")

    # ------------------------------------------------------------------
    # Feature: case writing
    # ------------------------------------------------------------------

    def _write_feature_case(
        self,
        case: Dict,
        path: Path,
        shared_variables: Dict[str, Any],
        tag: str,
        result: SyncResult,
        verbose: bool,
    ) -> None:
        title = case["clean_title"]

        preconds = _html_to_text(case.get("custom_preconds") or "")
        if not preconds:
            cid = _case_id(case)
            if cid:
                try:
                    full = self._tr.get_case(cid)
                    preconds = _html_to_text(full.get("custom_preconds") or "")
                except Exception:
                    pass

        if not preconds:
            result.skipped.append((title, "no preconditions"))
            return

        # Extract JSON data prefix for parameterised runs
        data_sets, preconds = _extract_inline_data(preconds)

        # Parse steps
        preconds_fixed = _fix_step_list_indent(preconds)
        case_variables: Dict[str, Any] = {}
        steps: List[Any] = []

        try:
            parsed = _yaml_safe_load_lenient(preconds_fixed)
            if isinstance(parsed, list):
                steps = [s for s in parsed if isinstance(s, dict)]
            elif isinstance(parsed, dict) and "steps" in parsed:
                steps = [s for s in (parsed.get("steps") or []) if isinstance(s, dict)]
                case_variables = {
                    str(k).lstrip("$"): v
                    for k, v in (parsed.get("variables") or {}).items()
                }
                if parsed.get("data") and not data_sets:
                    data_sets = parsed["data"]
            elif isinstance(parsed, dict):
                steps = [parsed]
        except Exception as exc:
            result.errors.append((title, str(exc)))
            return

        if not steps:
            result.skipped.append((title, "no steps parsed"))
            return

        # Build ordered test dict (field order mirrors local YAML convention)
        test_dict: Dict[str, Any] = {"name": title}

        if tag:
            test_dict["tags"] = [tag]

        # Variables: Var: case values merged with any case-level overrides.
        # Case-level variables take precedence (last-write-wins order below).
        merged_vars = {**shared_variables, **case_variables}
        if merged_vars:
            test_dict["variables"] = merged_vars

        test_dict["steps"] = steps

        if data_sets:
            test_dict["data"] = data_sets

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                test_dict, f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        if verbose:
            print(f"  Wrote: {path}")
        result.written.append(str(path))
