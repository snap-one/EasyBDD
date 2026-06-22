"""
YAML and JSON test definition parser with UI recorder support.

Lenient YAML utilities (strip_html_to_text, parse_yaml_lenient, etc.) live here
so that both the local runner and the TestRail runner share a single parse path.
"""

import html as _html_mod
import re as _re_mod
import yaml
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
import re


# ---------------------------------------------------------------------------
# Lenient YAML helpers — used when parsing TestRail rich-text content
# ---------------------------------------------------------------------------

def strip_html_to_text(raw: str) -> str:
    """Strip HTML tags and unescape entities from a TestRail rich-text field."""
    text = raw or ""
    text = _re_mod.sub(r"<br\s*/?>", "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"</p>",      "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"</div>",    "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"</li>",     "\n", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"<(p|div|li|ul|ol|pre|code)[^>]*>", "", text, flags=_re_mod.IGNORECASE)
    text = _re_mod.sub(r"<[^>]+>", "", text)
    text = _html_mod.unescape(text)
    # Normalize Unicode spaces (\xa0 etc.) to ASCII so YAML separators are recognised.
    text = _re_mod.sub(r"[^\S\n\r]", " ", text)
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join(lines).strip()


def _fix_yaml_indent(text: str) -> str:
    """Remove spurious continuation-line indentation from flat YAML dicts."""
    lines = text.splitlines()
    non_empty = [(i, ln) for i, ln in enumerate(lines) if ln.strip()]
    if len(non_empty) < 2:
        return text
    indents = [len(ln) - len(ln.lstrip()) for _, ln in non_empty]
    first_indent = indents[0]
    rest_min = min(indents[1:])
    if rest_min <= first_indent:
        return text
    extra = rest_min - first_indent
    result = list(lines)
    for i, ln in non_empty[1:]:
        curr_indent = len(ln) - len(ln.lstrip())
        if curr_indent >= extra:
            result[i] = ln[extra:]
    return "\n".join(result)


_BARE_QUOTED_LINE_RE     = _re_mod.compile(r'^(\s*)(["\'])([^:]*)\2\s*$')
_INLINE_BLOCK_SCALAR_RE  = _re_mod.compile(r'^(\s*)(\S[^:]*)\s*:\s*\|\s+(.+)$')
_YAML_KEY_OR_LIST_RE     = _re_mod.compile(r'^\s*(-\s+\S|#|\w[\w.\s]*:)')
_STEP_LINE_RE            = _re_mod.compile(r'^(\s*)- (\S[^:]*):(.*)$')
_PARAM_LINE_RE           = _re_mod.compile(r'^[A-Za-z_][\w. -]*\s*:')
_STEP_ANNOTATION_KEYS    = frozenset({'description', 'comment', 'note', 'label'})
# Control-flow keys that can legally appear as a root mapping dict that owns
# a subsequent bare sequence (the sequence becomes its 'steps:' value).
_LOOP_CONTROL_KEYS       = frozenset({'for_each', 'while', 'condition', 'if', 'try'})
_ROOT_MAPPING_KEY_RE     = _re_mod.compile(r'^([A-Za-z_][\w.\s-]*)\s*:')
# Root-level keys that must always appear at 0 indent in case YAML (never nested).
# MULTILINE so ^ / $ match at every line boundary in multi-line text.
_ROOT_KEYS_RE            = _re_mod.compile(r'^( +)(steps|variables|data)\s*:\s*$', _re_mod.MULTILINE)
# First line of a YAML block: a list item OR a mapping key (possibly indented).
_YAML_BLOCK_START_RE     = _re_mod.compile(r'^\s*(-\s+\S|[A-Za-z_][\w.\s-]*\s*:)')
# Bare list item — no colon after the leading '- ', so not an action mapping.
_BARE_SEQ_ITEM_RE        = _re_mod.compile(r'^- [^:\n]+$', _re_mod.MULTILINE)
# Root-level 'steps:' after de-indenting.
_ROOT_STEPS_ONLY_RE      = _re_mod.compile(r'^steps:\s*$', _re_mod.MULTILINE)


def _fix_inline_block_scalars(text: str) -> str:
    """Convert 'key: | content' (invalid YAML) to a proper block scalar."""
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
    """Strip surrounding quotes from lines that are just a quoted string with no colon."""
    result = []
    for line in text.splitlines():
        m = _BARE_QUOTED_LINE_RE.match(line)
        if m:
            line = m.group(1) + m.group(3)
        result.append(line)
    return "\n".join(result)


def _fix_plaintext_preamble(text: str) -> str:
    """Strip leading plain-text description lines that precede a YAML block.

    TestRail Preconditions sometimes start with a human-readable description
    (no YAML structure) followed by an indented YAML block, e.g.::

        Network Fault Insertion
        Device resiliency test
          steps:
            - ssh.connect: ...

    The plain-text lines cause the YAML parser to choke on ``steps:`` at a
    non-zero column.  Stripping those lines and de-indenting the remainder
    recovers valid YAML.
    """
    lines = text.splitlines()
    if not lines or _YAML_BLOCK_START_RE.match(lines[0]):
        return text  # first line already looks like YAML — nothing to strip

    yaml_start: Optional[int] = None
    for i, line in enumerate(lines):
        if line.strip() and _YAML_BLOCK_START_RE.match(line):
            yaml_start = i
            break

    if yaml_start is None:
        return text  # no YAML structure found at all

    yaml_lines = lines[yaml_start:]
    non_empty = [ln for ln in yaml_lines if ln.strip()]
    if not non_empty:
        return text

    min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_empty)
    if min_indent > 0:
        yaml_lines = [ln[min_indent:] if len(ln) > min_indent else ln.lstrip()
                      for ln in yaml_lines]
    return "\n".join(yaml_lines)


def _dedent_root_keys(text: str) -> str:
    """De-indent accidentally-indented root-level keys (steps, variables, data).

    TestRail rich-text conversion sometimes produces content where ``steps:``
    (or ``variables:`` / ``data:``) is indented by a few spaces, typically
    causing the YAML error: *mapping values are not allowed here*.  These keys
    are ONLY ever root-level in Easy-BDD case YAML, so normalising them to
    column 0 is always safe.
    """
    if not _ROOT_KEYS_RE.search(text):
        return text
    result = []
    for line in text.splitlines():
        m = _ROOT_KEYS_RE.match(line)
        result.append(line.lstrip() if m else line)
    return "\n".join(result)


def _extract_steps_block(text: str) -> str:
    """Extract the 'steps:' block when bare sequence items precede it at root level.

    After ``_dedent_root_keys`` runs, content like::

        - bare_description_1
        - bare_description_2
        steps:
          - ssh.command: ...

    is still invalid YAML (sequence then mapping at root).  When bare list items
    (no colon → not a valid action) appear before a root-level ``steps:`` key,
    the bare items are description text; return just the ``steps:`` block.
    """
    if not (_BARE_SEQ_ITEM_RE.search(text) and _ROOT_STEPS_ONLY_RE.search(text)):
        return text
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _re_mod.match(r'^steps:\s*$', line):
            return '\n'.join(lines[i:])
    return text


def fix_step_list_indent(text: str) -> str:
    """Re-indent step parameters that appear at the same level as their '-' marker."""
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
            if m.group(3).strip():
                continue
            param_prefix = ' ' * (dash_indent + 4)
            last_bare_key_indent: Optional[str] = None
            _bare_key_stack: list = []
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
                if stripped.startswith('- ') and nl_indent <= dash_indent:
                    if last_bare_key_indent is not None:
                        result.append(last_bare_key_indent + '  ' + stripped)
                        i += 1
                        continue
                    break
                if nl_indent <= dash_indent:
                    if dash_indent == 0 and _PARAM_LINE_RE.match(stripped):
                        while _bare_key_stack and _bare_key_stack[-1][0] >= nl_indent:
                            _bare_key_stack.pop()
                    elif last_bare_key_indent is not None and stripped and not stripped.startswith('- '):
                        if result and result[-1].rstrip().endswith(':'):
                            result[-1] = result[-1].rstrip() + ' ' + stripped
                        _bare_key_stack.pop()
                        last_bare_key_indent = None
                        i += 1
                        continue
                    else:
                        last_bare_key_indent = None
                        _bare_key_stack.clear()
                if nl_indent > dash_indent:
                    result.append(nl)
                    i += 1
                    continue
                if _PARAM_LINE_RE.match(stripped):
                    key = stripped.split(':', 1)[0].strip()
                    if key in _STEP_ANNOTATION_KEYS:
                        i += 1
                        continue
                    if _bare_key_stack:
                        current_prefix = _bare_key_stack[-1][1] + '  '
                    else:
                        current_prefix = param_prefix
                    result.append(current_prefix + stripped)
                    i += 1
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

    text = '\n'.join(result)
    out_lines = text.split('\n')
    fixed: List[str] = []
    j = 0
    while j < len(out_lines):
        ln = out_lines[j]
        if re.match(r'^[a-zA-Z_]\w*:\s*$', ln) and j + 1 < len(out_lines) and out_lines[j + 1].startswith('-'):
            fixed.append(ln)
            j += 1
            while j < len(out_lines):
                sub = out_lines[j]
                if sub and re.match(r'^[a-zA-Z_]\w*:\s*$', sub):
                    break
                fixed.append('  ' + sub if sub else sub)
                j += 1
        else:
            fixed.append(ln)
            j += 1
    return '\n'.join(fixed)


def _fix_mapping_then_sequence(text: str) -> str:
    """Fix content where a control-flow mapping dict has sequence items at column 0.

    TestRail authors sometimes write a for_each (or while/if/try) block as
    root-level mapping keys and then list the loop body as bare sequence items,
    either with or without a ``steps:`` key, e.g.::

        for_each: "[1, 10]"
        loop_var: item
        steps:
        - test.sleep:
        seconds: 120

    This is also common when TestRail stores content as HTML ``<p>`` paragraphs
    which HTML-to-text conversion turns into blank-line-separated lines —
    the blank line after ``steps:`` breaks the YAML indentation fixers.

    The fix strips blank lines (normalising HTML paragraph artifacts), then
    wraps everything as a single list item with sequence items under ``steps:``
    at 4-space indent.  The sibling parameter fixer (``fix_step_list_indent``)
    will run afterward and lift flat params to their correct indent level::

        - for_each: "[1, 10]"
          loop_var: item
          steps:
            - test.sleep:
                seconds: 120
    """
    lines = text.splitlines()
    if not lines:
        return text

    # First non-blank, non-comment line must be a root-level control-flow key.
    first_content = next(
        (l for l in lines if l.strip() and not l.strip().startswith('#')), None
    )
    if first_content is None or first_content.startswith(' ') or first_content.startswith('-'):
        return text
    m = _ROOT_MAPPING_KEY_RE.match(first_content)
    if not m or m.group(1).strip() not in _LOOP_CONTROL_KEYS:
        return text

    # Collapse blank lines — TestRail HTML-to-text conversion often inserts one
    # blank line between every content line (<p>…</p> per line).  Stripping
    # blank lines lets the subsequent fixers work on clean, contiguous content.
    non_blank = [l for l in lines if l.strip()]
    if not non_blank:
        return text

    # Locate the first root-level sequence item in the blank-stripped content.
    seq_start = None
    for i, line in enumerate(non_blank):
        if line.startswith('- '):
            seq_start = i
            break

    if seq_start is None:
        return text

    # Detect whether 'steps:' is already a key in the mapping portion.
    has_steps_key = any(
        _re_mod.match(r'^steps\s*:', line.strip())
        for line in non_blank[:seq_start]
    )

    # Build the corrected structure:
    #   - <first mapping key>
    #     <other mapping keys, including steps: if present>
    #     steps:           ← inserted only when not already present
    #       <sequence items, each prefixed with 4 extra spaces>
    result: List[str] = []
    first = True
    for i, line in enumerate(non_blank):
        if i < seq_start:
            if first:
                result.append(f"- {line.strip()}")
                first = False
            else:
                result.append(f"  {line.strip()}")
        elif i == seq_start:
            if not has_steps_key:
                result.append("  steps:")
            result.append(f"    {line}")
        else:
            result.append(f"    {line}" if line.strip() else "")

    return "\n".join(result)


def parse_yaml_lenient(text: str) -> Any:
    """Parse YAML text, retrying with repair passes if the first attempt fails.

    Use this for content from TestRail or any source where indentation or
    quoting may be imperfect. The local runner should use yaml.safe_load
    directly (strict mode).
    """
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        pass
    for fixer in (
        _fix_yaml_indent,
        _fix_inline_block_scalars,
        _unquote_bare_string_lines,
        _fix_plaintext_preamble,
        _dedent_root_keys,
        _extract_steps_block,
        _fix_mapping_then_sequence,
        fix_step_list_indent,
    ):
        fixed = fixer(text)
        if fixed != text:
            try:
                return yaml.safe_load(fixed)
            except yaml.YAMLError:
                text = fixed
    return yaml.safe_load(text)  # final attempt — raises if still broken


@dataclass
class TestStep:
    """Represents a single test step"""

    action: str
    parameters: Dict[str, Any]
    shared_step: Optional[str] = None
    condition: Optional[str] = None  # Conditional expression
    then_steps: Optional[List["TestStep"]] = None  # Steps if condition true
    else_steps: Optional[List["TestStep"]] = None  # Steps if condition false
    retry_config: Optional[Dict[str, Any]] = None  # Retry configuration
    # FOR loop
    for_each: Optional[str] = None   # Expression that yields an iterable
    loop_var: Optional[str] = None   # Variable name bound to each item
    loop_steps: Optional[List["TestStep"]] = None  # Body of loop
    # WHILE loop
    while_condition: Optional[str] = None  # Loop-continue expression
    loop_limit: int = 1000           # Safety cap on iterations
    # TRY/EXCEPT/FINALLY
    try_steps: Optional[List["TestStep"]] = None
    except_steps: Optional[List["TestStep"]] = None
    finally_steps: Optional[List["TestStep"]] = None
    # Break/continue guards (valid inside any loop body)
    break_if: Optional[str] = None
    continue_if: Optional[str] = None

    def __post_init__(self):
        # Ensure parameters is a dictionary
        if not isinstance(self.parameters, dict):
            self.parameters = {}


@dataclass
class SharedStep:
    """Represents a reusable shared step sequence"""

    name: str
    description: str
    parameters: List[str]
    steps: List[TestStep]


@dataclass
class TestDefinition:
    """Represents a complete test definition"""

    name: str
    description: str
    file_path: Path
    tags: List[str]
    variables: Dict[str, Any]
    setup: List[TestStep]
    steps: List[TestStep]
    cleanup: List[TestStep]
    data_source: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    async_execution: bool = False
    max_workers: int = 1
    device_config: Optional[str] = None  # Device configuration file reference
    browsers: Optional[List[str]] = None  # Run test on multiple browsers e.g. [chromium, firefox, webkit]
    record_video: Optional[bool] = None  # Enable video recording for this test (browser actions only)

    def __post_init__(self):
        # Ensure all list fields are lists
        if not isinstance(self.tags, list):
            self.tags = []
        if not isinstance(self.setup, list):
            self.setup = []
        if not isinstance(self.steps, list):
            self.steps = []
        if not isinstance(self.cleanup, list):
            self.cleanup = []
        if not isinstance(self.variables, dict):
            self.variables = {}


class YAMLParser:
    """Parser for YAML test definitions"""

    def __init__(self):
        self.supported_extensions = {".yaml", ".yml", ".json"}
        self.shared_steps: Dict[str, SharedStep] = {}
        self._load_shared_steps()

    def _load_shared_steps(self, workspace_dir: Optional[Path] = None) -> None:
        """Load shared steps: global file first, then workspace-local (overrides global).

        Uses a two-pass approach so that shared steps can reference each other
        regardless of their order in the YAML file:
          Pass 1 — collect all raw step-list dicts from every candidate file.
          Pass 2 — parse each entry in dependency order (topological sort) so
                   nested shared_step references are already registered when a
                   dependent entry is parsed.
        """
        candidates = [Path("shared_steps.yaml")]
        if workspace_dir is not None:
            candidates.append(Path(workspace_dir) / "shared_steps.yaml")

        # Pass 1: gather raw data from all candidate files (later files override earlier)
        raw: Dict[str, Dict[str, Any]] = {}
        for shared_steps_path in candidates:
            if not shared_steps_path.exists():
                continue
            try:
                with open(shared_steps_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if isinstance(data, dict):
                    for name, step_data in data.items():
                        if isinstance(step_data, dict):
                            raw[name] = step_data
            except Exception as e:
                print(f"Warning: Failed to load shared steps from {shared_steps_path}: {e}")

        # Helper: extract direct shared_step dependencies from a raw step list
        def _deps(steps_raw: List[Any]) -> List[str]:
            return [s["shared_step"] for s in (steps_raw or [])
                    if isinstance(s, dict) and "shared_step" in s]

        # Pass 2: topological sort so dependencies are parsed before dependents
        order: List[str] = []
        visiting: set = set()
        visited: set = set()

        def _visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                # Cycle — skip; _expand_shared_step raises a clear error at runtime
                return
            visiting.add(name)
            for dep in _deps((raw.get(name) or {}).get("steps", [])):
                if dep in raw:
                    _visit(dep)
            visiting.discard(name)
            visited.add(name)
            order.append(name)

        for name in raw:
            _visit(name)

        # Parse in dependency order so nested refs are already registered
        for name in order:
            step_data = raw[name]
            try:
                shared_step = SharedStep(
                    name=name,
                    description=step_data.get("description", ""),
                    parameters=step_data.get("parameters", []),
                    steps=self._parse_steps(step_data.get("steps", [])),
                )
                self.shared_steps[name] = shared_step
            except Exception as e:
                print(f"Warning: Failed to parse shared step '{name}': {e}")

    def parse_file(self, file_path: Path) -> TestDefinition:
        """Parse a single YAML test file, loading workspace-local shared steps if present."""
        file_path = Path(file_path)
        # Reload workspace-local shared steps (local overrides global)
        self._load_shared_steps(workspace_dir=file_path.parent)

        if not file_path.exists():
            error_info = self._create_test_error_info(
                file_path=file_path,
                error_type="FileNotFoundError",
                error_message=f"Test file not found: {file_path}",
                error_details={"absolute_path": str(file_path.absolute())}
            )
            self._handle_test_load_error(error_info)
            raise FileNotFoundError(f"Test file not found: {file_path}")

        if file_path.suffix.lower() not in self.supported_extensions:
            error_info = self._create_test_error_info(
                file_path=file_path,
                error_type="ValueError",
                error_message=f"Unsupported file extension: {file_path.suffix}",
                error_details={"supported_extensions": list(self.supported_extensions)}
            )
            self._handle_test_load_error(error_info)
            raise ValueError(f"Unsupported file extension: {file_path.suffix}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                if file_path.suffix.lower() == ".json":
                    data = json.load(f)
                    # Check if it's a recorder format
                    data = self._detect_and_convert_recorder_format(data, file_path)
                else:
                    data = yaml.safe_load(f)
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            error_info = self._create_test_error_info(
                file_path=file_path,
                error_type=type(e).__name__,
                error_message=f"Invalid file format in {file_path}: {e}",
                error_details={"error": str(e), "line": getattr(e, "line", None), "column": getattr(e, "column", None)}
            )
            self._handle_test_load_error(error_info)
            raise ValueError(f"Invalid file format in {file_path}: {e}")

        if not isinstance(data, dict):
            error_info = self._create_test_error_info(
                file_path=file_path,
                error_type="ValueError",
                error_message=f"YAML file must contain a dictionary: {file_path}",
                error_details={"data_type": type(data).__name__}
            )
            self._handle_test_load_error(error_info)
            raise ValueError(f"YAML file must contain a dictionary: {file_path}")

        try:
            return self._parse_test_definition(data, file_path)
        except Exception as e:
            error_info = self._create_test_error_info(
                file_path=file_path,
                error_type=type(e).__name__,
                error_message=f"Failed to parse test definition: {e}",
                error_details={"error": str(e)}
            )
            self._handle_test_load_error(error_info)
            raise
    
    def _create_test_error_info(
        self, file_path: Path, error_type: str, error_message: str, error_details: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Create structured error information for test loading failures"""
        file_path = Path(file_path)
        return {
            "file_path": str(file_path),
            "absolute_path": str(file_path.absolute()),
            "relative_path": str(file_path.relative_to(Path.cwd())) if file_path.is_relative_to(Path.cwd()) else str(file_path),
            "file_name": file_path.name,
            "error_type": error_type,
            "error_message": error_message,
            "error_details": error_details or {},
            "can_edit": file_path.exists() and file_path.is_file(),
        }
    
    def _handle_test_load_error(self, error_info: Dict[str, Any]) -> None:
        """Handle test loading errors with helpful messages and edit options"""
        file_path = Path(error_info["file_path"])
        print(f"\n{'='*80}")
        print(f"❌ FAILED TO LOAD TEST")
        print(f"{'='*80}")
        print(f"📁 File: {error_info['file_path']}")
        print(f"   Absolute: {error_info['absolute_path']}")
        if error_info.get('relative_path') != error_info['file_path']:
            print(f"   Relative: {error_info['relative_path']}")
        print(f"🔴 Error Type: {error_info['error_type']}")
        print(f"💬 Message: {error_info['error_message']}")
        
        if error_info.get('error_details'):
            print(f"📋 Details:")
            for key, value in error_info['error_details'].items():
                print(f"   {key}: {value}")
        
        if error_info['can_edit']:
            print(f"\n✏️  To edit this file, run:")
            print(f"   python -m easy_bdd edit-test \"{error_info['file_path']}\"")
            print(f"   Or manually open: {error_info['absolute_path']}")
            
            # Try to detect and suggest editor commands
            editor_commands = self._get_editor_commands(file_path)
            if editor_commands:
                print(f"\n   Quick edit commands:")
                for cmd_name, cmd in editor_commands.items():
                    print(f"   {cmd_name}: {cmd}")
        else:
            print(f"\n⚠️  File does not exist or is not accessible")
        
        print(f"{'='*80}\n")
    
    def _get_editor_commands(self, file_path: Path) -> Dict[str, str]:
        """Get platform-specific editor commands for opening a file"""
        commands = {}
        file_path_str = str(file_path.absolute())
        
        system = platform.system().lower()
        
        if system == "darwin":  # macOS
            commands["Open in default editor"] = f"open {file_path_str}"
            commands["Open in VS Code"] = f"code {file_path_str}"
            commands["Open in TextEdit"] = f"open -a TextEdit {file_path_str}"
        elif system == "linux":
            # Try common editors
            editors = ["code", "vim", "nano", "gedit", "kate"]
            for editor in editors:
                if self._command_exists(editor):
                    commands[f"Open in {editor}"] = f"{editor} {file_path_str}"
                    break
            if not commands:
                commands["Open in default editor"] = f"xdg-open {file_path_str}"
        elif system == "windows":
            commands["Open in default editor"] = f"start {file_path_str}"
            commands["Open in VS Code"] = f"code {file_path_str}"
            commands["Open in Notepad"] = f"notepad {file_path_str}"
        
        return commands
    
    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in PATH"""
        try:
            subprocess.run(
                ["which", command] if platform.system() != "Windows" else ["where", command],
                capture_output=True,
                check=True
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def parse_directory(self, directory_path: Path) -> List[TestDefinition]:
        """Parse all YAML files in a directory"""
        directory_path = Path(directory_path)

        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        if not directory_path.is_dir():
            raise ValueError(f"Path is not a directory: {directory_path}")

        test_files = []
        for ext in self.supported_extensions:
            test_files.extend(directory_path.glob(f"**/*{ext}"))

        tests = []
        for file_path in test_files:
            try:
                test = self.parse_file(file_path)
                tests.append(test)
            except Exception as e:
                # Error handling is done in parse_file, just log a summary here
                print(f"⚠️  Skipping {file_path.name} due to parsing error")

        return tests

    def _parse_test_definition(
        self, data: Dict[str, Any], file_path: Path
    ) -> TestDefinition:
        """Parse test definition from YAML data"""
        # Required fields
        if "name" not in data:
            raise ValueError("Test definition must have a 'name' field")

        if "steps" not in data:
            raise ValueError("Test definition must have a 'steps' field")

        # Extract basic fields
        name = data["name"]
        description = data.get("description", "")
        tags = data.get("tags", [])
        variables = data.get("variables", {})
        data_source = data.get("data_source")
        device_config = data.get("device_config")  # Device configuration file reference
        browsers = data.get("browsers")  # e.g. [chromium, firefox, webkit]
        if isinstance(browsers, str):
            browsers = [b.strip() for b in browsers.split(",") if b.strip()]
        record_video = data.get("record_video")  # Optional per-test video recording flag

        # Extract data-driven fields
        test_data = data.get("data", None)
        async_execution = data.get("async_execution", False)
        max_workers = data.get("max_workers", 1)

        # Parse steps
        setup_steps = self._parse_steps(data.get("setup", []))
        test_steps = self._parse_steps(data["steps"])
        cleanup_steps = self._parse_steps(data.get("cleanup", []))

        return TestDefinition(
            name=name,
            description=description,
            file_path=file_path,
            tags=tags,
            variables=variables,
            setup=setup_steps,
            steps=test_steps,
            cleanup=cleanup_steps,
            data_source=data_source,
            data=test_data,
            async_execution=async_execution,
            max_workers=max_workers,
            device_config=device_config,
            browsers=browsers,
            record_video=record_video,
        )

    def _parse_steps(self, steps_data: List[Dict[str, Any]]) -> List[TestStep]:
        """Parse list of step definitions"""
        if not isinstance(steps_data, list):
            raise ValueError("Steps must be a list")

        steps = []
        for i, step_data in enumerate(steps_data):
            if not isinstance(step_data, dict):
                raise ValueError(f"Step {i} must be a dictionary")

            # Check if this is a shared step
            if "shared_step" in step_data:
                shared_steps = self._expand_shared_step(step_data)
                steps.extend(shared_steps)

            # FOR loop
            elif "for_each" in step_data:
                loop_steps_data = step_data.get("steps", [])
                steps.append(
                    TestStep(
                        action="for_loop",
                        parameters={},
                        for_each=str(step_data["for_each"]),
                        loop_var=step_data.get("loop_var", "item"),
                        loop_steps=self._parse_steps(loop_steps_data) if loop_steps_data else [],
                        loop_limit=int(step_data.get("limit", 1000)),
                        break_if=step_data.get("break_if"),
                        continue_if=step_data.get("continue_if"),
                    )
                )

            # WHILE loop
            elif "while" in step_data:
                loop_steps_data = step_data.get("steps", [])
                steps.append(
                    TestStep(
                        action="while_loop",
                        parameters={},
                        while_condition=str(step_data["while"]),
                        loop_steps=self._parse_steps(loop_steps_data) if loop_steps_data else [],
                        loop_limit=int(step_data.get("limit", 1000)),
                        break_if=step_data.get("break_if"),
                        continue_if=step_data.get("continue_if"),
                    )
                )

            # TRY/EXCEPT/FINALLY
            elif "try" in step_data:
                try_data = step_data.get("try", [])
                except_data = step_data.get("except", [])
                finally_data = step_data.get("finally", [])
                steps.append(
                    TestStep(
                        action="try_except",
                        parameters={},
                        try_steps=self._parse_steps(try_data) if try_data else [],
                        except_steps=self._parse_steps(except_data) if except_data else None,
                        finally_steps=self._parse_steps(finally_data) if finally_data else None,
                    )
                )

            # IF/ELSE conditional
            elif "condition" in step_data or "if" in step_data:
                condition = step_data.get("condition") or step_data.get("if")
                then_data = step_data.get("then", [])
                else_data = step_data.get("else", [])

                then_steps = self._parse_steps(then_data) if then_data else None
                else_steps = self._parse_steps(else_data) if else_data else None

                steps.append(
                    TestStep(
                        action="conditional",
                        parameters={"expression": condition},
                        condition=condition,
                        then_steps=then_steps,
                        else_steps=else_steps,
                    )
                )
            else:
                # Support both old format (action: "browser.navigate") and new dot notation (browser.navigate: {})
                if "action" in step_data:
                    # Old format
                    action = step_data["action"]
                    retry_config = step_data.get("retry")
                    parameters = {
                        k: v
                        for k, v in step_data.items()
                        if k not in ["action", "condition", "if", "then", "else", "retry"]
                    }
                else:
                    # New dot notation format: browser.navigate: {url: ...}
                    # Find the action key (should be the first key that looks like an action)
                    action = None
                    parameters = {}
                    retry_config = None
                    
                    for key, value in step_data.items():
                        if key not in ["condition", "if", "then", "else", "retry", "description"]:
                            # This is likely the action
                            action = key
                            if isinstance(value, dict):
                                parameters = value.copy()
                            elif value is not None:
                                # If value is not a dict, it might be a single parameter
                                parameters = {"value": value}
                            break

                    if action is None:
                        raise ValueError(f"Step {i} must have an 'action' field or use dot notation (e.g., browser.navigate: {{url: ...}})")

                    # Collect sibling keys as parameters — handles YAML where params are
                    # at the same indent level as the action key instead of nested under it:
                    #   - test.sleep:      ← action value is None
                    #     seconds: 120     ← sibling key, not nested
                    _skip = {action, "condition", "if", "then", "else", "retry", "description"}
                    for key, value in step_data.items():
                        if key not in _skip and key not in parameters:
                            parameters[key] = value

                    # Extract retry if present
                    retry_config = step_data.get("retry")

                # Warn about null parameter values — common cause of runtime
                # failures (e.g. unquoted '#' starts a YAML comment, empty key
                # becomes null, or YAML 'None'/'null' used as a literal value).
                null_params = [k for k, v in parameters.items() if v is None]
                if null_params:
                    import warnings
                    warnings.warn(
                        f"Step '{action}': parameter(s) {null_params} are null/None. "
                        "If this is unintentional, check your YAML: "
                        "unquoted '#' starts a comment (quote the value), "
                        "and an empty 'key:' line becomes null.",
                        stacklevel=2,
                    )

                steps.append(
                    TestStep(
                        action=action, parameters=parameters, retry_config=retry_config
                    )
                )

        return steps

    def _expand_shared_step(
        self,
        step_data: Dict[str, Any],
        _visited: Optional[frozenset] = None,
    ) -> List[TestStep]:
        """Expand a shared step into its constituent steps, recursively.

        Nested shared_step references inside a shared step definition are
        expanded depth-first.  A frozenset of already-expanding names is
        threaded through the recursion so circular references raise a clear
        error rather than causing infinite recursion.
        """
        shared_step_name = step_data["shared_step"]
        step_parameters = step_data.get("parameters", {})

        if shared_step_name not in self.shared_steps:
            raise ValueError(f"Shared step '{shared_step_name}' not found")

        if _visited is None:
            _visited = frozenset()
        if shared_step_name in _visited:
            raise ValueError(
                f"Circular shared step reference detected: '{shared_step_name}' "
                f"is already being expanded (chain: {' -> '.join(sorted(_visited))} -> {shared_step_name})"
            )
        _visited = _visited | {shared_step_name}

        shared_step = self.shared_steps[shared_step_name]
        expanded_steps = []

        for step in shared_step.steps:
            # Nested shared step — recurse
            if step.action == "shared_step" and isinstance(step.parameters, dict) and "shared_step" in step.parameters:
                nested_data = {
                    "shared_step": step.parameters["shared_step"],
                    "parameters": {**step_parameters, **step.parameters.get("parameters", {})},
                }
                expanded_steps.extend(self._expand_shared_step(nested_data, _visited))
            else:
                expanded_steps.append(
                    TestStep(
                        action=step.action,
                        parameters=self._substitute_parameters(
                            step.parameters, step_parameters
                        ),
                    )
                )

        return expanded_steps

    def _substitute_parameters(
        self, original_params: Dict[str, Any], substitutions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Substitute parameters in step parameters"""
        result = {}
        for key, value in original_params.items():
            if isinstance(value, str):
                # Replace parameter placeholders
                for param_name, param_value in substitutions.items():
                    value = value.replace(f"${{{param_name}}}", str(param_value))
            result[key] = value
        return result

    def validate_test_definition(self, test: TestDefinition) -> List[str]:
        """Validate a test definition and return list of errors"""
        errors = []

        # Basic validation
        if not test.name.strip():
            errors.append("Test name cannot be empty")

        if not test.steps:
            errors.append("Test must have at least one step")

        # Validate steps
        for i, step in enumerate(test.steps):
            step_errors = self._validate_step(step, f"Step {i + 1}")
            errors.extend(step_errors)

        # Validate setup steps
        for i, step in enumerate(test.setup):
            step_errors = self._validate_step(step, f"Setup step {i + 1}")
            errors.extend(step_errors)

        # Validate cleanup steps
        for i, step in enumerate(test.cleanup):
            step_errors = self._validate_step(step, f"Cleanup step {i + 1}")
            errors.extend(step_errors)

        return errors

    def _validate_step(self, step: TestStep, step_name: str) -> List[str]:
        """Validate a single step"""
        errors = []

        if not step.action.strip():
            errors.append(f"{step_name}: Action cannot be empty")

        return errors

    def _detect_and_convert_recorder_format(
        self, data: Dict[str, Any], file_path: Path
    ) -> Dict[str, Any]:
        """Detect and convert UI recorder formats to Easy BDD format"""
        from .recorder_converter import RecorderConverter

        converter = RecorderConverter()
        detected_format = converter.detect_format(data)

        if detected_format:
            print(f"Detected {detected_format} recording format in {file_path.name}")
            return converter.convert(data, detected_format, file_path)

        # If no recorder format detected, return data as-is
        return data
