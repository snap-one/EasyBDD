/**
 * selector_engine.js
 *
 * Generates a ranked list of CSS/ARIA selector candidates for a DOM element.
 * Injected into every page (all_frames: false — main frame only).
 * iframe elements are handled separately by iframe_handler.js.
 *
 * Stability tier (index 0 = best):
 *   0. data-testid / data-cy / data-qa
 *   1. ARIA role + accessible name
 *   2. Stable ID (#element-id)
 *   3. Label / placeholder / aria-label
 *   4. Visible text (button/link content)
 *   5. CSS class chain (non-generated)
 *   6. Structural XPath / nth-child (last resort)
 */

(function () {
  "use strict";
  if (window.__easybdd_selector_engine_loaded) return;
  window.__easybdd_selector_engine_loaded = true;

  // ── Helpers ────────────────────────────────────────────────────────────────

  const GENERATED_ID_RE =
    /(\b[0-9a-f]{8,}\b|--\d+$|__\d+$|[a-z]+-\d+-\d+)/i;

  function isStableId(id) {
    if (!id || id.length > 60) return false;
    return !GENERATED_ID_RE.test(id);
  }

  function escapeAttr(val) {
    return val.replace(/"/g, '\\"');
  }

  function getAccessibleName(el) {
    // aria-labelledby → aria-label → label[for] → placeholder → title → text
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const lbEl = document.getElementById(labelledBy);
      if (lbEl) return lbEl.textContent.trim().slice(0, 80);
    }
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim().slice(0, 80);
    if (el.id) {
      const lbl = document.querySelector(`label[for="${el.id}"]`);
      if (lbl) return lbl.textContent.trim().slice(0, 80);
    }
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) return placeholder.trim().slice(0, 80);
    const title = el.getAttribute("title");
    if (title) return title.trim().slice(0, 80);
    const text = (el.textContent || "").trim().slice(0, 80);
    if (text) return text;
    return null;
  }

  function getAriaRole(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    const roleMap = {
      button: "button",
      a: "link",
      select: "combobox",
      textarea: "textbox",
      input: type === "checkbox" ? "checkbox" : type === "radio" ? "radio" : "textbox",
      h1: "heading",
      h2: "heading",
      h3: "heading",
      nav: "navigation",
      main: "main",
      form: "form",
    };
    return roleMap[tag] || null;
  }

  function getNthChildXPath(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === Node.ELEMENT_NODE) {
      let index = 1;
      let sibling = node.previousSibling;
      while (sibling) {
        if (
          sibling.nodeType === Node.ELEMENT_NODE &&
          sibling.tagName === node.tagName
        ) {
          index++;
        }
        sibling = sibling.previousSibling;
      }
      parts.unshift(`${node.tagName.toLowerCase()}[${index}]`);
      node = node.parentNode;
    }
    return "/" + parts.join("/");
  }

  // ── Main export ────────────────────────────────────────────────────────────

  /**
   * Generate a ranked array of selector strings for *el*.
   * @param {Element} el
   * @returns {string[]}
   */
  window.__easybdd_selectors = function generateSelectors(el) {
    const selectors = [];

    // Tier 0 — test attributes
    for (const attr of ["data-testid", "data-cy", "data-qa", "data-test"]) {
      const val = el.getAttribute(attr);
      if (val) {
        selectors.push(`[${attr}="${escapeAttr(val)}"]`);
      }
    }

    // Tier 1 — ARIA role + name
    const role = getAriaRole(el);
    const name = getAccessibleName(el);
    if (role && name) {
      selectors.push(`role=${role}[name="${escapeAttr(name)}"]`);
    }

    // Tier 2 — Stable ID
    const id = el.id;
    if (isStableId(id)) {
      selectors.push(`#${id}`);
    }

    // Tier 3 — aria-label / label
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) {
      selectors.push(`[aria-label="${escapeAttr(ariaLabel)}"]`);
    }
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) {
      selectors.push(`[placeholder="${escapeAttr(placeholder)}"]`);
    }

    // Tier 4 — visible text (links, buttons)
    const tag = el.tagName.toLowerCase();
    if (["button", "a", "label"].includes(tag)) {
      const txt = (el.textContent || "").trim().slice(0, 60);
      if (txt && txt.length > 1) {
        selectors.push(`text="${escapeAttr(txt)}"`);
      }
    }

    // Tier 5 — CSS class chain (non-generated)
    if (el.classList && el.classList.length > 0) {
      const stableClasses = Array.from(el.classList).filter(
        (c) => !GENERATED_ID_RE.test(c) && c.length < 40
      );
      if (stableClasses.length > 0) {
        selectors.push(
          `${tag}.${stableClasses.slice(0, 3).join(".")}`
        );
      }
    }

    // Tier 6 — structural XPath (last resort)
    selectors.push(getNthChildXPath(el));

    return selectors;
  };

  /**
   * Snapshot a single element into a plain object.
   * @param {Element} el
   * @param {boolean} inIframe
   * @param {string|null} iframeSelector
   */
  window.__easybdd_snapshot_element = function snapshotElement(
    el,
    inIframe = false,
    iframeSelector = null
  ) {
    const rect = el.getBoundingClientRect();
    return {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute("type") || null,
      role: getAriaRole(el),
      name: getAccessibleName(el),
      label: el.getAttribute("aria-label") || null,
      placeholder: el.getAttribute("placeholder") || null,
      text: (el.textContent || "").trim().slice(0, 80) || null,
      value: el.value != null ? String(el.value).slice(0, 80) : null,
      href: el.href || null,
      id: el.id || null,
      css_class: el.className || null,
      data_testid:
        el.getAttribute("data-testid") ||
        el.getAttribute("data-cy") ||
        el.getAttribute("data-qa") ||
        null,
      aria_label: el.getAttribute("aria-label") || null,
      options: el.tagName === "SELECT"
        ? Array.from(el.options)
            .slice(0, 10)
            .map(o => ({ value: o.value, text: (o.textContent || "").trim() }))
            .filter(o => o.value !== "" && o.text !== "")
        : null,
      required: el.required || el.getAttribute("aria-required") === "true" || false,
      selectors: window.__easybdd_selectors(el),
      bbox:
        rect.width > 0
          ? {
              x: Math.round(rect.x),
              y: Math.round(rect.y),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
            }
          : null,
      in_iframe: inIframe,
      iframe_selector: iframeSelector,
    };
  };
})();
