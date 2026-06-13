"""
TestRail-driven test runner for Easy BDD Framework.

Lifecycle (6 phases):
  1. find_run      — scan project for EASY_BDD: run with pending tests
  2. prepare_run   — fetch tests, parse run_vars from description
  3. cron_gate     — skip all if outside cron window
  4. execute_tests — resolve each case to YAML, run it, post result in real-time
  5. finalize_run  — write result summary back to run description
  6. retry_loop    — if retry > 0, mark failed as retest and loop from phase 4

Case prefix taxonomy:
  Var: <name>       — key: value pairs injected as variables into every test
  Setup: <name>     — executes before Test: cases
  Test: <name>      — main test case (body: tag: or file: pointer to local YAML)
  Feature: <name>   — main test case (steps written directly in TestRail fields)
  Teardown: <name>  — executes after all Test: cases

Test: case body format (Steps/Preconditions field):
  tag: <tag>    — run all local YAML tests in tests/cases/ that have this tag
  file: <path>  — run a specific YAML file (relative to tests/cases/ or absolute)

Feature: case body formats (all written in the Preconditions field):

  PREFERRED — same dot-notation format used in local YAML files:
    - aws.list_files:
        bucket_name: my-bucket
        folder_prefix: vps
        file_extension: .bin
        store_as: firmware_files
    - eval.exec:
        code: print(firmware_files)

  Parameters may also be written flush-left (no indentation) — the runner
  will re-indent them automatically:
    - aws.list_files:
    bucket_name: my-bucket
    folder_prefix: vps/

  PARAMETERIZED — JSON data block + steps (for multiple SKUs / devices):
    JSON:
    [{"mac": "D4:6A:91:29:0F:5A", "product": "WB-800", "bucket_name": "my-bucket"}]

    - ovrc.connect:
    device_id: ${mac}
    - ovrc.disconnect: {}

  WITH data + steps block (full YAML format, mirrors local YAML files):
    data:
      - mac: D4:6A:91:29:0F:5A
        product: WB-800
    steps:
      - ovrc.connect:
          device_id: ${mac}

  WITH variables block (mirrors local YAML files exactly):
    variables:
      base_url: https://staging.example.com
    steps:
      - api.request:
          method: GET
          url: ${base_url}/status
          store_as: last_response
      - test.assert_response:
          status: 200

  ALSO ACCEPTED — flat action: key format (single-step shorthand):
    action: aws.list_files
    bucket_name: my-bucket
    folder_prefix: vps
    file_extension: .bin
    store_as: firmware_files

  Legacy Option A — Steps field contains a YAML steps list (still supported).
  Legacy Option B — "Steps (Separated)" TestRail case type (still supported):
    Step Description column: Easy BDD action YAML, one step per row
    Expected Result column: Python expression or natural-language assertion

Variable injection (Var: case body):
  base_url: https://staging.example.com
  username: testuser
"""

import html as _html_mod
import json
import os
import re as _re_mod
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .runner import TestResult, TestRunner
from .variable_manager import GlobalConfigManager
from ..services.testrail_service import RunVariables, TestRailService, TestRailError


def _html_to_text(raw: str) -> str:
    """Strip HTML tags and unescape entities from a TestRail rich-text field.

    TestRail's web UI stores Preconditions/Steps as HTML.  Convert to plain
    text so YAML parsers can read it cleanly.
    """
    text = raw or ""
    # Block-level closing tags → newline
    text = _re_mod.sub(r"<br\s*/?>",  "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"</p>",       "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"</div>",     "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"</li>",      "\n", text, flags=_re_mod.IGNORECASE)
    # Opening block-level tags → nothing (content follows on same line)
    text = _re_mod.sub(r"<(p|div|li|ul|ol|pre|code)[^>]*>", "", text, flags=_re_mod.IGNORECASE)
    # Strip any remaining tags
    text = _re_mod.sub(r"<[^>]+>", "", text)
    # Unescape HTML entities (&amp; &lt; &gt; &nbsp; etc.)
    text = _html_mod.unescape(text)
    # Normalize Unicode spaces (e.g. \xa0 from &nbsp;) to ASCII space so YAML
    # can recognise ':' as a key-value separator even when typed via a rich-text
    # editor that inserts a non-breaking space after the colon.
    text = _re_mod.sub(r"[^\S\n\r]", " ", text)
    # Trim each line, drop trailing blank lines
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


def _fix_yaml_indent(text: str) -> str:
    """Remove spurious continuation-line indentation from flat YAML dicts.

    When a user types key-value pairs in TestRail and accidentally indents
    all keys after the first (4 spaces, etc.), YAML fails to parse because
    the extra indentation implies nesting under the previous scalar value.

    This function detects that pattern (first non-empty line has less indent
    than all subsequent non-empty lines) and strips the extra indent so the
    result is a valid flat mapping.

    Only called as a fallback when yaml.safe_load already failed, so there
    is no risk of mis-processing already-valid YAML.

        action: aws.list_files          ← indent 0
            bucket_name: jpdsauto-wattbox  ← indent 4 (spurious)
        →
        action: aws.list_files
        bucket_name: jpdsauto-wattbox
    """
    lines = text.splitlines()
    non_empty = [(i, ln) for i, ln in enumerate(lines) if ln.strip()]
    if len(non_empty) < 2:
        return text

    indents = [len(ln) - len(ln.lstrip()) for _, ln in non_empty]
    first_indent = indents[0]
    rest_min = min(indents[1:])

    if rest_min <= first_indent:
        return text  # no spurious indentation — don't touch it

    extra = rest_min - first_indent
    result = list(lines)
    for i, ln in non_empty[1:]:
        curr_indent = len(ln) - len(ln.lstrip())
        if curr_indent >= extra:
            result[i] = ln[extra:]
        # else: less-indented than expected — leave unchanged

    return "\n".join(result)


_BARE_QUOTED_LINE_RE = _re_mod.compile(r'^(\s*)(["\'])([^:]*)\2\s*$')
# Matches lines where a block-scalar indicator has content on the same line (invalid YAML):
#   code: | some content here
_INLINE_BLOCK_SCALAR_RE = _re_mod.compile(r'^(\s*)(\S[^:]*)\s*:\s*\|\s+(.+)$')
# Matches lines that look like YAML keys or list items (stop collecting block scalar content)
_YAML_KEY_OR_LIST_RE = _re_mod.compile(r'^\s*(-\s+\S|#|\w[\w.\s]*:)')


def _fix_inline_block_scalars(text: str) -> str:
    """Convert 'key: | content' (invalid YAML) to a proper block scalar.

    TestRail sometimes collapses newlines when saving multi-line field values.
    Two failure modes are handled:

    Mode A — content on the same line as |:
        code: | line1 line2
      →
        code: |
          line1 line2

    Mode B — first content line inline, subsequent continuation lines unindented:
        code: | line1
        line2
      →
        code: |
          line1
          line2

    Lines that look like YAML keys (word: ...) or list items (- ...) stop the
    absorption so they are not accidentally swallowed into the block scalar.
    """
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _INLINE_BLOCK_SCALAR_RE.match(line)
        if m:
            indent, key, first_content = m.group(1), m.group(2), m.group(3)
            result.append(f"{indent}{key}: |")
            result.append(f"{indent}  {first_content}")
            i += 1
            # Absorb following unindented lines that are block-scalar continuations
            while i < len(lines):
                nxt = lines[i]
                stripped = nxt.strip()
                if not stripped:
                    break
                if _YAML_KEY_OR_LIST_RE.match(nxt):
                    break
                result.append(f"{indent}  {stripped}")
                i += 1
        else:
            result.append(line)
            i += 1
    return "\n".join(result)


def _unquote_bare_string_lines(text: str) -> str:
    """Strip surrounding quotes from lines that are just a quoted string with no colon.

    TestRail editors sometimes wrap variable references in quotes, producing
    lines like:  "${gv.message}"
    YAML treats these as mapping keys and fails when no ':' follows.
    Removing the outer quotes turns them into bare scalars that parse cleanly.
    Only lines whose quoted content contains no ':' are touched, to avoid
    accidentally unquoting  "key: value"  strings that are valid YAML values.
    """
    result = []
    for line in text.splitlines():
        m = _BARE_QUOTED_LINE_RE.match(line)
        if m:
            line = m.group(1) + m.group(3)
        result.append(line)
    return "\n".join(result)


def _yaml_safe_load_lenient(text: str):
    """Parse YAML, retrying with several fixup passes if the first attempt fails."""
    import yaml as _yaml
    try:
        return _yaml.safe_load(text)
    except _yaml.YAMLError:
        pass

    for fixer in (_fix_yaml_indent, _fix_inline_block_scalars, _unquote_bare_string_lines):
        fixed = fixer(text)
        if fixed != text:
            try:
                return _yaml.safe_load(fixed)
            except _yaml.YAMLError:
                text = fixed   # carry forward fixes before trying the next fixer

    return _yaml.safe_load(text)   # final attempt — raises if still broken


_STEP_LINE_RE = _re_mod.compile(r'^(\s*)- (\S[^:]*):(.*)$')
_PARAM_LINE_RE = _re_mod.compile(r'^[A-Za-z_][\w. -]*\s*:')
_STEP_ANNOTATION_KEYS = frozenset({'description', 'comment', 'note', 'label'})
_GV_VAR_RE = _re_mod.compile(r"gv\.tests\['variables'\]\['([^']+)'\]")


def _extract_inline_data(text: str):
    """Extract a 'JSON:\\n[...]' data block prepended to inline preconditions.

    Allows parameterized runs by putting a JSON array in the Preconditions
    field before the steps list:

        JSON:
        [{"mac": "AA:BB:CC:DD:EE:FF", "product": "WB-800", "bucket_name": "my-bucket"}]

        - ovrc.connect:
        device_id: ${mac}

    Returns (data_list, remaining_steps_text) on success,
    or (None, original_text) if no recognised prefix is found.
    """
    if not text.startswith("JSON:"):
        return None, text
    nl = text.find('\n')
    if nl == -1:
        return None, text
    rest = text[nl + 1:].lstrip()
    if not rest.startswith('['):
        return None, text
    # Find the matching closing ']' (handle nested arrays/objects)
    depth = 0
    end_idx = -1
    for idx, ch in enumerate(rest):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end_idx = idx
                break
    if end_idx == -1:
        return None, text
    try:
        data = json.loads(rest[:end_idx + 1])
        if not isinstance(data, list):
            return None, text
        return data, rest[end_idx + 1:].lstrip('\n\r ')
    except Exception:
        return None, text


def _normalize_shared_step_refs(steps: List[Any]) -> List[Any]:
    """Normalize ``shared_step`` reference names in a steps list to slug format.

    When a Shared: case body references another shared step with spaces or special
    characters (e.g. ``- shared_step: Connect to Device``), the reference must
    match the slugified key used in shared_steps.yaml
    (``Connect_to_Device``).  This function rewrites every ``shared_step``
    value in the list so it uses the same slug format.
    """
    result = []
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("shared_step"), str):
            slug = _re_mod.sub(r"[^A-Za-z0-9_]+", "_", step["shared_step"]).strip("_")
            step = {**step, "shared_step": slug}
        result.append(step)
    return result


def _fix_step_list_indent(text: str) -> str:
    """Re-indent step parameters that appear at the same level as their '-' marker.

    Users often type step params flush-left in TestRail's plain-text editor:

        - aws.list_files:
        bucket_name: my-bucket     ← wrong: needs 4-space indent
        folder_prefix: vps/

    This function indents them under the step key so YAML parses correctly:

        - aws.list_files:
            bucket_name: my-bucket
            folder_prefix: vps/

    Also handles sub-list values under a bare key, e.g.:

        - websocket.send:
        subprotocols:
        - firmware-protocol     ← indented as list value under subprotocols:

    Bare annotation lines (description:, note:, label:) after a step are dropped.
    """
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _STEP_LINE_RE.match(line)
        if m:
            dash_indent = len(m.group(1))
            result.append(line)
            i += 1
            # Steps with an inline value (e.g. "- shared_step: Foo", "- power_fault_time: 70")
            # cannot have sub-parameters.  Skip the inner collection loop entirely so that
            # a following structural key like "steps:" is never consumed as a parameter.
            if m.group(3).strip():
                continue
            param_prefix = ' ' * (dash_indent + 4)
            # Track if last emitted param was a bare key (e.g. "subprotocols:") so
            # that a following "- item" at flush-level is treated as its list value
            # rather than as a new step at the same indent.
            last_bare_key_indent: Optional[str] = None
            # Stack for nested bare keys (e.g. body: → user:/password:)
            # Each entry is (source_indent, target_prefix) for a bare key seen at
            # source_indent that should make its children emit at target_prefix.
            _bare_key_stack: list = []  # list of (src_indent, tgt_prefix)

            while i < len(lines):
                nl = lines[i]
                if not nl.strip():
                    result.append(nl)
                    i += 1
                    last_bare_key_indent = None
                    _bare_key_stack.clear()
                    break
                nl_indent = len(nl) - len(nl.lstrip())
                stripped = nl.lstrip()

                # A "- item" at the step's indent level is either:
                #   • a sub-list value under the preceding bare key  → indent it
                #   • the start of the next step                     → stop
                if stripped.startswith('- ') and nl_indent <= dash_indent:
                    if last_bare_key_indent is not None:
                        result.append(last_bare_key_indent + '  ' + stripped)
                        i += 1
                        continue  # more list items may follow
                    break

                # Any non-list flush-level line:
                # When dash_indent==0 (step starts at col 0), flush-left params
                # (indent 0) are ALSO at "same level" — re-indent them rather than
                # treating them as a new step.
                if nl_indent <= dash_indent:
                    if dash_indent == 0 and _PARAM_LINE_RE.match(stripped):
                        # Pop bare-key stack entries that are no longer parents
                        # (i.e. same or shallower indent than current line)
                        while _bare_key_stack and _bare_key_stack[-1][0] >= nl_indent:
                            _bare_key_stack.pop()
                        # fall through to the re-indent block below
                        pass
                    elif last_bare_key_indent is not None and stripped and not stripped.startswith('- '):
                        # Value on next line after a bare key (TestRail sometimes
                        # splits "folder_prefix: ${val}" into two lines). Merge inline.
                        if result and result[-1].rstrip().endswith(':'):
                            result[-1] = result[-1].rstrip() + ' ' + stripped
                        _bare_key_stack.pop()
                        last_bare_key_indent = None
                        i += 1
                        continue
                    else:
                        last_bare_key_indent = None
                        _bare_key_stack.clear()

                # Already correctly indented → keep as-is
                if nl_indent > dash_indent:
                    result.append(nl)
                    i += 1
                    continue
                # At wrong indent level: check if it's a key: value line
                if _PARAM_LINE_RE.match(stripped):
                    key = stripped.split(':', 1)[0].strip()
                    if key in _STEP_ANNOTATION_KEYS:
                        i += 1  # drop bare annotation lines
                        continue
                    # Determine the correct output prefix:
                    # if there's an active bare-key parent, nest under it
                    if _bare_key_stack:
                        current_prefix = _bare_key_stack[-1][1] + '  '
                    else:
                        current_prefix = param_prefix
                    result.append(current_prefix + stripped)
                    i += 1
                    # Remember if this was a bare key so following list items / child
                    # params can be nested under it
                    val_part = stripped.split(':', 1)[1].strip() if ':' in stripped else ''
                    if not val_part:
                        last_bare_key_indent = current_prefix
                        _bare_key_stack.append((nl_indent, current_prefix))
                    else:
                        last_bare_key_indent = None
                else:
                    result.append(nl)
                    i += 1
                    last_bare_key_indent = None
        else:
            result.append(line)
            i += 1
    return '\n'.join(result)


# Ordered prefix → role mapping (order matters: longest prefix checked first)
# "Shared:" replaces "Keyword:", "Feature:" replaces "Inline:" — old prefixes kept for back-compat.
_CASE_ROLES: Dict[str, str] = {
    "Teardown:": "teardown",
    "Shared:":   "keyword",
    "Keyword:":  "keyword",   # legacy alias
    "Feature:":  "inline",
    "Inline:":   "inline",    # legacy alias
    "Setup:":    "setup",
    "Test:":     "test",
    "Var:":      "var",
}


def _classify(title: str) -> str:
    for prefix, role in _CASE_ROLES.items():
        if title.startswith(prefix):
            return role
    return "unknown"


def _strip_prefix(title: str) -> str:
    for prefix in _CASE_ROLES:
        if title.startswith(prefix):
            return title[len(prefix):].strip()
    return title.strip()


def _format_elapsed(seconds: float) -> str:
    seconds = max(1, int(seconds))
    minutes = seconds // 60
    secs = seconds % 60
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _cron_in_window(cron: str, now: datetime = None) -> bool:
    """Return True if a 5-field cron expression matches within a ±5 minute window."""
    now = now or datetime.now()
    parts = cron.strip().split()
    if len(parts) != 5:
        return False
    minute_f, hour_f, day_f, month_f, weekday_f = parts

    def expand(field: str) -> set:
        result: set = set()
        for token in field.split(","):
            token = token.strip()
            if token == "*":
                result.update(range(0, 100))
            elif token.startswith("*/"):
                step = int(token[2:])
                result.update(range(0, 100, max(1, step)))
            elif "-" in token:
                a, b = token.split("-", 1)
                result.update(range(int(a), int(b) + 1))
            else:
                try:
                    result.add(int(token))
                except ValueError:
                    pass
        return result

    minutes_set = expand(minute_f)
    hours_set = expand(hour_f)
    days_set = expand(day_f)
    months_set = expand(month_f)

    start = (now - timedelta(minutes=5)).replace(second=0, microsecond=0)
    for offset in range(11):
        candidate = start + timedelta(minutes=offset)
        if abs((now - candidate).total_seconds()) > 300:
            continue
        if (
            candidate.minute in minutes_set
            and candidate.hour in hours_set
            and candidate.day in days_set
            and candidate.month in months_set
        ):
            return True
    return False


_STEP_FIELDS = ("custom_steps_separated", "custom_steps", "custom_preconds")
# Fields intentionally excluded from step extraction — reserved for documentation only:
#   custom_summary  (the "Summary" textarea in TestRail)
_EXCLUDED_FROM_STEPS = frozenset({"custom_summary"})


def _get_case_body(test: Dict[str, Any]) -> str:
    """Extract case body text from a TestRail test object.

    Reads ONLY the designated step fields (custom_steps_separated,
    custom_steps, custom_preconds).  The Summary field (custom_summary) and
    any other documentation fields are never read here.
    """
    steps = test.get("custom_steps_separated")
    if steps and isinstance(steps, list):
        parts = [
            part
            for step in steps
            if isinstance(step, dict)
            for part in (step.get("content", ""), step.get("expected", ""))
            if part
        ]
        if parts:
            return "\n".join(parts)

    for field in ("custom_steps", "custom_preconds"):
        value = test.get(field)
        if value and not isinstance(value, list):
            return _html_to_text(str(value))
    return ""


def _parse_preconds_vars(test: Dict[str, Any]) -> Dict[str, Any]:
    """Parse the Preconditions field as key: value variable pairs.

    Tries YAML first, then falls back to line-by-line splitting on the first colon.
    """
    import yaml as _yaml
    text = _html_to_text(test.get("custom_preconds") or "")
    if not text:
        return {}
    try:
        parsed = _yaml.safe_load(text)
        if isinstance(parsed, dict):
            return {str(k): _coerce(str(v)) for k, v in parsed.items()}
    except Exception:
        pass
    variables: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith(("#", "-")):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key:
                variables[key] = _coerce(value)
    return variables


# Tokens that suggest a string is a Python expression rather than natural language
_EXPR_SIGNALS = ("==", "!=", " in ", " not in ", " is ", " is not ", " and ", " or ",
                 ">(", ">=", "<=", "<(", "(", ".", "[")


def _parse_structured_steps(test: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Map custom_steps_separated rows to Easy BDD step dicts (Option B).

    Each row:
      content  → parsed as an action YAML dict; plain text becomes test.log
      expected → Python expression becomes test.assert; natural language
                 becomes a soft test.assert with the text as the message
    """
    import yaml as _yaml
    rows = test.get("custom_steps_separated") or []
    if not isinstance(rows, list):
        return []
    steps: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        content  = (row.get("content")  or "").strip()
        expected = (row.get("expected") or "").strip()
        if content:
            try:
                parsed = _yaml.safe_load(content)
                if isinstance(parsed, dict):
                    steps.append(parsed)
                elif isinstance(parsed, list):
                    steps.extend(s for s in parsed if isinstance(s, dict))
                else:
                    steps.append({"action": "test.log", "message": content})
            except Exception:
                steps.append({"action": "test.log", "message": content})
        if expected:
            if any(sig in expected for sig in _EXPR_SIGNALS):
                steps.append({"action": "test.assert", "expression": expected})
            else:
                steps.append({
                    "action":     "test.assert",
                    "expression": "True",
                    "soft":       True,
                    "message":    expected,
                })
    return steps


def _parse_inline_body(body: str) -> List[Dict[str, Any]]:
    """Parse raw YAML from a TestRail text field as a steps list."""
    body = _html_to_text(body)
    if not body:
        return []
    try:
        parsed = _yaml_safe_load_lenient(body)
        if isinstance(parsed, list):
            return [s for s in parsed if isinstance(s, dict)]
        if isinstance(parsed, dict) and "steps" in parsed:
            return [s for s in parsed["steps"] if isinstance(s, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except Exception:
        pass
    return []


def _coerce(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value.startswith(('[', '{')):
        try:
            import yaml as _yaml_coerce
            parsed = _yaml_coerce.safe_load(value)
            if isinstance(parsed, (list, dict)):
                return parsed
        except Exception:
            pass
    return value


class TestRailRunner:
    """Runs Easy BDD tests driven by a TestRail test run.

    Usage:
        runner = TestRailRunner(config_manager)
        result = runner.run(project_id=59)
    """

    DEFAULT_PREFIX = "EASY_BDD:"

    def __init__(
        self,
        config_manager: GlobalConfigManager,
        testrail: TestRailService = None,
        tests_dir: Path = None,
        artifact_dir: Path = None,
        run_prefix: str = None,
        running_status_id: int = None,
    ):
        self._config = config_manager
        self._tr = testrail or TestRailService()
        self._tests_dir = Path(tests_dir or "tests/cases")
        self._artifact_dir = Path(artifact_dir or "reports/testrail")
        self._run_prefix = run_prefix or os.getenv(
            "TESTRAIL_RUN_PREFIX", self.DEFAULT_PREFIX
        )
        # Custom "Running" status ID — defaults to STATUS_RUNNING (6) if not overridden
        running_env = os.getenv("TESTRAIL_RUNNING_STATUS_ID")
        self._running_status_id: int = (
            running_status_id
            or (int(running_env) if running_env else TestRailService.STATUS_RUNNING)
        )
        # Tracks the test_id currently executing so signal handlers can mark it failed
        self._inflight_test_id: Optional[int] = None

    def list_runs(self, project_id: int) -> List[Dict]:
        """Return all runs in a project that match the configured prefix."""
        created_after = int(time.time()) - 30 * 86400
        runs = self._tr.get_runs(project_id, created_after=created_after)
        return [r for r in runs if r.get("name", "").startswith(self._run_prefix)]

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    def run(
        self,
        project_id: int,
        run_id: int = None,
        verbose: bool = True,
        no_datalake: bool = False,
    ) -> Dict[str, Any]:
        """Execute the full TestRail-driven lifecycle.

        Returns a summary dict: run_id, passed, failed, skipped, success.
        """
        return self._lifecycle(project_id, run_id, verbose, no_datalake=no_datalake)

    # ------------------------------------------------------------------ #
    # Lifecycle phases                                                     #
    # ------------------------------------------------------------------ #

    def _lifecycle(
        self, project_id: int, run_id: int = None, verbose: bool = True, no_datalake: bool = False
    ) -> Dict[str, Any]:
        # Phase 1: Find run
        if run_id is not None:
            run = self._tr.get_run(run_id)
        else:
            run = self._find_run(project_id)
            if run is None:
                project_name = self._tr.get_project(project_id).get("name", str(project_id))
                msg = (
                    f'No "{self._run_prefix}" run with pending tests found '
                    f"in project {project_name}"
                )
                if verbose:
                    print(f"\n[TestRail] {msg}")
                return {"skipped": True, "reason": msg}

        run_id = run["id"]
        run_vars = TestRailService.parse_run_vars(run.get("description"))

        if verbose:
            print(f"\n[TestRail] Run [{run_id}] {run['name']}")
            if run_vars.cron:
                print(f"[TestRail] Cron schedule: {run_vars.cron}")
            if run_vars.retry:
                print(f"[TestRail] Retries configured: {run_vars.retry}")

        # Phase 2: Get tests
        tests = self._tr.get_tests(run_id)
        if not tests:
            return {"skipped": True, "reason": "Run has no tests", "run_id": run_id}

        classified = self._classify_tests(tests)

        # Phase 3: Cron gate
        if run_vars.cron and not _cron_in_window(run_vars.cron):
            if verbose:
                print(
                    f"[TestRail] Outside cron window ({run_vars.cron}) — marking all skipped"
                )
            self._skip_all(classified)
            return {"skipped": True, "reason": "Outside cron window", "run_id": run_id}

        # Setup artifact directory
        self._artifact_dir.mkdir(parents=True, exist_ok=True)

        # run_vars.extra are static overrides supplied in the run description;
        # Var: case variables are re-extracted fresh inside each _execute_cases call.
        static_extra = dict(run_vars.extra)
        static_extra["_testrail_run_id"] = run_id  # available to eval.extract_version etc.

        # Phase 4–6: Execute with retry loop
        retry_remaining = run_vars.retry
        rerun_count = run_vars.rerun
        total_passed = total_failed = total_skipped = 0
        run_start_time = datetime.now()

        while True:
            passed, failed, skipped = self._execute_cases(
                classified, static_extra, run_id, verbose
            )
            total_passed += passed
            total_failed += failed
            total_skipped += skipped

            # Phase 5: Finalize
            self._finalize(run_id, run_vars, passed, failed, skipped)

            if failed == 0 or retry_remaining <= 0:
                break

            if verbose:
                print(
                    f"\n[TestRail] Retry {rerun_count + 1}: "
                    f"{failed} failed, {retry_remaining} retry(s) left"
                )

            self._mark_failed_for_retest(run_id)
            retry_remaining -= 1
            rerun_count += 1
            run_vars.retry = retry_remaining
            run_vars.rerun = rerun_count
            try:
                self._tr.update_run(run_id, description=json.dumps(run_vars.to_dict()))
            except Exception:
                pass

            # Re-fetch tests with updated statuses
            tests = self._tr.get_tests(run_id)
            classified = self._classify_tests(tests)

        if verbose:
            print(
                f"\n[TestRail] Done — "
                f"Passed: {total_passed}  Failed: {total_failed}  Skipped: {total_skipped}"
            )

        # Single datalake post for the entire run (skipped if --no-datalake)
        if not no_datalake:
            self._post_run_to_datalake(
                run_title=run["name"],
                run_id=run_id,
                classified=classified,
                success=total_failed == 0,
                start_time=run_start_time,
                verbose=verbose,
            )

        return {
            "run_id": run_id,
            "run_name": run["name"],
            "run_url": f"https://jpdsauto.testrail.io/index.php?/runs/view/{run_id}",
            "passed": total_passed,
            "failed": total_failed,
            "skipped": total_skipped,
            "success": total_failed == 0,
        }

    def _post_run_to_datalake(
        self,
        run_title: str,
        run_id: int,
        classified: List[Dict],
        success: bool,
        start_time: datetime,
        verbose: bool,
    ) -> None:
        """Post one datalake entry for the entire TestRail run."""
        try:
            from .datalake_logger import DatalakeLogger
            dl = DatalakeLogger(artifact_path="reports", post_results=True)

            # Pull representative metadata from the first Feature/test case
            product = "Unknown"
            product_category = "Test"
            mac_address = "00:00:00:00:00:00"
            time_savings = 5.0
            for case in classified:
                if case.get("role") in ("inline", "test"):
                    body = _get_case_body(case)
                    try:
                        import yaml as _yaml
                        parsed = _yaml_safe_load_lenient(body) if body else None
                        if isinstance(parsed, dict):
                            v = parsed.get("variables") or {}
                            product = v.get("product", product)
                            product_category = v.get("product_category", product_category)
                            mac_address = v.get("mac_address") or v.get("mac") or mac_address
                            time_savings = float(v.get("time_savings", time_savings))
                    except Exception:
                        pass
                    break

            run_url = f"https://jpdsauto.testrail.io/index.php?/runs/view/{run_id}"

            dl.datalake_post(
                test_name=run_title,
                product=product,
                product_category=product_category,
                mac_address=mac_address,
                time_savings=time_savings,
                start_time=start_time,
                console="",
                run_url=run_url,
                success=success,
                type="testrail",
                run_title=run_title,
            )
            if verbose:
                print(f"\n[TestRail] Datalake posted for run: {run_title!r}")
        except Exception as exc:
            if verbose:
                print(f"\n[TestRail] Datalake post failed: {exc}")

    # ------------------------------------------------------------------ #
    # Phase helpers                                                        #
    # ------------------------------------------------------------------ #

    def _find_run(self, project_id: int) -> Optional[Dict]:
        """Return the first EASY_BDD: run with pending tests created in the last 30 days."""
        created_after = int(time.time()) - 30 * 86400
        runs = self._tr.get_runs(project_id, created_after=created_after)
        for run in runs:
            if not run.get("name", "").startswith(self._run_prefix):
                continue
            if run.get("untested_count", 0) > 0 or run.get("retest_count", 0) > 0:
                return run
        return None

    def _classify_tests(self, tests: List[Dict]) -> List[Dict]:
        return [
            {
                **t,
                "role": _classify(t.get("title", "")),
                "clean_title": _strip_prefix(t.get("title", "")),
            }
            for t in tests
        ]

    def _extract_vars(self, classified: List[Dict]) -> Dict[str, Any]:
        """Parse key: value pairs from all Var: cases that have a flat mapping body.

        Var: cases whose body is a YAML steps list are skipped here; they are
        handled by _execute_step_var_cases, which runs the steps and harvests
        any variables set via store_as.

        After collecting all variables a second pass resolves ${var}
        cross-references so Var: cases can reference values defined in other
        Var: cases.
        """
        variables: Dict[str, Any] = {}
        for test in classified:
            if test["role"] != "var":
                continue
            body = _get_case_body(test)
            # Skip step-list bodies — handled by _execute_step_var_cases
            try:
                parsed = _yaml_safe_load_lenient(body)
                if isinstance(parsed, list):
                    continue
            except Exception:
                # If YAML parsing failed but the body contains list markers it's a
                # step list with syntax errors — skip it so we don't accidentally
                # pull step parameters (e.g. "folder_prefix: [upgrade, dummy]")
                # into the variable dict as if they were Var: key-value definitions.
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
        # Second pass: resolve ${var} cross-references (repeat until stable or 10 iterations)
        for _ in range(10):
            changed = False
            for k in list(variables.keys()):
                if not isinstance(variables[k], str) or "${" not in variables[k]:
                    continue
                new_val = variables[k]
                for ref_k, ref_v in variables.items():
                    if ref_k != k:
                        new_val = new_val.replace(f"${{{ref_k}}}", str(ref_v))
                if new_val != variables[k]:
                    variables[k] = _coerce(new_val)
                    changed = True
            if not changed:
                break
        return variables

    def _execute_step_var_cases(
        self,
        classified: List[Dict],
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> None:
        """Execute Var: cases whose body is a YAML steps list.

        Each step-list Var: case is run as a mini feature test.  Variables
        captured via store_as during execution are merged into injected_vars
        (and into the config scope) so subsequent Test:/Feature: cases can use
        them via ${variable_name}.

        The Var: case is always executed when there are pending tests,
        regardless of its current TestRail status.
        """
        import yaml as _yaml

        for case in classified:
            if case["role"] != "var":
                continue
            body = _get_case_body(case)
            if not body:
                continue
            # Fetch full case body if the run's test list doesn't include it
            has_body = bool(
                case.get("custom_preconds")
                or case.get("custom_steps")
                or case.get("custom_steps_separated")
            )
            if not has_body:
                case_id = case.get("case_id")
                if case_id:
                    try:
                        full = self._tr.get_case(int(case_id))
                        case = {**full, **{k: v for k, v in case.items() if v is not None}}
                        body = _get_case_body(case)
                    except Exception:
                        pass
            try:
                body_fixed = _fix_step_list_indent(body)
                parsed = _yaml_safe_load_lenient(body_fixed)
            except Exception:
                continue
            if not isinstance(parsed, list):
                continue  # flat key:value — handled by _extract_vars
            steps_raw = [s for s in parsed if isinstance(s, dict)]
            if not steps_raw:
                continue

            title = case.get("clean_title", "Var steps")
            test_dict = {"name": title, "steps": steps_raw}
            test_id = case.get("id", "var_steps")
            tmp_path = self._artifact_dir / f"_var_{test_id}.yaml"
            try:
                self._artifact_dir.mkdir(parents=True, exist_ok=True)
                with open(tmp_path, "w", encoding="utf-8") as f:
                    _yaml.dump(test_dict, f, allow_unicode=True,
                               default_flow_style=False, sort_keys=False)

                if verbose:
                    print(f"  [VAR] Executing step-based Var case: {title}")

                # Inject current vars so ${aws_bucket} etc. resolve inside the steps
                for k, v in injected_vars.items():
                    self._config.set_variable(k, str(v), scope="collection_vars")

                result = self._run_single(tmp_path, injected_vars, verbose)
                if result is None:
                    if verbose:
                        print(f"  [warn] Var case '{title}' failed to execute")
                    continue

                # Harvest all variables that the steps set at runtime
                try:
                    runtime_vars = self._config.variable_manager.get_all_variables()
                    for k, v in runtime_vars.items():
                        if k not in injected_vars or injected_vars[k] != v:
                            injected_vars[k] = v
                            if verbose:
                                preview = str(v)[:80]
                                print(f"    → {k} = {preview}")
                except Exception:
                    pass

                # Also scan step store_as fields for any not already captured
                for step in steps_raw:
                    sa = step.get("store_as") or (
                        list(step.values())[0].get("store_as")
                        if isinstance(list(step.values())[0], dict) else None
                    ) if step else None
                    if sa and sa not in injected_vars:
                        val = self._config.variable_manager.get_variable(sa)
                        if val is not None:
                            injected_vars[sa] = val

                # Expand gv.tests['variables']['$key'] store_as paths to plain
                # '$key' entries so Feature tests can access them via the
                # gv.tests['variables'] shim which returns the variables dict.
                for k, v in list(injected_vars.items()):
                    m = _GV_VAR_RE.match(str(k))
                    if m:
                        inner = m.group(1)
                        if inner not in injected_vars:
                            injected_vars[inner] = v

            except Exception as exc:
                if verbose:
                    print(f"  [warn] Var case '{title}' error: {exc}")
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    # Status IDs that mean "this test needs to be run"
    _PENDING_STATUSES = frozenset({
        TestRailService.STATUS_UNTESTED,
        TestRailService.STATUS_RETEST,
    })

    def _execute_cases(
        self,
        classified: List[Dict],
        static_extra: Dict[str, Any],
        run_id: int,
        verbose: bool,
    ) -> Tuple[int, int, int]:
        """Run Setup → Test → Teardown cases in order, posting results to TR in real-time.

        Only Test: cases in untested or retest status are executed.
        Setup: and Teardown: cases always run when there are pending tests.
        Var: cases are always re-extracted here so variables are current even
        when the Var: case status is already Passed from a previous run.
        """
        passed = failed = skipped = 0

        # Re-extract Var: variables every execution so they are always current,
        # regardless of the Var: case's current TestRail status.  Mirrors how
        # _sync_keyword_cases unconditionally rebuilds shared_steps.yaml.
        injected_vars = self._extract_vars(classified)
        injected_vars.update(static_extra)  # static overrides win

        # Execute any step-based Var: cases (bodies that are YAML step lists)
        # so their store_as outputs land in injected_vars before tests run.
        self._execute_step_var_cases(classified, injected_vars, verbose)

        if verbose and injected_vars:
            print(
                f"  [vars] {len(injected_vars)} variable(s) loaded: "
                f"{list(injected_vars.keys())}"
            )

        # Build shared_steps.yaml from Shared: cases so Feature: cases can reference them
        self._sync_keyword_cases(classified)

        # Filter Test: / Feature: cases to only those that need running
        pending_tests = [
            t for t in classified
            if t["role"] in ("test", "inline")
            and t.get("status_id", TestRailService.STATUS_UNTESTED) in self._PENDING_STATUSES
        ]

        if not pending_tests:
            if verbose:
                print("  No pending tests (untested or retest) — nothing to execute.")
            self._mark_definitions(classified)
            return passed, failed, skipped

        setups = [t for t in classified if t["role"] == "setup"]
        teardowns = [t for t in classified if t["role"] == "teardown"]
        execution_order = setups + pending_tests + teardowns

        build_url = os.getenv("BUILD_URL", "")
        build_number = os.getenv("BUILD_NUMBER", "")
        jenkins_footer = (
            f"\n\nJenkins Build #{build_number}: {build_url}console"
            if build_url else ""
        )

        def _on_cancel(signum, frame):
            if self._inflight_test_id is not None:
                try:
                    self._tr.add_result(
                        self._inflight_test_id,
                        status_id=TestRailService.STATUS_FAILED,
                        comment=f"Test cancelled — Jenkins job was aborted{jenkins_footer}",
                    )
                except Exception:
                    pass
            signal.signal(signal.SIGTERM, _prev_sigterm)
            signal.signal(signal.SIGINT, _prev_sigint)
            raise SystemExit(1)

        _prev_sigterm = signal.signal(signal.SIGTERM, _on_cancel)
        _prev_sigint = signal.signal(signal.SIGINT, _on_cancel)

        try:
            for case in execution_order:
                test_id = case["id"]
                title = case["clean_title"]
                role = case["role"]
                body = _get_case_body(case)

                if verbose:
                    role_label = {
                        "inline": "FEATURE",
                        "keyword": "SHARED",
                    }.get(role, role.upper())
                    print(f"\n  [{role_label}] {title}")

                # Mark test as Running immediately so TestRail reflects live state
                self._inflight_test_id = test_id
                try:
                    self._tr.add_result(
                        test_id,
                        status_id=self._running_status_id,
                        comment="Running...",
                    )
                except Exception:
                    pass

                start_time = time.time()

                if role == "inline":
                    test_passed, comment_lines = self._run_feature(case, injected_vars, verbose)
                else:
                    yaml_files = self._resolve(body, title, injected_vars)
                    if not yaml_files:
                        elapsed = _format_elapsed(time.time() - start_time)
                        if not body:
                            comment = (
                                "Case body is empty.\n"
                                "Test: cases: add 'tag: <tag>' or 'file: <path>' to the Steps field.\n"
                                "To write steps directly in TestRail, rename to 'Feature: <title>'."
                            )
                        elif not (body.startswith("tag:") or body.startswith("file:")):
                            comment = (
                                f"Unrecognised body format. Use:\n"
                                f"  tag: <tag>    — run all local YAMLs with that tag\n"
                                f"  file: <path>  — run a specific YAML file\n"
                                f"Or rename the case to 'Feature: {title}' to write steps directly.\n\n"
                                f"Body received:\n{body[:200]}"
                            )
                        else:
                            comment = f"No YAML tests found matching: {body[:200]}"
                        self._tr.add_result(
                            test_id,
                            status_id=TestRailService.STATUS_FAILED,
                            comment=comment + jenkins_footer,
                            elapsed=elapsed,
                        )
                        self._inflight_test_id = None
                        failed += 1
                        if verbose:
                            print(f"    FAIL — {comment.splitlines()[0]}")
                        continue
                    test_passed, comment_lines = self._run_yaml_files(
                        yaml_files, injected_vars, verbose
                    )

                elapsed = _format_elapsed(time.time() - start_time)
                comment = "\n".join(comment_lines) or ("Passed" if test_passed else "Failed")
                status_id = (
                    TestRailService.STATUS_PASSED
                    if test_passed
                    else TestRailService.STATUS_FAILED
                )

                self._tr.add_result(test_id, status_id=status_id, comment=comment + jenkins_footer, elapsed=elapsed)
                self._inflight_test_id = None

                if test_passed:
                    passed += 1
                    if verbose:
                        print(f"    PASS ({elapsed})")
                else:
                    failed += 1
                    if verbose:
                        print(f"    FAIL ({elapsed})")

        finally:
            signal.signal(signal.SIGTERM, _prev_sigterm)
            signal.signal(signal.SIGINT, _prev_sigint)
            self._inflight_test_id = None

        # Mark definition cases (Shared: / Var:) as passed so they don't
        # remain "untested" in the run. They are not executable directly.
        self._mark_definitions(classified)

        return passed, failed, skipped

    _DEFINITION_ROLES = {
        "keyword": "Shared step definition (Shared:)",
        "var": "Variable definition",
    }

    def _mark_definitions(self, classified: List[Dict]) -> None:
        """Mark Shared: and Var: cases as Passed so they don't stay Untested or Retest in the run."""
        for case in classified:
            role = case.get("role", "")
            if role not in self._DEFINITION_ROLES:
                continue
            if case.get("status_id", TestRailService.STATUS_UNTESTED) not in self._PENDING_STATUSES:
                continue
            label = self._DEFINITION_ROLES[role]
            try:
                self._tr.add_result(
                    case["id"],
                    status_id=TestRailService.STATUS_PASSED,
                    comment=f"{label} — not directly executable. Referenced via shared_step actions in Feature: cases.",
                )
            except Exception:
                pass

    def _run_yaml_files(
        self,
        yaml_files: List[Path],
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> Tuple[bool, List[str]]:
        """Execute a list of YAML files; return (all_passed, comment_lines)."""
        all_passed = True
        comment_lines: List[str] = []

        for yaml_path in yaml_files:
            result = self._run_single(yaml_path, injected_vars, verbose)
            if result is None:
                all_passed = False
                comment_lines.append(f"ERROR: could not execute {yaml_path.name}")
                continue

            for detail in result.test_details or []:
                name = detail.get("name", yaml_path.stem)
                status = detail.get("status", "FAILED")
                line = f"{status}: {name}"
                if status == "FAILED":
                    err = detail.get("error") or ""
                    log = detail.get("execution_log") or ""
                    tail = "\n".join(log.splitlines()[-10:]) if log else ""
                    if err:
                        line += f"\n{err}"
                    if tail:
                        line += f"\n---\n{tail}"
                comment_lines.append(line)

            if not result.success:
                all_passed = False

        return all_passed, comment_lines

    def _run_single(
        self,
        yaml_path: Path,
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> Optional[TestResult]:
        try:
            # Inject TestRail variables into the collection scope.
            # Preserve list/dict types so steps like aws.list_files can receive
            # folder_prefix as an actual list rather than its string repr.
            if injected_vars:
                for k, v in injected_vars.items():
                    self._config.set_variable(
                        k,
                        v if isinstance(v, (list, dict)) else str(v),
                        scope="collection_vars",
                    )

            runner = TestRunner(self._config, log_dir=self._artifact_dir)
            return runner.run(yaml_path)
        except Exception as exc:
            if verbose:
                print(f"    ERROR running {yaml_path.name}: {exc}")
            return None

    def _build_inline_test_dict(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build an in-memory Easy BDD test dict from a Feature: case.

        Read priority:
          1. custom_preconds as YAML list  → plain steps list written by UI or converter
          2. custom_preconds as dict with 'steps' key → steps + optional variables block
          3. custom_preconds as plain dict with action key → single-step shorthand
          4. custom_steps_separated rows   → structured content/expected (Option B)
          5. custom_steps text             → raw YAML steps (Option A, legacy)

        The Summary field (custom_summary) is never read; it is reserved for
        documentation and has no effect on test execution.
        """
        import yaml as _yaml

        title = case.get("clean_title", case.get("title", "Feature Test"))
        steps: List[Dict[str, Any]] = []
        variables: Dict[str, Any] = {}
        data_sets: Optional[List[Dict[str, Any]]] = None

        preconds_text = _html_to_text(case.get("custom_preconds") or "")
        if preconds_text:
            # Extract "JSON:\n[...]" data prefix for parameterized runs
            data_sets, preconds_text = _extract_inline_data(preconds_text)
            # Re-indent step params that are flush-left in TestRail's editor
            preconds_text = _fix_step_list_indent(preconds_text)
            try:
                parsed = _yaml_safe_load_lenient(preconds_text)
                if isinstance(parsed, list):
                    steps = [s for s in parsed if isinstance(s, dict)]
                elif isinstance(parsed, dict) and "steps" in parsed:
                    steps = [s for s in (parsed.get("steps") or []) if isinstance(s, dict)]
                    variables = {
                        str(k).lstrip("$"): v
                        for k, v in (parsed.get("variables") or {}).items()
                    }
                    # Support full YAML format: data: + steps: (mirrors local YAML files)
                    if parsed.get("data") and isinstance(parsed["data"], list):
                        data_sets = parsed["data"]
                elif isinstance(parsed, dict):
                    # Any dict in preconds → single step (covers both `action:` and short-key formats)
                    steps = [parsed]
                # else: plain string/scalar → fall through to legacy
            except Exception as _exc:
                print(f"  [warn] Could not parse Preconditions as YAML: {_exc}")

        if not steps:
            # Legacy / Option B fallback
            structured = case.get("custom_steps_separated") or []
            has_structured = isinstance(structured, list) and any(
                isinstance(r, dict) and (r.get("content") or r.get("expected"))
                for r in structured
            )
            if has_structured:
                steps = _parse_structured_steps(case)
            else:
                # custom_steps may be a string (plain text) or a list (structured field)
                raw_steps = case.get("custom_steps")
                if isinstance(raw_steps, list):
                    # Treat as structured rows if they have content/expected keys
                    if any(isinstance(r, dict) and (r.get("content") or r.get("expected"))
                           for r in raw_steps):
                        steps = _parse_structured_steps({"custom_steps_separated": raw_steps})
                    else:
                        body = " ".join(
                            str(r.get("content", r)) for r in raw_steps if r
                        )
                        steps = _parse_inline_body(body)
                else:
                    steps = _parse_inline_body(raw_steps or "")
            if not variables:
                variables = _parse_preconds_vars(case)

        if not steps:
            return None

        result: Dict[str, Any] = {"name": title, "steps": steps}
        if variables:
            result["variables"] = variables
        if data_sets:
            result["data"] = data_sets
        return result

    def _run_feature(
        self,
        case: Dict[str, Any],
        injected_vars: Dict[str, Any],
        verbose: bool,
    ) -> Tuple[bool, List[str]]:
        """Execute a Feature: case by materialising it as a temp YAML file."""
        import yaml as _yaml

        # If the test object from get_tests lacks case body fields, fetch the full case.
        # TestRail sometimes doesn't include custom_preconds/custom_steps in the run's
        # test list — calling get_case by case_id gets the authoritative data.
        has_body = bool(
            case.get("custom_preconds")
            or case.get("custom_steps")
            or case.get("custom_steps_separated")
        )
        if not has_body:
            case_id = case.get("case_id")
            if case_id:
                try:
                    full_case = self._tr.get_case(int(case_id))
                    # Merge: keep test-level fields (id, status_id, etc.), overlay case body
                    case = {**full_case, **{k: v for k, v in case.items() if v is not None}}
                    print(f"  [info] Fetched full case body from get_case({case_id})")
                except Exception as _e:
                    print(f"  [warn] Could not fetch case body for case_id={case_id}: {_e}")

        test_dict = self._build_inline_test_dict(case)
        if not test_dict:
            # Debug: show raw field lengths to aid diagnosis
            preconds_raw = case.get("custom_preconds") or ""
            steps_raw    = case.get("custom_steps") or ""
            preconds_clean = _html_to_text(preconds_raw)
            steps_clean    = _html_to_text(str(steps_raw)) if isinstance(steps_raw, str) else str(steps_raw)
            debug_lines = [
                f"  [debug] custom_preconds ({len(preconds_raw)} chars raw → {len(preconds_clean)} clean): "
                f"{repr(preconds_clean[:200])}",
                f"  [debug] custom_steps ({type(steps_raw).__name__}, len={len(str(steps_raw))} raw → "
                f"{len(steps_clean)} clean): {repr(steps_clean[:200])}",
            ]
            return False, [
                "Feature case has no steps.\n"
                + "\n".join(debug_lines) + "\n"
                "\nPaste steps in the Preconditions field using one of these formats:\n"
                "\n"
                "  PREFERRED (dot-notation, params may be flush-left):\n"
                "    - aws.list_files:\n"
                "    bucket_name: my-bucket\n"
                "    folder_prefix: vps/\n"
                "    store_as: firmware_files\n"
                "    - ovrc.connect:\n"
                "    device_id: ${mac}\n"
                "\n"
                "  PARAMETERIZED (JSON data prefix + steps):\n"
                "    JSON:\n"
                "    [{\"mac\": \"AA:BB:CC:DD\", \"bucket_name\": \"my-bucket\"}]\n"
                "\n"
                "    - aws.list_files:\n"
                "    bucket_name: ${bucket_name}\n"
                "    - ovrc.connect:\n"
                "    device_id: ${mac}\n"
                "\n"
                "  WITH VARIABLES (mirrors local YAML exactly):\n"
                "    variables:\n"
                "      base_url: https://staging.example.com\n"
                "    steps:\n"
                "      - api.request:\n"
                "          method: GET\n"
                "          url: ${base_url}/status\n"
            ]

        test_id = case.get("id", "tmp")
        tmp_path = self._artifact_dir / f"_inline_{test_id}.yaml"
        try:
            self._artifact_dir.mkdir(parents=True, exist_ok=True)
            self._sync_shared_steps_to_artifact_dir()
            with open(tmp_path, "w", encoding="utf-8") as f:
                _yaml.dump(test_dict, f, allow_unicode=True, default_flow_style=False,
                           sort_keys=False)
            return self._run_yaml_files([tmp_path], injected_vars, verbose)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _sync_keyword_cases(self, classified: List[Dict]) -> None:
        """Parse Shared: cases and write them into artifact_dir/shared_steps.yaml.

        Each Shared: case becomes one entry in shared_steps.yaml, keyed by its
        clean_title (title with the 'Shared: ' prefix stripped).

        Accepted Preconditions formats:

          Full definition (description + parameters + steps):
            description: Connect to OvrC server
            parameters:
              - server_url
              - mac
            steps:
              - ovrc.connect:
                  auth_type: bearer
                  server_url: ${server_url}
                  device_id: ${mac}

          Steps-only shorthand (no wrapper dict):
            - ovrc.connect:
            auth_type: bearer
            server_url: ${server_url}
            device_id: ${mac}
            - ovrc.disconnect: {}
        """
        import yaml as _yaml

        keyword_cases = [c for c in classified if c.get("role") == "keyword"]
        if not keyword_cases:
            return

        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        out = self._artifact_dir / "shared_steps.yaml"

        existing: Dict[str, Any] = {}
        if out.exists():
            try:
                with open(out, encoding="utf-8") as f:
                    existing = _yaml.safe_load(f) or {}
            except Exception:
                pass

        updated = False
        for case in keyword_cases:
            raw_name = case.get("clean_title", "").strip()
            if not raw_name:
                continue
            # Normalize to match the slug generated by bdd_migrator for shared_step refs:
            # re.sub(r"[^A-Za-z0-9_]+", "_", name) — spaces and non-word chars → "_"
            name = _re_mod.sub(r"[^A-Za-z0-9_]+", "_", raw_name).strip("_")

            # Fetch full body if missing
            has_body = bool(
                case.get("custom_preconds")
                or case.get("custom_steps")
                or case.get("custom_steps_separated")
            )
            if not has_body:
                case_id = case.get("case_id")
                if case_id:
                    try:
                        full = self._tr.get_case(int(case_id))
                        case = {**full, **{k: v for k, v in case.items() if v is not None}}
                    except Exception:
                        pass

            body = _html_to_text(case.get("custom_preconds") or "")
            if not body:
                body = _html_to_text(str(case.get("custom_steps") or ""))
            if not body:
                continue

            # Apply same indentation fix as Feature: cases
            body = _fix_step_list_indent(body)

            try:
                parsed = _yaml_safe_load_lenient(body)
            except Exception as exc:
                print(f"  [warn] Shared '{name}': could not parse body: {exc}")
                continue

            if isinstance(parsed, list):
                # Steps-only shorthand → wrap in a definition dict
                steps_raw = _normalize_shared_step_refs([s for s in parsed if isinstance(s, dict)])
                entry = {"steps": steps_raw}
            elif isinstance(parsed, dict) and "steps" in parsed:
                # Full definition dict — normalize shared_step refs in the steps list
                entry = {**parsed, "steps": _normalize_shared_step_refs(parsed.get("steps") or [])}
            elif isinstance(parsed, dict):
                # Single-step dict
                entry = {"steps": _normalize_shared_step_refs([parsed])}
            else:
                print(f"  [warn] Shared '{name}': unrecognised body format, skipping")
                continue

            if existing.get(name) != entry:
                existing[name] = entry
                updated = True

        if updated:
            try:
                with open(out, "w", encoding="utf-8") as f:
                    _yaml.dump(existing, f, allow_unicode=True,
                               default_flow_style=False, sort_keys=False)
                print(f"  [info] Wrote {len([c for c in keyword_cases if c.get('clean_title')])} "
                      f"shared step(s) to {out.name}")
            except Exception as exc:
                print(f"  [warn] Could not write shared_steps.yaml: {exc}")

    def _sync_shared_steps_to_artifact_dir(self) -> None:
        """Merge all shared_steps.yaml files from tests_dir into artifact_dir.

        The parser looks for shared_steps.yaml in the same directory as the
        YAML file being parsed. Inline temp files land in artifact_dir, so
        shared steps must be there too.
        """
        import yaml as _yaml

        merged: Dict[str, Any] = {}
        for path in sorted(self._tests_dir.rglob("shared_steps.yaml")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = _yaml.safe_load(f) or {}
                if isinstance(data, dict):
                    merged.update(data)
            except Exception:
                pass

        if not merged:
            return

        out = self._artifact_dir / "shared_steps.yaml"
        try:
            existing: Dict[str, Any] = {}
            if out.exists():
                with open(out, encoding="utf-8") as f:
                    existing = _yaml.safe_load(f) or {}
            if existing != merged:
                existing.update(merged)
                with open(out, "w", encoding="utf-8") as f:
                    _yaml.dump(existing, f, allow_unicode=True,
                               default_flow_style=False, sort_keys=False)
        except Exception:
            pass

    def _skip_all(self, classified: List[Dict]) -> None:
        for case in classified:
            if case["role"] in ("test", "setup", "teardown"):
                try:
                    self._tr.add_result(
                        case["id"],
                        status_id=TestRailService.STATUS_BLOCKED,
                        comment="Skipped: outside cron window",
                    )
                except Exception:
                    pass

    def _mark_failed_for_retest(self, run_id: int) -> None:
        try:
            for test in self._tr.get_tests(run_id):
                if test.get("status_id") == TestRailService.STATUS_FAILED:
                    self._tr.add_result(
                        test["id"],
                        status_id=TestRailService.STATUS_RETEST,
                        comment="Marked for retry",
                    )
        except Exception:
            pass

    def _finalize(
        self,
        run_id: int,
        run_vars: RunVariables,
        passed: int,
        failed: int,
        skipped: int,
    ) -> None:
        summary = {
            **run_vars.to_dict(),
            "last_result": {
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "timestamp": datetime.now().isoformat(),
            },
        }
        try:
            self._tr.update_run(run_id, description=json.dumps(summary))
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Case body resolution                                                 #
    # ------------------------------------------------------------------ #

    def _resolve(
        self, body: str, title: str, variables: Dict[str, Any]
    ) -> List[Path]:
        """Resolve a case body string to a list of YAML file paths.

        Supported formats:
          tag: <tag>    — run all local YAMLs in tests_dir that have this tag
          file: <path>  — run a specific YAML file (relative to tests_dir or absolute)
        """
        body = (body or "").strip()
        if not body:
            return []

        if body.startswith("tag:"):
            return self._by_tag(body[4:].strip())
        if body.startswith("file:"):
            return self._by_file(body[5:].strip())

        # Unrecognised format — log it and return empty so it posts a clear failure
        return []

    def _by_tag(self, tag: str) -> List[Path]:
        import yaml
        matches: List[Path] = []
        for path in sorted(self._tests_dir.rglob("*.yaml")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict) and tag in (data.get("tags") or []):
                    matches.append(path)
            except Exception:
                continue
        return matches

    def _by_file(self, file_path: str) -> List[Path]:
        p = Path(file_path)
        if not p.is_absolute():
            p = self._tests_dir / file_path
        return [p] if p.exists() else []
