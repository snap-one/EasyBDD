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


# Max characters of HTML to send to the AI (keep context manageable)
_MAX_HTML_CHARS = 40_000


def _slim_snapshot(snapshot: PageSnapshot) -> Dict[str, Any]:
    """Return a trimmed dict representation safe to serialise for the AI."""
    elements = []
    for el in snapshot.elements:
        e: Dict[str, Any] = {
            "tag": el.tag,
            "selectors": el.selectors[:6],
        }
        for field in ("type", "role", "name", "label", "placeholder", "text",
                      "id", "aria_label", "data_testid", "in_iframe", "iframe_selector"):
            v = getattr(el, field, None)
            if v:
                e[field] = v
        elements.append(e)

    html_snippet = (snapshot.html or "")[:_MAX_HTML_CHARS]

    return {
        "url": snapshot.url,
        "title": snapshot.title,
        "elements": elements,
        "html_snippet": html_snippet,
        "iframes": snapshot.iframes,
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
    # ── Rule-based path (no AI, no API key) ───────────────────────────────────
    from .ai_client import RuleBasedClient
    if isinstance(ai_client, RuleBasedClient):
        from .rule_based_analyzer import analyze_snapshot_rules
        return analyze_snapshot_rules(snapshot)

    # ── AI path (Claude or Ollama) ────────────────────────────────────────────
    slim = _slim_snapshot(snapshot)
    snapshot_json = json.dumps(slim, indent=2)

    raw_cases = ai_client.analyze_page(snapshot_json, existing_context=existing_context)

    if not raw_cases:
        return []

    element_index = _build_element_index(snapshot)
    cases: List[GeneratedTestCase] = []

    for raw in raw_cases:
        if not isinstance(raw, dict):
            continue

        name = raw.get("name", "Unnamed test")
        description = raw.get("description", "")
        tags = raw.get("tags", ["browser", "crawled"])
        raw_steps = raw.get("steps", [])

        steps = [_enrich_step(s, element_index) for s in raw_steps if isinstance(s, dict)]

        cases.append(
            GeneratedTestCase(
                name=name,
                description=description,
                tags=tags,
                url=snapshot.url,
                steps=steps,
            )
        )

    return cases
