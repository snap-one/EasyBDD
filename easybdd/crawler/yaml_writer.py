"""
YAML writer — serialises GeneratedTestCase objects to Easy BDD YAML files.

Output format matches the existing Easy BDD dot-notation style:

  name: Login test
  description: ...
  tags: [browser, crawled]
  variables:
    base_url: ${BASE_URL}
  steps:
    - browser.open:
        url: ${base_url}
    - browser.fill:
        selector: "#email"
        value: ${username}
    - browser.click:
        role: button
        name: Sign In
    - browser.screenshot:
        name: after-login

Selector fallback comments are embedded as YAML comments for human review.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .models import GeneratedStep, GeneratedTestCase


# ── YAML helpers ──────────────────────────────────────────────────────────────


class _LiteralStr(str):
    """Marker class: render as YAML literal block scalar (|)."""


def _literal_representer(dumper: yaml.Dumper, data: _LiteralStr) -> yaml.ScalarNode:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


def _str_representer(dumper: yaml.Dumper, data: str) -> yaml.ScalarNode:
    """Keep strings without unnecessary quotes unless they need it."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_yaml_dumper = yaml.Dumper
_yaml_dumper.add_representer(_LiteralStr, _literal_representer)
_yaml_dumper.add_representer(str, _str_representer)


def _safe_filename(name: str) -> str:
    """Convert a test name to a safe snake_case filename."""
    name = name.lower()
    name = re.sub(r"[^a-z0-9_\s-]", "", name)
    name = re.sub(r"[\s-]+", "_", name).strip("_")
    return name[:60] or "test"


def _step_to_dict(step: GeneratedStep) -> Dict[str, Any]:
    """
    Convert a GeneratedStep to the Easy BDD dot-notation dict.

    e.g.  browser.fill → {"browser.fill": {"selector": "#email", "value": "${username}"}}

    When the step has ranked selector fallbacks, they are appended as
    `fallback_selectors` so the runner can cycle through them automatically.
    """
    params = {k: v for k, v in step.params.items() if v not in (None, "")}

    # Inject fallback selectors (ranked 2nd onward) when available
    if step.selectors and len(step.selectors) > 1 and "selector" in params:
        fallbacks = []
        for r in step.selectors[1:6]:   # up to 5 fallbacks
            sel = f"{r.iframe_prefix}{r.selector}" if r.iframe_prefix else r.selector
            if sel != params["selector"]:  # skip if identical to primary
                fallbacks.append(sel)
        if fallbacks:
            params["fallback_selectors"] = fallbacks

    if not params:
        return {step.action: None}

    return {step.action: params}


def _build_yaml_doc(case: GeneratedTestCase, base_url: str = "") -> Dict[str, Any]:
    """Build the full YAML document dict for a test case."""
    doc: Dict[str, Any] = {
        "name": case.name,
        "description": case.description,
        "tags": case.tags,
    }

    # Standard variables block
    variables: Dict[str, Any] = {}
    if base_url:
        variables["base_url"] = base_url
    # Store the specific crawled page URL so the test runner and locator
    # debugger can navigate directly to the right page rather than root.
    if case.url:
        variables["page_url"] = case.url
    variables["username"] = "${USERNAME}"
    variables["password"] = "${PASSWORD}"
    doc["variables"] = variables

    # Steps
    doc["steps"] = [_step_to_dict(s) for s in case.steps]

    return doc


# ── Public API ────────────────────────────────────────────────────────────────


def write_test_case(
    case: GeneratedTestCase,
    output_dir: str | Path,
    base_url: str = "",
) -> Path:
    """
    Write a GeneratedTestCase to disk as an Easy BDD YAML file.

    Returns the path of the written file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = _safe_filename(case.name) + ".yaml"
    output_path = output_dir / filename

    # Avoid clobbering — append index suffix if file already exists
    counter = 1
    while output_path.exists():
        output_path = output_dir / f"{_safe_filename(case.name)}_{counter}.yaml"
        counter += 1

    doc = _build_yaml_doc(case, base_url=base_url)

    # Build YAML string with inline fallback comments
    yaml_lines = yaml.dump(
        doc,
        Dumper=_yaml_dumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).splitlines()

    # Inject selector fallback comments
    annotated_lines = _inject_fallback_comments(yaml_lines, case)

    output_path.write_text("\n".join(annotated_lines) + "\n", encoding="utf-8")
    case.yaml_path = str(output_path)
    return output_path


def _inject_fallback_comments(
    lines: List[str], case: GeneratedTestCase
) -> List[str]:
    """
    For each step that has ranked selectors, append a YAML comment listing
    the fallback options so test engineers can pick a better one if needed.
    """
    step_selector_map: Dict[str, List[str]] = {}
    for step in case.steps:
        if len(step.selectors) > 1:
            primary = step.selectors[0].selector
            fallbacks = [
                f"{r.strategy}:{r.selector} (score={r.score:.2f})"
                for r in step.selectors[1:4]
            ]
            if fallbacks:
                step_selector_map[primary] = fallbacks

    if not step_selector_map:
        return lines

    result: List[str] = []
    for line in lines:
        result.append(line)
        for primary_sel, fallbacks in step_selector_map.items():
            if primary_sel in line:
                indent = " " * (len(line) - len(line.lstrip()) + 2)
                result.append(
                    f"{indent}# Fallback selectors: {' | '.join(fallbacks)}"
                )
                break
    return result


def write_all_cases(
    cases: List[GeneratedTestCase],
    output_dir: str | Path,
    base_url: str = "",
) -> List[Path]:
    """Write a list of test cases; return list of written paths."""
    paths: List[Path] = []
    for case in cases:
        p = write_test_case(case, output_dir, base_url=base_url)
        paths.append(p)
    return paths
