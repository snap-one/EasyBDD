/**
 * iframe_handler.js
 *
 * Detects iframes on the page and attempts to extract interactive elements
 * from same-origin frames by injecting a helper into each.
 *
 * Cross-origin iframes are recorded in the iframes list but cannot be
 * introspected due to browser security policies — the test engineer must
 * handle those manually (or use the "iframe >> selector" prefix in Easy BDD).
 *
 * Loaded before crawler.js so the crawler can call window.__easybdd_iframes().
 */

(function () {
  if (window.__easybdd_iframe_handler_loaded) return;
  window.__easybdd_iframe_handler_loaded = true;
  "use strict";

  /**
   * Returns a list of iframe descriptors found on the page.
   * Each descriptor: { selector, origin, sameOrigin, elements[] }
   */
  window.__easybdd_iframes = function detectIframes() {
    const iframes = [];
    const iframeEls = Array.from(document.querySelectorAll("iframe"));

    for (const iframe of iframeEls) {
      const selector = _iframeSelector(iframe);
      let origin = "";
      let sameOrigin = false;
      let elements = [];

      try {
        // This throws if cross-origin
        const iframeDoc =
          iframe.contentDocument || iframe.contentWindow.document;
        origin = iframe.contentWindow.location.origin;
        sameOrigin = origin === window.location.origin;

        if (sameOrigin && iframeDoc) {
          elements = _extractFromDoc(iframeDoc, selector);
        }
      } catch (_) {
        // Cross-origin: record the iframe but leave elements empty
        origin = iframe.src ? new URL(iframe.src).origin : "cross-origin";
        sameOrigin = false;
      }

      iframes.push({ selector, origin, sameOrigin, elements });
    }

    return iframes;
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  function _iframeSelector(iframe) {
    if (iframe.id) return `iframe#${iframe.id}`;
    if (iframe.name) return `iframe[name="${iframe.name}"]`;
    if (iframe.src) {
      try {
        const u = new URL(iframe.src);
        return `iframe[src*="${u.pathname.split("/").pop() || u.hostname}"]`;
      } catch (_) {}
    }
    // Positional fallback
    const siblings = Array.from(
      (iframe.parentElement || document.body).querySelectorAll("iframe")
    );
    const idx = siblings.indexOf(iframe);
    return idx >= 0 ? `iframe:nth-of-type(${idx + 1})` : "iframe";
  }

  const INTERACTIVE_SELECTORS =
    'input:not([type="hidden"]), textarea, select, button, a[href], [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="combobox"], [role="textbox"], [tabindex]:not([tabindex="-1"])';

  function _extractFromDoc(doc, iframeSelector) {
    const elements = [];
    try {
      const els = doc.querySelectorAll(INTERACTIVE_SELECTORS);
      for (const el of els) {
        if (!_isVisible(el)) continue;
        // Use the selector engine if it was injected into the iframe too,
        // otherwise fall back to a basic snapshot
        if (
          el.ownerDocument.defaultView &&
          el.ownerDocument.defaultView.__easybdd_snapshot_element
        ) {
          elements.push(
            el.ownerDocument.defaultView.__easybdd_snapshot_element(
              el,
              true,
              iframeSelector
            )
          );
        } else {
          elements.push(_basicSnapshot(el, iframeSelector));
        }
      }
    } catch (_) {}
    return elements;
  }

  function _isVisible(el) {
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function _basicSnapshot(el, iframeSelector) {
    return {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute("type") || null,
      role: el.getAttribute("role") || null,
      name: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 80),
      label: el.getAttribute("aria-label") || null,
      placeholder: el.getAttribute("placeholder") || null,
      text: (el.textContent || "").trim().slice(0, 80),
      id: el.id || null,
      selectors: el.id ? [`#${el.id}`] : [],
      in_iframe: true,
      iframe_selector: iframeSelector,
    };
  }
})();
