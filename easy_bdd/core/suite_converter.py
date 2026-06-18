"""
mybdd TestRail suite → Easy BDD migrator.

Does two things in one pass:

  1. Writes Easy BDD YAML test files to a local directory tree.
  2. Creates a new TestRail suite with Easy BDD-format cases so tests can be
     driven from the TestRail UI via `testrail-run`.

Source case prefix taxonomy (mybdd format):
  Given: <name>   — custom_preconds: Python/JSON dict of $key: value pairs
                    → Var: <name>  in new TestRail suite
                    → variables injected into generated YAML files

  Shared: <name>  — custom_preconds: pipe-delimited step block
                    → Shared: <name>  in new TestRail suite
                    → entry in shared_steps.yaml

  Feature: <name> — custom_preconds + custom_expected: step blocks
                    → Feature: <name>  in new TestRail suite
                    → one YAML file per Feature: case

Multiple Given: cases (multiple devices / SKUs):
  Each Given: case represents a separate device configuration. YAML files
  are written once per device under <output_dir>/<device_slug>/, with that
  device's variables injected into the `variables:` section. The TestRail
  suite gets one `Var:` case per device so you can create per-device runs.

Variable handling for custom_expected in Feature: cases:
  - Starts with '{'  → parsed as a dict and merged into that test's variables
  - Otherwise        → parsed as additional pipe-delimited steps (assertions)

Shared: references inside Feature: bodies:
  bdd_migrator.parse_step_block() converts "Shared: name" lines into
  {"shared_step": "slug"} dicts automatically.
"""

from __future__ import annotations

import html as _html
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from .testrail_utils import build_testrail_preconditions

# Add frontend/ to path once at module load so bdd_migrator is importable
_FRONTEND = Path(__file__).parent.parent.parent / "frontend"
if str(_FRONTEND) not in sys.path:
    sys.path.insert(0, str(_FRONTEND))


# ── source role detection ─────────────────────────────────────────────────────

_SOURCE_PREFIXES: Dict[str, str] = {
    "Given:":   "given",
    "Shared:":  "shared",
    "Feature:": "feature",
}


def _classify_source(title: str) -> Tuple[str, str]:
    for prefix, role in _SOURCE_PREFIXES.items():
        if title.startswith(prefix):
            return role, title[len(prefix):].strip()
    return "unknown", title.strip()


def _get_field(case: Dict, field_name: str) -> str:
    """Extract and HTML-unescape a text field from a case dict."""
    val = case.get(field_name) or ""
    return _html.unescape(str(val)).strip() if val else ""


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", text).strip("_").lower()


# ── step parsing helpers ──────────────────────────────────────────────────────

def _sanitize(obj: Any) -> Any:
    """Recursively convert tuples → lists so yaml.dump never emits !!python/tuple."""
    if isinstance(obj, tuple):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    return obj


def _parse_steps(body: str) -> Tuple[List[Dict], int]:
    """Parse a pipe-delimited mybdd step body → (Easy BDD steps list, todo_count)."""
    try:
        from bdd_migrator import parse_step_block
    except ImportError as exc:
        raise ImportError(
            f"Could not import bdd_migrator from {_FRONTEND}. "
            f"Ensure frontend/bdd_migrator.py exists. Original error: {exc}"
        )
    steps, _data = parse_step_block(body or "")
    todos = sum(
        1 for s in steps
        if isinstance(s, dict)
        and str(s.get("action", "")) == "test.log"
        and str(s.get("message", "")).startswith("TODO")
    )
    return steps, todos


def _parse_given_vars(body: str) -> Dict[str, Any]:
    """Parse a Given: case body (Python/JSON dict or key:value lines)."""
    try:
        from bdd_migrator import parse_given_variables
        return parse_given_variables(body)
    except ImportError:
        pass
    import json, ast
    body = body.strip()
    if not body:
        return {}
    for attempt in (body, body.replace("'", '"')):
        try:
            d = json.loads(attempt)
            if isinstance(d, dict):
                return {k.lstrip("$").strip("\"' "): v for k, v in d.items()}
        except Exception:
            pass
    try:
        d = ast.literal_eval(body)
        if isinstance(d, dict):
            return {k.lstrip("$").strip("\"' "): v for k, v in d.items()}
    except Exception:
        pass
    result: Dict[str, Any] = {}
    for line in body.splitlines():
        line = line.strip().strip(",").strip("{}")
        if ":" in line and not line.startswith(("#", "-")):
            k, _, v = line.partition(":")
            k = k.strip().strip("\"'$")
            v = v.strip().strip("\"',")
            if k:
                result[k] = v
    return result


# ── result dataclasses ────────────────────────────────────────────────────────

@dataclass
class CaseConversionResult:
    source_id:    int
    source_title: str
    role:         str               # given | shared | feature | unknown
    status:       str               # written | skipped | error | dry_run
    output_path:  Optional[Path] = None
    tr_case_id:   Optional[int]  = None
    todo_steps:   int = 0
    error:        str = ""


@dataclass
class ConversionResult:
    source_suite_id:    Optional[int]
    source_run_id:      Optional[int]
    output_dir:         Optional[Path]
    shared_steps_path:  Optional[Path]
    target_suite_id:    Optional[int] = None
    cases:              List[CaseConversionResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def written(self) -> int:
        return sum(1 for c in self.cases if c.status in ("written", "dry_run"))

    @property
    def errors(self) -> int:
        return sum(1 for c in self.cases if c.status == "error")

    @property
    def todo_steps(self) -> int:
        return sum(c.todo_steps for c in self.cases)

    def print_summary(self) -> None:
        print(f"\n{'='*60}")
        print("CONVERSION SUMMARY")
        print(f"{'='*60}")
        if self.source_suite_id:
            print(f"  Source suite      : {self.source_suite_id}")
        if self.source_run_id:
            print(f"  Source run        : {self.source_run_id}")
        if self.target_suite_id:
            print(f"  New TR suite      : [{self.target_suite_id}]")
        print(f"  Output dir        : {self.output_dir or '(dry-run)'}")
        if self.shared_steps_path:
            print(f"  Shared steps      : {self.shared_steps_path}")

        by_role: Dict[str, List] = {}
        for c in self.cases:
            by_role.setdefault(c.role, []).append(c)

        print(f"\n  {'Role':<20} {'Count'}")
        print(f"  {'-'*30}")
        for role, label in (
            ("given",   "Given: → Var:"),
            ("shared",  "Shared: → Shared:"),
            ("feature", "Feature: → Feature:"),
            ("unknown", "Skipped (unknown)"),
        ):
            group = by_role.get(role, [])
            if group:
                print(f"  {label:<20} {len(group)}")

        print(f"\n  Files/cases written : {self.written}")
        print(f"  Errors              : {self.errors}")
        if self.todo_steps:
            print(f"  TODO steps          : {self.todo_steps}  (need manual review)")
            for c in self.cases:
                if c.todo_steps:
                    print(f"    [{c.todo_steps}] {c.source_title}")
        if self.errors:
            print("\n  Errors:")
            for c in self.cases:
                if c.status == "error":
                    print(f"    {c.source_title}: {c.error}")
        print()


# ── converter ─────────────────────────────────────────────────────────────────

class BddSuiteConverter:
    """Converts a mybdd-format TestRail suite to Easy BDD YAML files and a
    new TestRail suite with Easy BDD-format cases."""

    def __init__(self, testrail):
        self._tr = testrail

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def convert(
        self,
        project_id: int,
        source_suite_id: int = None,
        source_run_id: int = None,
        # YAML output
        output_dir: Path = None,
        shared_steps_path: Path = None,
        suite_tag: str = None,
        write_yaml: bool = True,
        # TestRail output
        create_testrail_suite: bool = True,
        target_suite_id: int = None,
        target_suite_name: str = None,
        # misc
        dry_run: bool = False,
        verbose: bool = True,
    ) -> ConversionResult:
        """
        Convert a mybdd TestRail suite/run to Easy BDD format.

        write_yaml:            Write YAML test files locally.
        create_testrail_suite: Create a new TestRail suite with Easy BDD cases.
        target_suite_id:       Write into an existing suite (omit to create new).
        target_suite_name:     Name for the new suite (default: EASY_BDD: <source>).
        """
        if not source_suite_id and not source_run_id:
            raise ValueError("Provide source_suite_id or source_run_id.")

        output_dir = Path(output_dir) if output_dir else Path("tests/cases")
        if not shared_steps_path:
            shared_steps_path = output_dir / "shared_steps.yaml"

        result = ConversionResult(
            source_suite_id=source_suite_id,
            source_run_id=source_run_id,
            output_dir=output_dir if not dry_run else None,
            shared_steps_path=shared_steps_path,
        )

        # ── fetch source cases ─────────────────────────────────────────
        sections_by_id: Dict[int, Dict] = {}

        if source_run_id:
            if verbose:
                print(f"[Convert] Fetching tests from run {source_run_id}...")
            raw_cases = self._tr.get_tests(source_run_id)
            raw_cases = self._enrich_from_cases(raw_cases)
        else:
            if verbose:
                print(f"[Convert] Fetching cases from suite {source_suite_id}...")
            raw_cases = self._tr.get_cases(project_id, source_suite_id)
            try:
                sections_list = self._tr.get_sections(project_id, source_suite_id)
                sections_by_id = {s["id"]: s for s in sections_list}
            except Exception:
                pass

        if not raw_cases:
            print("[Convert] No cases found in source.")
            return result

        # ── resolve suite / target names ───────────────────────────────
        source_suite_name = ""
        if source_suite_id:
            try:
                info = self._tr.get_suite(source_suite_id)
                source_suite_name = info.get("name", "")
            except Exception:
                pass
        elif source_run_id:
            try:
                info = self._tr.get_run(source_run_id)
                source_suite_name = info.get("name", "")
            except Exception:
                pass

        if not suite_tag:
            suite_tag = _slug(source_suite_name) if source_suite_name else f"suite_{source_suite_id or source_run_id}"
        if not target_suite_name:
            target_suite_name = f"EASY_BDD: {source_suite_name}" if source_suite_name else "EASY_BDD: Converted Suite"

        # ── classify cases ──────────────────────────────────────────────
        classified = []
        for c in raw_cases:
            title = c.get("title", c.get("case", {}).get("title", ""))
            role, clean = _classify_source(title)
            classified.append({**c, "_role": role, "_clean": clean})

        given_cases   = [c for c in classified if c["_role"] == "given"]
        shared_cases  = [c for c in classified if c["_role"] == "shared"]
        feature_cases = [c for c in classified if c["_role"] == "feature"]
        unknown_cases = [c for c in classified if c["_role"] == "unknown"]

        if verbose:
            print(f"[Convert] Found: {len(given_cases)} Given, {len(shared_cases)} Shared, "
                  f"{len(feature_cases)} Feature, {len(unknown_cases)} Unknown")
        if unknown_cases and verbose:
            for c in unknown_cases[:5]:
                print(f"  [SKIP] Unrecognised prefix: {c.get('title', '')}")
            if len(unknown_cases) > 5:
                print(f"  ... and {len(unknown_cases) - 5} more skipped")

        # ── parse Given: → per-device variable dicts ───────────────────
        # Each Given: = one device/SKU. Collect all so we can write per-device
        # YAML sub-directories when there are multiple devices.
        devices: List[Dict[str, Any]] = []
        for c in given_cases:
            body = _get_field(c, "custom_preconds")
            v    = _parse_given_vars(body)
            name = c["_clean"]
            devices.append({"name": name, "slug": _slug(name), "vars": v, "case": c})
            result.cases.append(CaseConversionResult(
                source_id=c.get("case_id", c.get("id", 0)),
                source_title=c.get("title", ""),
                role="given",
                status="skipped",
            ))

        if verbose and devices:
            print(f"[Convert] Device configs ({len(devices)}): {[d['name'] for d in devices]}")

        # ── parse Shared: cases ─────────────────────────────────────────
        parsed_shared: List[Dict] = []
        for c in shared_cases:
            body = _get_field(c, "custom_preconds")
            try:
                steps, todos = _parse_steps(body)
            except Exception as exc:
                result.cases.append(CaseConversionResult(
                    source_id=c.get("case_id", c.get("id", 0)),
                    source_title=c.get("title", ""),
                    role="shared", status="error", error=str(exc),
                ))
                continue
            parsed_shared.append({
                "slug":         _slug(c["_clean"]),
                "clean":        c["_clean"],
                "keyword_name": c["_clean"].replace(" ", "_"),
                "steps":        steps,
                "todos":        todos,
                "case":         c,
            })

        # ── parse Feature: cases ────────────────────────────────────────
        parsed_features: List[Dict] = []
        for c in feature_cases:
            preconds_body = _get_field(c, "custom_preconds")
            expected_raw  = _get_field(c, "custom_expected")
            try:
                steps, todos = _parse_steps(preconds_body)
            except Exception as exc:
                result.cases.append(CaseConversionResult(
                    source_id=c.get("case_id", c.get("id", 0)),
                    source_title=c.get("title", ""),
                    role="feature", status="error", error=str(exc),
                ))
                continue
            extra_vars: Dict[str, Any] = {}
            if expected_raw:
                if expected_raw.strip().startswith("{"):
                    extra_vars = _parse_given_vars(expected_raw)
                else:
                    try:
                        exp_steps, exp_todos = _parse_steps(expected_raw)
                        steps  += exp_steps
                        todos  += exp_todos
                    except Exception:
                        pass
            parsed_features.append({
                "clean":      c["_clean"],
                "steps":      steps,
                "extra_vars": extra_vars,
                "todos":      todos,
                "case":       c,
            })

        # ── build section → directory path map ─────────────────────────
        section_paths = self._build_section_paths(sections_by_id)

        # ── write YAML files ────────────────────────────────────────────
        if write_yaml:
            shared_yaml: Dict[str, Any] = {}
            for ps in parsed_shared:
                if ps["slug"]:
                    shared_yaml[ps["slug"]] = {
                        "description": ps["clean"],
                        "steps":       ps["steps"],
                    }
                result.cases.append(CaseConversionResult(
                    source_id=ps["case"].get("case_id", ps["case"].get("id", 0)),
                    source_title=ps["case"].get("title", ""),
                    role="shared",
                    status="dry_run" if dry_run else "written",
                    output_path=shared_steps_path,
                    todo_steps=ps["todos"],
                ))

            if shared_yaml:
                if dry_run:
                    if verbose:
                        print(f"\n[dry-run] Would write shared_steps.yaml ({len(shared_yaml)} entries):")
                        for slug in shared_yaml:
                            print(f"  - {slug}")
                else:
                    self._write_shared_steps(shared_yaml, shared_steps_path, verbose)

            for pf in parsed_features:
                crs = self._write_feature_yamls(
                    pf=pf,
                    devices=devices,
                    section_paths=section_paths,
                    output_dir=output_dir,
                    suite_tag=suite_tag,
                    dry_run=dry_run,
                    verbose=verbose,
                )
                result.cases.extend(crs)

        # ── create TestRail suite ───────────────────────────────────────
        if create_testrail_suite:
            tr_suite_id = self._create_testrail_suite(
                project_id=project_id,
                target_suite_id=target_suite_id,
                target_suite_name=target_suite_name,
                sections_by_id=sections_by_id,
                devices=devices,
                parsed_shared=parsed_shared,
                parsed_features=parsed_features,
                dry_run=dry_run,
                verbose=verbose,
                result=result,
            )
            result.target_suite_id = tr_suite_id

        total_todos = sum(c.todo_steps for c in result.cases)
        if verbose:
            print(
                f"\n[Convert] Done — {result.written} written, {result.errors} error(s)"
                + (f", {total_todos} TODO step(s)" if total_todos else "") + "."
            )

        return result

    # ------------------------------------------------------------------ #
    # YAML file writing                                                    #
    # ------------------------------------------------------------------ #

    def _write_feature_yamls(
        self,
        pf: Dict,
        devices: List[Dict],
        section_paths: Dict[int, Path],
        output_dir: Path,
        suite_tag: str,
        dry_run: bool,
        verbose: bool,
    ) -> List[CaseConversionResult]:
        c            = pf["case"]
        source_id    = c.get("case_id", c.get("id", 0))
        source_title = c.get("title", "")
        section_id   = c.get("section_id")
        section_sub  = section_paths.get(section_id, Path(""))
        file_name    = _slug(pf["clean"]) + ".yaml"

        # Multiple devices → one sub-dir per device; single/no device → root
        device_list = devices if devices else [{"slug": "", "vars": {}}]

        results = []
        for dev in device_list:
            dev_slug = dev.get("slug", "")
            dev_vars = {**dev.get("vars", {}), **pf["extra_vars"]}

            parts = [output_dir]
            if dev_slug:
                parts.append(Path(dev_slug))
            if section_sub:
                parts.append(section_sub)
            out_path = Path(*parts) / file_name

            # Build Easy BDD YAML test dict
            test_dict: Dict[str, Any] = {
                "name":        pf["clean"],
                "description": f"TestRail case {source_id}",
                "tags":        [suite_tag],
            }
            if dev_vars:
                test_dict["variables"] = dev_vars
            test_dict["steps"] = pf["steps"]

            if dry_run:
                if verbose:
                    dev_label  = f" [{dev.get('name', '')}]" if dev_slug else ""
                    todo_mark  = f" [{pf['todos']} TODO]" if pf["todos"] else ""
                    print(f"  [dry-run]{dev_label} {source_title!r}")
                    print(f"           → {out_path}  ({len(pf['steps'])} steps{todo_mark})")
                results.append(CaseConversionResult(
                    source_id=source_id, source_title=source_title,
                    role="feature", status="dry_run",
                    output_path=out_path, todo_steps=pf["todos"],
                ))
                continue

            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    yaml.dump(_sanitize(test_dict), f, allow_unicode=True,
                              default_flow_style=False, sort_keys=False)
                if verbose:
                    dev_label = f" [{dev.get('name', '')}]" if dev_slug else ""
                    todo_mark = f"  [{pf['todos']} TODO]" if pf["todos"] else ""
                    print(f"  [written]{dev_label} {out_path}{todo_mark}")
                results.append(CaseConversionResult(
                    source_id=source_id, source_title=source_title,
                    role="feature", status="written",
                    output_path=out_path, todo_steps=pf["todos"],
                ))
            except Exception as exc:
                results.append(CaseConversionResult(
                    source_id=source_id, source_title=source_title,
                    role="feature", status="error",
                    output_path=out_path, error=str(exc),
                ))

        return results

    def _write_shared_steps(
        self, shared_yaml: Dict, path: Path, verbose: bool
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: Dict = {}
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            except Exception:
                pass
        existing.update(shared_yaml)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(_sanitize(existing), f, allow_unicode=True,
                      default_flow_style=False, sort_keys=False)
        if verbose:
            print(f"[Convert] Wrote {len(shared_yaml)} shared step(s) → {path}")

    # ------------------------------------------------------------------ #
    # TestRail suite creation                                              #
    # ------------------------------------------------------------------ #

    def _create_testrail_suite(
        self,
        project_id: int,
        target_suite_id: Optional[int],
        target_suite_name: str,
        sections_by_id: Dict[int, Dict],
        devices: List[Dict],
        parsed_shared: List[Dict],
        parsed_features: List[Dict],
        dry_run: bool,
        verbose: bool,
        result: ConversionResult,
    ) -> Optional[int]:

        if dry_run:
            if verbose:
                print(f"\n[dry-run] Would create TestRail suite: '{target_suite_name}'")
                for d in devices:
                    print(f"  Var: {d['name']}  ({len(d['vars'])} var(s))")
                for ps in parsed_shared:
                    print(f"  Shared: {ps['keyword_name']}  ({len(ps['steps'])} step(s))")
                for pf in parsed_features:
                    print(f"  Feature: {pf['clean']}  ({len(pf['steps'])} step(s))")
            return None

        # ── create or use target suite ─────────────────────────────────
        if not target_suite_id:
            try:
                new_suite = self._tr.add_suite(
                    project_id,
                    name=target_suite_name,
                    description="Converted from mybdd format by Easy BDD converter.",
                )
                target_suite_id = new_suite["id"]
                if verbose:
                    print(f"\n[Convert] Created TestRail suite [{target_suite_id}] '{target_suite_name}'")
            except Exception as exc:
                print(f"[Convert] ERROR creating suite: {exc}", file=sys.stderr)
                return None
        else:
            if verbose:
                print(f"\n[Convert] Using existing suite [{target_suite_id}]")

        # ── mirror sections ─────────────────────────────────────────────
        section_map: Dict[int, int] = {}
        if sections_by_id:
            section_map = self._mirror_sections(
                project_id, target_suite_id, sections_by_id, verbose
            )

        def _target_section(case: Dict) -> Optional[int]:
            sid = case.get("section_id")
            if sid and sid in section_map:
                return section_map[sid]
            return self._default_section(project_id, target_suite_id)

        # ── Var: cases (one per device/Given:) ─────────────────────────
        for d in devices:
            c    = d["case"]
            sec  = _target_section(c)
            body = "\n".join(f"{k}: {v}" for k, v in d["vars"].items())
            payload = {
                "title":           f"Var: {d['name']}",
                "custom_preconds": body,
            }
            try:
                new_case = self._tr.add_case(sec, **payload)
                if verbose:
                    print(f"  [TR created] Var: {d['name']}  ({len(d['vars'])} var(s))")
                for cr in result.cases:
                    if cr.source_id == c.get("case_id", c.get("id", 0)) and cr.role == "given":
                        cr.tr_case_id = new_case.get("id")
                        cr.status     = "written"
                        break
            except Exception as exc:
                if verbose:
                    print(f"  [TR error] Var: {d['name']}: {exc}", file=sys.stderr)

        # ── Shared: cases ───────────────────────────────────────────────
        for ps in parsed_shared:
            c   = ps["case"]
            sec = _target_section(c)
            steps_yaml = yaml.dump(
                _sanitize(ps["steps"]), allow_unicode=True,
                default_flow_style=False, sort_keys=False
            ).rstrip()
            payload = {
                "title":           f"Shared: {ps['keyword_name']}",
                "custom_preconds": steps_yaml,
            }
            try:
                new_case = self._tr.add_case(sec, **payload)
                if verbose:
                    print(f"  [TR created] Shared: {ps['keyword_name']}  ({len(ps['steps'])} step(s))")
                for cr in result.cases:
                    if cr.source_id == c.get("case_id", c.get("id", 0)) and cr.role == "shared":
                        cr.tr_case_id = new_case.get("id")
                        break
            except Exception as exc:
                if verbose:
                    print(f"  [TR error] Shared: {ps['keyword_name']}: {exc}", file=sys.stderr)

        # ── Feature: cases ─────────────────────────────────────────────
        for pf in parsed_features:
            c   = pf["case"]
            sec = _target_section(c)

            if pf["extra_vars"]:
                # Prepend variables block then numbered steps
                var_lines = ["variables:"]
                for k, v in pf["extra_vars"].items():
                    var_lines.append(f"  {k}: {v}")
                preconds_text = "\n".join(var_lines) + "\n" + build_testrail_preconditions(pf["steps"])
            else:
                preconds_text = build_testrail_preconditions(pf["steps"]) if pf["steps"] else ""

            payload: Dict[str, Any] = {
                "title":           f"Feature: {pf['clean']}",
                "custom_preconds": preconds_text,
            }

            try:
                new_case = self._tr.add_case(sec, **payload)
                if verbose:
                    todo_mark = f"  [{pf['todos']} TODO]" if pf["todos"] else ""
                    print(f"  [TR created] Feature: {pf['clean']}  ({len(pf['steps'])} step(s)){todo_mark}")
                for cr in result.cases:
                    if cr.source_id == c.get("case_id", c.get("id", 0)) and cr.role == "feature":
                        cr.tr_case_id = new_case.get("id")
                        break
            except Exception as exc:
                if verbose:
                    print(f"  [TR error] Feature: {pf['clean']}: {exc}", file=sys.stderr)

        return target_suite_id

    # ------------------------------------------------------------------ #
    # Section helpers                                                      #
    # ------------------------------------------------------------------ #

    def _build_section_paths(self, sections_by_id: Dict[int, Dict]) -> Dict[int, Path]:
        def _path_for(sid: int, visited: set) -> Path:
            if sid in visited:
                return Path(_slug(sections_by_id[sid]["name"]))
            visited.add(sid)
            s      = sections_by_id.get(sid, {})
            parent = s.get("parent_id")
            name   = _slug(s.get("name", str(sid)))
            if parent and parent in sections_by_id:
                return _path_for(parent, visited) / name
            return Path(name)
        return {sid: _path_for(sid, set()) for sid in sections_by_id}

    def _mirror_sections(
        self,
        project_id: int,
        target_suite_id: int,
        sections_by_id: Dict[int, Dict],
        verbose: bool,
    ) -> Dict[int, int]:
        def _depth(s: Dict) -> int:
            d, pid = 0, s.get("parent_id")
            while pid and pid in sections_by_id:
                d += 1
                pid = sections_by_id[pid].get("parent_id")
            return d

        ordered = sorted(sections_by_id.values(), key=_depth)
        id_map: Dict[int, int] = {}
        for s in ordered:
            src_id     = s["id"]
            parent_src = s.get("parent_id")
            parent_tgt = id_map.get(parent_src) if parent_src else None
            kwargs     = {"name": s["name"], "suite_id": target_suite_id}
            if parent_tgt:
                kwargs["parent_id"] = parent_tgt
            try:
                new_sec = self._tr.add_section(project_id, **kwargs)
                id_map[src_id] = new_sec["id"]
            except Exception as exc:
                if verbose:
                    print(f"  [WARN] Could not create section '{s['name']}': {exc}",
                          file=sys.stderr)
        return id_map

    _default_section_cache: Dict = {}

    def _default_section(self, project_id: int, suite_id: int) -> Optional[int]:
        key = (project_id, suite_id)
        if key not in self._default_section_cache:
            try:
                sec = self._tr.add_section(
                    project_id, name="Converted Tests", suite_id=suite_id
                )
                self._default_section_cache[key] = sec["id"]
            except Exception:
                return None
        return self._default_section_cache.get(key)

    # ------------------------------------------------------------------ #
    # Misc helpers                                                         #
    # ------------------------------------------------------------------ #

    def _enrich_from_cases(self, tests: List[Dict]) -> List[Dict]:
        enriched = []
        for t in tests:
            has_body = any(t.get(f) for f in ("custom_preconds", "custom_expected", "custom_steps"))
            if not has_body:
                case_id = t.get("case_id")
                if case_id:
                    try:
                        full = self._tr.get_case(case_id)
                        t = {**full, **{k: v for k, v in t.items() if v is not None}}
                    except Exception:
                        pass
            enriched.append(t)
        return enriched
