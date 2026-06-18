"""
Selector ranking and stability scoring.

Given a list of raw selector candidates for an element, ranks them by
stability (resistance to DOM refactoring) and returns a prioritised list.

Stability tiers (highest first):
  1. data-testid / data-cy / data-qa attributes
  2. ARIA role + accessible name
  3. Element ID (stable IDs only — rejects generated/hashed ones)
  4. Semantic HTML (label, button text, link text)
  5. CSS class (non-generated)
  6. CSS nth-child / positional XPath  (least stable — last resort)
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .models import ElementSnapshot, RankedSelector


# Patterns that suggest an auto-generated / unstable identifier
_GENERATED_ID_RE = re.compile(
    r"(\b[0-9a-f]{8,}\b|--[0-9]+$|__[0-9]+$|[a-z]+-[0-9]+-[0-9]+)",
    re.I,
)

# Positional / fragile selector patterns
_POSITIONAL_RE = re.compile(r":nth-child|:nth-of-type|:eq\(|\[(\d+)\]")


def _is_stable_id(id_val: str) -> bool:
    """Return True when an element ID looks human-authored and stable."""
    if not id_val:
        return False
    if _GENERATED_ID_RE.search(id_val):
        return False
    if len(id_val) > 60:
        return False
    return True


def _score_selector(selector: str, strategy: str) -> float:
    """Assign a 0-1 stability score."""
    if strategy == "testid":
        return 0.97
    if strategy == "aria":
        return 0.92
    if strategy == "id" and not _GENERATED_ID_RE.search(selector):
        return 0.88
    if strategy == "label":
        return 0.85
    if strategy == "text":
        return 0.75
    if strategy == "css":
        if _POSITIONAL_RE.search(selector):
            return 0.35
        if re.search(r"\.[a-z]+-[a-z]+-[a-z]+", selector, re.I):
            # BEM-style class — fairly stable
            return 0.65
        return 0.55
    if strategy == "xpath":
        if _POSITIONAL_RE.search(selector):
            return 0.30
        return 0.50
    return 0.40


def _infer_strategy(selector: str) -> str:
    """Guess strategy from the selector string."""
    s = selector.strip()
    if s.startswith("//") or s.startswith("(//"):
        return "xpath"
    if re.match(r"^\[data-(testid|cy|qa|test)\]", s, re.I):
        return "testid"
    if re.search(r'\[data-(testid|cy|qa|test)=', s, re.I):
        return "testid"
    if s.startswith("#") and not _GENERATED_ID_RE.search(s[1:]):
        return "id"
    if "aria-label" in s or "role=" in s:
        return "aria"
    return "css"


def rank_selectors(
    element: ElementSnapshot,
    extra_selectors: Optional[List[Tuple[str, str]]] = None,
) -> List[RankedSelector]:
    """
    Build a ranked list of selectors for *element*.

    Args:
        element: the element snapshot
        extra_selectors: additional (selector, strategy) tuples from the AI

    Returns:
        List of RankedSelector sorted by score descending (best first)
    """
    candidates: List[Tuple[str, str, float]] = []

    # ── 1. data-testid (best) ─────────────────────────────────────────────
    if element.data_testid:
        sel = f'[data-testid="{element.data_testid}"]'
        candidates.append((sel, "testid", _score_selector(sel, "testid")))

    # ── 2. ARIA role + name ───────────────────────────────────────────────
    if element.role and element.name:
        sel = f'role={element.role}[name="{element.name}"]'
        candidates.append((sel, "aria", _score_selector(sel, "aria")))

    # ── 3. aria-label ─────────────────────────────────────────────────────
    if element.aria_label:
        sel = f'[aria-label="{element.aria_label}"]'
        candidates.append((sel, "aria", _score_selector(sel, "aria")))

    # ── 4. label / placeholder ────────────────────────────────────────────
    if element.label:
        sel = f'label="{element.label}"'
        candidates.append((sel, "label", _score_selector(sel, "label")))
    if element.placeholder:
        sel = f'[placeholder="{element.placeholder}"]'
        candidates.append((sel, "css", 0.72))

    # ── 5. stable ID ──────────────────────────────────────────────────────
    if element.id and _is_stable_id(element.id):
        sel = f"#{element.id}"
        candidates.append((sel, "id", _score_selector(sel, "id")))

    # ── 6. element text ───────────────────────────────────────────────────
    text = (element.text or "").strip()
    if text and len(text) <= 60:
        sel = f'text="{text}"'
        candidates.append((sel, "text", _score_selector(sel, "text")))

    # ── 7. raw selectors from content script (ranked last unless testid) ──
    for raw_sel in element.selectors:
        strategy = _infer_strategy(raw_sel)
        score = _score_selector(raw_sel, strategy)
        candidates.append((raw_sel, strategy, score))

    # ── 8. extra selectors from AI ────────────────────────────────────────
    if extra_selectors:
        for sel, strat in extra_selectors:
            score = _score_selector(sel, strat)
            candidates.append((sel, strat, score))

    # Deduplicate (keep highest score for each unique selector)
    seen: dict[str, Tuple[str, float]] = {}
    for sel, strat, score in candidates:
        if sel not in seen or seen[sel][1] < score:
            seen[sel] = (strat, score)

    ranked = [
        RankedSelector(
            selector=sel,
            strategy=strat,
            score=score,
            iframe_prefix=f"{element.iframe_selector} >> " if element.in_iframe and element.iframe_selector else None,
        )
        for sel, (strat, score) in seen.items()
    ]
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def best_selector(element: ElementSnapshot) -> str:
    """Return the single best selector string for use in YAML, including iframe prefix."""
    ranked = rank_selectors(element)
    if not ranked:
        return element.tag
    r = ranked[0]
    if r.iframe_prefix:
        return f"{r.iframe_prefix}{r.selector}"
    return r.selector
