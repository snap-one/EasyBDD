"""
Page analyser — converts raw PageSnapshot + AI output into GeneratedTestCase objects.

Responsibilities:
  1. Trim the snapshot to fit AI context limits
  2. Call the AI client
  3. Map AI-generated steps → GeneratedStep with ranked selectors
  4. Return a list of GeneratedTestCase objects ready for YAML writing
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from .ai_client import AIClient
from .models import (
    ElementSnapshot,
    GeneratedStep,
    GeneratedTestCase,
    PageSnapshot,
    RankedSelector,
)
from .selector_ranker import rank_selectors, best_selector


# Tags that represent interactive elements worth testing
_INTERACTIVE_TAGS = {"input", "button", "select", "textarea", "a", "form"}
_INTERACTIVE_ROLES = {"button", "link", "textbox", "combobox", "checkbox",
                      "radio", "switch", "menuitem", "tab", "searchbox"}
_SKIP_INPUT_TYPES = {"hidden", "submit", "reset", "image"}


def _slim_snapshot(snapshot: PageSnapshot) -> Dict[str, Any]:
    """
    Return a compact dict of ONLY interactive elements for the AI.
    Skips raw HTML entirely — the element list is all the AI needs.
    """
    elements = []
    for el in snapshot.elements:
        # Skip non-interactive elements
        tag = (el.tag or "").lower()
        role = (getattr(el, "role", "") or "").lower()
        input_type = (getattr(el, "type", "") or "").lower()

        is_interactive = (
            tag in _INTERACTIVE_TAGS
            or role in _INTERACTIVE_ROLES
        )
        if not is_interactive:
            continue
        if tag == "input" and input_type in _SKIP_INPUT_TYPES:
            continue

        e: Dict[str, Any] = {"tag": tag}
        for field in ("type", "role", "name", "label", "placeholder", "text",
                      "id", "aria_label", "data_testid", "in_iframe", "iframe_selector"):
            v = getattr(el, field, None)
            if v:
                e[field] = v
        # Include best 3 selectors only
        e["selectors"] = el.selectors[:3]
        elements.append(e)

    return {
        "url":      snapshot.url,
        "title":    snapshot.title,
        "elements": elements,
        "iframes":  snapshot.iframes,
    }


def _build_element_index(snapshot: PageSnapshot) -> Dict[str, ElementSnapshot]:
    """Index elements by their best selector for fast lookup during step enrichment."""
    index: Dict[str, ElementSnapshot] = {}
    for el in snapshot.elements:
        key = best_selector(el)
        index[key] = el
        # Also index by raw selectors from the content script
        for raw_sel in el.selectors:
            if raw_sel not in index:
                index[raw_sel] = el
    return index


def _enrich_step(
    step_dict: Dict[str, Any],
    element_index: Dict[str, ElementSnapshot],
) -> GeneratedStep:
    """
    Convert an AI-produced step dict → GeneratedStep with ranked selectors.

    The AI may use selector keys like 'selector', 'label', 'role'+'name'.
    We look up the matching element and attach the ranked selector list.
    """
    action = step_dict.get("action", "")
    params: Dict[str, Any] = dict(step_dict.get("params", {}))
    description = step_dict.get("description")

    ranked: List[RankedSelector] = []

    # Try to find the element in our index
    raw_sel = (
        params.get("selector")
        or params.get("label")
        or params.get("name")
    )
    if raw_sel and raw_sel in element_index:
        el = element_index[raw_sel]
        ranked = rank_selectors(el)
        # Use the best selector in the step params
        if ranked:
            best = ranked[0]
            if best.iframe_prefix:
                params["selector"] = f"{best.iframe_prefix}{best.selector}"
            elif best.strategy == "aria" and el.role:
                params.pop("selector", None)
                params["role"] = el.role
                params["name"] = el.name or best.selector
            elif best.strategy in ("label",):
                params["selector"] = best.selector
            else:
                params["selector"] = best.selector

    return GeneratedStep(
        action=action,
        params=params,
        description=description,
        selectors=ranked,
    )


def analyze_snapshot(
    snapshot: PageSnapshot,
    ai_client: AIClient,
    existing_context: Optional[str] = None,
) -> List[GeneratedTestCase]:
    """
    Main entry point: analyse a page snapshot and return generated test cases.

    Args:
        snapshot: The page snapshot from the Chrome extension
        ai_client: Configured AI client (Claude, Ollama, or RuleBasedClient)
        existing_context: JSON string of previously generated cases (for deduplication)

    Returns:
        List of GeneratedTestCase objects
    """
    from .ai_client import RuleBasedClient, HybridClient

    # ── Rule-based path ────────────────────────────────────────────────────────
    if isinstance(ai_client, RuleBasedClient):
        from .rule_based_analyzer import analyze_snapshot_rules
        return analyze_snapshot_rules(snapshot)

    # ── Hybrid path: rules first, Ollama adds workflow tests on top ────────────
    if isinstance(ai_client, HybridClient):
        from .rule_based_analyzer import analyze_snapshot_rules
        rule_cases = analyze_snapshot_rules(snapshot)

        # Build known selectors set for hallucination filtering
        element_index = _build_element_index(snapshot)
        known_selectors = set(element_index.keys())

        # Slim snapshot for Ollama (interactive elements only, no HTML)
        slim = _slim_snapshot(snapshot)
        snapshot_json = json.dumps(slim, indent=2)

        # Serialize rule cases as few-shot examples for Ollama
        rule_cases_json = json.dumps([
            {
                "name": c.name,
                "steps": [{"action": s.action, "params": s.params} for s in c.steps],
            }
            for c in rule_cases[:5]  # first 5 as examples
        ], indent=2)

        workflow_raw = ai_client.analyze_workflows(
            snapshot_json, rule_cases_json, known_selectors
        )

        # Convert workflow cases to GeneratedTestCase objects
        workflow_cases = _raw_to_cases(workflow_raw, element_index, snapshot.url, ["browser", "workflow"])

        return rule_cases + workflow_cases

    # ── Pure AI path (Claude or Ollama standalone) ────────────────────────────
    slim = _slim_snapshot(snapshot)
    snapshot_json = json.dumps(slim, indent=2)

    raw_cases = ai_client.analyze_page(snapshot_json, existing_context=existing_context)

    if not raw_cases:
        return []

    element_index = _build_element_index(snapshot)
    return _raw_to_cases(raw_cases, element_index, snapshot.url, ["browser", "crawled"])


def _raw_to_cases(
    raw_cases: List[Dict[str, Any]],
    element_index: Dict[str, Any],
    url: str,
    default_tags: List[str],
) -> List[GeneratedTestCase]:
    """Convert a list of raw AI dicts → GeneratedTestCase objects."""
    cases: List[GeneratedTestCase] = []
    for raw in raw_cases:
        if not isinstance(raw, dict):
            continue
        name = (raw.get("name") or "").strip()
        if not name or name.lower() in ("unnamed test", "untitled"):
            continue
        steps = [
            _enrich_step(s, element_index)
            for s in raw.get("steps", [])
            if isinstance(s, dict)
        ]
        cases.append(GeneratedTestCase(
            name=name,
            description=raw.get("description", ""),
            tags=raw.get("tags", default_tags),
            url=url,
            steps=steps,
        ))
    return cases
