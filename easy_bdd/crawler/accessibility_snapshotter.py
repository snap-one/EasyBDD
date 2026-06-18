"""
Accessibility snapshotter — converts a Playwright page's accessibility tree
into a PageSnapshot that the existing crawler pipeline understands.

Why this is better than DOM scraping for test generation:
  - The accessibility tree is exactly what ARIA-based selectors target
  - Roles and names are already resolved (no guessing from CSS classes)
  - Works correctly with dynamic/SPA content (no timing races with JS)
  - Same data Playwright's own locators use internally

Usage:
    from easy_bdd.crawler.accessibility_snapshotter import snapshot_page_a11y

    # Inside a Playwright sync context:
    page_snapshot = snapshot_page_a11y(page)

    # Or via async:
    page_snapshot = await snapshot_page_a11y_async(page)

The output PageSnapshot plugs directly into analyze_snapshot() / analyze_snapshot_rules().
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    try:
        from playwright.sync_api import Page as SyncPage
        from playwright.async_api import Page as AsyncPage
    except ImportError:
        SyncPage = None
        AsyncPage = None

from .models import ElementSnapshot, PageSnapshot
from .selector_ranker import rank_selectors


# ── Node roles that represent interactive / meaningful elements ───────────────

_INTERACTIVE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "option", "menuitem", "menuitemcheckbox", "menuitemradio",
    "tab", "switch", "searchbox", "spinbutton", "slider",
    "treeitem", "gridcell", "columnheader", "rowheader",
}

_STRUCTURAL_ROLES = {
    "heading", "navigation", "main", "complementary", "contentinfo",
    "banner", "region", "form", "search", "article", "group",
}

_SKIP_ROLES = {
    "none", "presentation", "generic", "document", "application",
    "img", "figure", "separator", "scrollbar",
}


# ── Selector builders from accessibility node properties ──────────────────────

def _build_selectors_from_node(node: Dict[str, Any]) -> List[str]:
    """
    Generate ranked selector candidates from an accessibility tree node.
    These are all stable ARIA/role-based selectors — no fragile CSS.
    """
    selectors: List[str] = []
    role   = node.get("role", "")
    name   = node.get("name", "")
    value  = node.get("value", "")

    # Best: role + accessible name (exact Playwright locator syntax)
    if role and name and role not in _SKIP_ROLES:
        clean_name = name.strip()[:80]
        selectors.append(f'role={role}[name="{_escape(clean_name)}"]')
        # Also emit get_by_role format for documentation clarity
        selectors.append(f'[role="{role}"][aria-label="{_escape(clean_name)}"]')

    # Fallback: visible text for buttons/links
    if role in ("button", "link") and name:
        selectors.append(f'text="{_escape(name.strip()[:60])}"')

    return selectors


def _escape(s: str) -> str:
    return s.replace('"', '\\"')


# ── Node → ElementSnapshot ────────────────────────────────────────────────────

def _node_to_element(
    node: Dict[str, Any],
    in_iframe: bool = False,
    iframe_selector: Optional[str] = None,
) -> Optional[ElementSnapshot]:
    """
    Convert a single accessibility tree node to an ElementSnapshot.
    Returns None for nodes that don't map to meaningful test steps.
    """
    role = node.get("role", "")
    name = (node.get("name") or "").strip()

    if role in _SKIP_ROLES:
        return None
    if not name and role not in _STRUCTURAL_ROLES:
        return None  # nameless non-structural node — skip

    # Map a11y role → HTML tag (approximate, for yaml_writer)
    tag_map = {
        "button": "button", "link": "a", "textbox": "input",
        "searchbox": "input", "checkbox": "input", "radio": "input",
        "combobox": "select", "listbox": "select", "spinbutton": "input",
        "switch": "input", "heading": "h2",
    }
    tag = tag_map.get(role, "div")

    # Input type
    type_map = {
        "textbox": "text", "searchbox": "search",
        "checkbox": "checkbox", "radio": "radio",
        "spinbutton": "number", "switch": "checkbox",
    }
    input_type = type_map.get(role)

    selectors = _build_selectors_from_node(node)

    return ElementSnapshot(
        tag=tag,
        type=input_type,
        role=role,
        name=name if name else None,
        aria_label=name if name else None,
        text=name if role in ("button", "link", "heading") else None,
        value=str(node.get("value", "")) or None,
        selectors=selectors,
        in_iframe=in_iframe,
        iframe_selector=iframe_selector,
    )


# ── Recursive tree walker ─────────────────────────────────────────────────────

def _walk_tree(
    node: Dict[str, Any],
    results: List[ElementSnapshot],
    seen_names: Set[str],
    in_iframe: bool = False,
    iframe_selector: Optional[str] = None,
    depth: int = 0,
    max_depth: int = 20,
) -> None:
    if depth > max_depth:
        return

    el = _node_to_element(node, in_iframe=in_iframe, iframe_selector=iframe_selector)
    if el is not None:
        # Deduplicate by role+name combo
        key = f"{el.role}:{el.name}"
        if key not in seen_names:
            seen_names.add(key)
            results.append(el)

    for child in node.get("children", []):
        _walk_tree(
            child, results, seen_names,
            in_iframe=in_iframe,
            iframe_selector=iframe_selector,
            depth=depth + 1,
        )


# ── Iframe snapshot helper ────────────────────────────────────────────────────

def _snapshot_iframes_sync(page: "SyncPage") -> List[ElementSnapshot]:
    """
    Enumerate same-origin iframes and snapshot their accessibility trees.
    Cross-origin frames raise an exception which we silently skip.
    """
    elements: List[ElementSnapshot] = []

    frames = page.frames
    for frame in frames[1:]:  # skip main frame
        try:
            iframe_url = frame.url
            if not iframe_url or iframe_url == "about:blank":
                continue

            # Generate a selector for this frame
            # Try to find the iframe element in the parent
            frame_selector = f"iframe[src*=\"{_url_path_tail(iframe_url)}\"]"

            tree = frame.accessibility.snapshot(interesting_only=True)
            if not tree:
                continue

            seen: Set[str] = set()
            frame_els: List[ElementSnapshot] = []
            _walk_tree(tree, frame_els, seen, in_iframe=True, iframe_selector=frame_selector)
            elements.extend(frame_els)
        except Exception:
            continue  # cross-origin or unavailable

    return elements


async def _snapshot_iframes_async(page: "AsyncPage") -> List[ElementSnapshot]:
    elements: List[ElementSnapshot] = []
    for frame in page.frames[1:]:
        try:
            iframe_url = frame.url
            if not iframe_url or iframe_url == "about:blank":
                continue
            frame_selector = f"iframe[src*=\"{_url_path_tail(iframe_url)}\"]"
            tree = await frame.accessibility.snapshot(interesting_only=True)
            if not tree:
                continue
            seen: Set[str] = set()
            frame_els: List[ElementSnapshot] = []
            _walk_tree(tree, frame_els, seen, in_iframe=True, iframe_selector=frame_selector)
            elements.extend(frame_els)
        except Exception:
            continue
    return elements


def _url_path_tail(url: str) -> str:
    """Extract the last meaningful path segment from a URL for iframe matching."""
    try:
        from urllib.parse import urlparse
        path = urlparse(url).path
        tail = path.rstrip("/").split("/")[-1]
        return tail if tail else urlparse(url).hostname or "frame"
    except Exception:
        return "frame"


# ── Public API ────────────────────────────────────────────────────────────────

def snapshot_page_a11y(page: "SyncPage", include_html: bool = False) -> PageSnapshot:
    """
    Synchronous version — use inside Playwright sync context.

    Args:
        page: Active Playwright sync Page
        include_html: Whether to also capture page.content() for AI analysis
                      (adds ~100ms; not needed for rule-based mode)

    Returns:
        PageSnapshot populated from the accessibility tree
    """
    url   = page.url
    title = page.title()

    from urllib.parse import urlparse
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path   = parsed.path

    # Main frame accessibility snapshot
    tree = page.accessibility.snapshot(interesting_only=True)
    elements: List[ElementSnapshot] = []
    seen: Set[str] = set()
    if tree:
        _walk_tree(tree, elements, seen)

    # Same-origin iframes
    elements.extend(_snapshot_iframes_sync(page))

    # Iframe origins list
    iframes = list({f.url for f in page.frames[1:] if f.url and f.url != "about:blank"})

    html = page.content()[:150_000] if include_html else None

    return PageSnapshot(
        url=url,
        title=title,
        origin=origin,
        path=path,
        html=html,
        elements=elements,
        iframes=iframes,
        timestamp=time.time(),
    )


async def snapshot_page_a11y_async(page: "AsyncPage", include_html: bool = False) -> PageSnapshot:
    """
    Async version — use inside Playwright async context.
    """
    url   = page.url
    title = await page.title()

    from urllib.parse import urlparse
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path   = parsed.path

    tree = await page.accessibility.snapshot(interesting_only=True)
    elements: List[ElementSnapshot] = []
    seen: Set[str] = set()
    if tree:
        _walk_tree(tree, elements, seen)

    elements.extend(await _snapshot_iframes_async(page))

    iframes = list({f.url for f in page.frames[1:] if f.url and f.url != "about:blank"})

    html = await page.content() if include_html else None
    if html:
        html = html[:150_000]

    return PageSnapshot(
        url=url,
        title=title,
        origin=origin,
        path=path,
        html=html,
        elements=elements,
        iframes=iframes,
        timestamp=time.time(),
    )
