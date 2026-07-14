"""
Self-healing selector engine.

When a browser step fails because a selector no longer matches, this module
attempts to recover using three strategies in order:

  1. Fallback selector chain  — try the ranked alternative selectors stored
     in the test case metadata (fastest; no external calls)

  2. AI re-locate             — send a description of the element + the
     current page HTML to the AI client and ask for a new selector

  3. Visual similarity        — compare the element's stored bounding box
     against currently visible elements at a similar position on the page
     (requires an active Playwright page object)

Usage from browser_service.py:
    from easybdd.crawler.self_healer import SelfHealer

    healer = SelfHealer(ai_client=build_ai_client())
    new_selector = healer.heal(
        broken_selector="##old-id",
        element_description="Submit button for the login form",
        page_html=page.content(),
        page=page,               # Playwright page (optional, for visual check)
        ranked_selectors=[...],  # from test metadata
    )
    if new_selector:
        # retry the action with new_selector
"""

from __future__ import annotations

import re
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

from .models import RankedSelector
from .ai_client import AIClient


class SelfHealer:
    """
    Three-layer self-healing:
      1. fallback selector chain
      2. AI re-locate
      3. visual similarity (bbox proximity)
    """

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        visual_tolerance_px: float = 80.0,
    ):
        self.ai_client = ai_client
        self.visual_tolerance_px = visual_tolerance_px

    # ── Public ────────────────────────────────────────────────────────────────

    def heal(
        self,
        broken_selector: str,
        element_description: str = "",
        page_html: str = "",
        page: Optional["Page"] = None,
        ranked_selectors: Optional[List[RankedSelector]] = None,
        stored_bbox: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Attempt to find a working replacement for *broken_selector*.

        Returns the first working selector, or None if all strategies fail.
        """

        # ── Strategy 1: fallback chain ────────────────────────────────────
        if ranked_selectors:
            healed = self._try_fallback_chain(ranked_selectors, broken_selector, page)
            if healed:
                print(f"  [HEAL-1] Fallback chain found: {healed!r}")
                return healed

        # ── Strategy 2: AI re-locate ──────────────────────────────────────
        if self.ai_client and (element_description or page_html):
            healed = self._try_ai_relocate(
                broken_selector, element_description, page_html, page
            )
            if healed:
                print(f"  [HEAL-2] AI suggested: {healed!r}")
                return healed

        # ── Strategy 3: visual similarity ─────────────────────────────────
        if page and stored_bbox:
            healed = self._try_visual_similarity(stored_bbox, page)
            if healed:
                print(f"  [HEAL-3] Visual match at bbox: {healed!r}")
                return healed

        print(f"  [HEAL] All strategies exhausted for {broken_selector!r}.")
        return None

    # ── Strategy implementations ──────────────────────────────────────────────

    def _try_fallback_chain(
        self,
        ranked: List[RankedSelector],
        broken: str,
        page: Optional["Page"],
    ) -> Optional[str]:
        """Try each ranked selector in order (skip the broken one)."""
        for rs in ranked:
            sel = f"{rs.iframe_prefix}{rs.selector}" if rs.iframe_prefix else rs.selector
            if sel == broken:
                continue
            if page is None:
                # No live page — return next best without verification
                return sel
            try:
                count = page.locator(sel).count()
                if count > 0:
                    return sel
            except Exception:
                continue
        return None

    def _try_ai_relocate(
        self,
        broken_selector: str,
        element_description: str,
        page_html: str,
        page: Optional["Page"],
    ) -> Optional[str]:
        """Ask the AI for alternative selectors, then verify against live page."""
        if not self.ai_client:
            return None
        try:
            html_frag = self._extract_html_context(broken_selector, page_html)
            suggestions = self.ai_client.suggest_selectors(
                element_description or f"Element with selector {broken_selector!r}",
                html_frag,
            )
        except Exception as e:
            print(f"  [HEAL-2] AI call failed: {e}")
            return None

        for sel in suggestions:
            if not sel or sel == broken_selector:
                continue
            if page is None:
                return sel
            try:
                if page.locator(sel).count() > 0:
                    return sel
            except Exception:
                continue
        return None

    def _try_visual_similarity(
        self,
        stored_bbox: dict,
        page: "Page",
    ) -> Optional[str]:
        """
        Find an interactive element whose bounding box is closest to the
        stored one. Returns an XPath-based locator as a last resort.

        stored_bbox: {"x": float, "y": float, "width": float, "height": float}
        """
        sx = stored_bbox.get("x", 0)
        sy = stored_bbox.get("y", 0)
        sw = stored_bbox.get("width", 0)
        sh = stored_bbox.get("height", 0)
        # centre point of stored element
        cx, cy = sx + sw / 2, sy + sh / 2

        try:
            # Query all interactive elements visible on the page
            js = """
            () => {
                const tags = ['button', 'a', 'input', 'select', 'textarea', '[role]'];
                const els = [];
                tags.forEach(tag => {
                    document.querySelectorAll(tag).forEach(el => {
                        const r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {
                            els.push({
                                tag: el.tagName.toLowerCase(),
                                id: el.id || '',
                                text: (el.innerText || el.value || el.placeholder || '').trim().slice(0, 60),
                                x: r.x, y: r.y, w: r.width, h: r.height
                            });
                        }
                    });
                });
                return els;
            }
            """
            elements = page.evaluate(js)
        except Exception:
            return None

        best_dist = self.visual_tolerance_px
        best_sel: Optional[str] = None

        for el in elements:
            ex = el["x"] + el["w"] / 2
            ey = el["y"] + el["h"] / 2
            dist = ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                # Build a best-effort selector
                if el.get("id") and not re.search(r"[0-9a-f]{8,}", el["id"], re.I):
                    best_sel = f"#{el['id']}"
                elif el.get("text"):
                    best_sel = f'text="{el["text"]}"'
                else:
                    best_sel = el["tag"]

        return best_sel

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_html_context(selector: str, full_html: str, context_chars: int = 3000) -> str:
        """Extract a snippet of HTML around the broken selector's ID/class hint."""
        if not full_html:
            return ""
        # Try to find the element's ID or first class from the selector
        match = re.search(r"#([\w-]+)|\.first:([\w-]+)|\.([\w-]+)", selector)
        hint = (match.group(1) or match.group(2) or match.group(3)) if match else None
        if hint and hint in full_html:
            idx = full_html.index(hint)
            start = max(0, idx - 500)
            end = min(len(full_html), idx + context_chars)
            return full_html[start:end]
        # Fallback: return the beginning of the HTML
        return full_html[:context_chars]
