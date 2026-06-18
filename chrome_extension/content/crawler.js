/**
 * crawler.js
 *
 * Main content script — crawls the current page and POSTs a PageSnapshot
 * to the local Easy BDD Crawler backend (default http://127.0.0.1:8765).
 *
 * Triggered by a message from the background service worker:
 *   { type: "CRAWL_PAGE", sessionId, serverUrl }
 *
 * Responds with:
 *   { type: "CRAWL_RESULT", success, url, casesGenerated, error }
 */

(function () {
  "use strict";

  // Guard: prevent double-registration if the script is injected more than once
  // (can happen when the service worker injects programmatically into an already-loaded tab)
  if (window.__easybdd_crawler_loaded) return;
  window.__easybdd_crawler_loaded = true;

  const INTERACTIVE_SELECTORS = [
    'input:not([type="hidden"])',
    "textarea",
    "select",
    "button",
    "a[href]",
    '[role="button"]',
    '[role="link"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="combobox"]',
    '[role="textbox"]',
    '[role="menuitem"]',
    '[role="tab"]',
    '[role="option"]',
    'label',
    'h1, h2, h3',    // headings help the AI understand page structure
  ].join(", ");

  const MAX_HTML_CHARS = 150_000;

  // ── Visibility check ───────────────────────────────────────────────────────

  function isVisible(el) {
    if (!el.isConnected) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || style.opacity === "0")
      return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  // ── Snapshot current page ─────────────────────────────────────────────────

  function snapshotPage() {
    // Collect visible interactive elements
    const domElements = Array.from(document.querySelectorAll(INTERACTIVE_SELECTORS))
      .filter(isVisible)
      .slice(0, 300); // cap for very large pages

    const elements = domElements.map((el) => {
      if (window.__easybdd_snapshot_element) {
        return window.__easybdd_snapshot_element(el, false, null);
      }
      // Fallback if selector_engine.js hasn't loaded yet
      return {
        tag: el.tagName.toLowerCase(),
        type: el.getAttribute("type") || null,
        text: (el.textContent || "").trim().slice(0, 80),
        id: el.id || null,
        selectors: el.id ? [`#${el.id}`] : [],
        in_iframe: false,
      };
    });

    // Add iframe elements
    if (window.__easybdd_iframes) {
      const iframeData = window.__easybdd_iframes();
      for (const frame of iframeData) {
        elements.push(...frame.elements);
      }
    }

    // Collect iframe origins
    const iframes = Array.from(document.querySelectorAll("iframe")).map((f) => {
      try { return f.contentWindow.location.origin; } catch (_) { return f.src || "cross-origin"; }
    });

    const html = document.documentElement.outerHTML.slice(0, MAX_HTML_CHARS);

    return {
      url: window.location.href,
      title: document.title,
      origin: window.location.origin,
      path: window.location.pathname,
      html,
      elements,
      iframes: [...new Set(iframes)],
      timestamp: Date.now() / 1000,
    };
  }

  // ── Discover same-origin links ────────────────────────────────────────────

  function discoverLinks(origin) {
    const links = new Set();
    document.querySelectorAll("a[href]").forEach((a) => {
      try {
        const url = new URL(a.href, window.location.href);
        // Same origin, not a fragment-only jump, not a download
        if (
          url.origin === origin &&
          url.pathname !== window.location.pathname ||
          (url.origin === origin && url.search !== window.location.search)
        ) {
          // Normalize: strip fragment, keep path+query
          const clean = url.origin + url.pathname + url.search;
          // Skip obvious non-page links
          const skip = /\.(pdf|zip|png|jpg|jpeg|gif|svg|ico|css|js|woff2?|ttf|eot|mp4|mp3)(\?|$)/i;
          if (!skip.test(url.pathname)) {
            links.add(clean);
          }
        }
      } catch (_) {}
    });
    return Array.from(links).slice(0, 60); // cap at 60 links per page
  }

  // ── POST to backend ────────────────────────────────────────────────────────

  async function sendSnapshot(serverUrl, sessionId, snapshot) {
    const url = `${serverUrl}/crawl/snapshot?session_id=${encodeURIComponent(sessionId)}`;
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshot),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Server error ${resp.status}: ${text}`);
    }
    return await resp.json();
  }

  // ── Message listener ───────────────────────────────────────────────────────

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    // PING — lets the service worker check if we're loaded before injecting
    if (message.type === "PING") {
      sendResponse({ type: "PONG" });
      return false;
    }

    if (message.type !== "CRAWL_PAGE") return false;

    const { sessionId, serverUrl = "http://127.0.0.1:8765" } = message;

    (async () => {
      try {
        const snapshot = snapshotPage();
        const discoveredLinks = discoverLinks(snapshot.origin);
        const result = await sendSnapshot(serverUrl, sessionId, snapshot);
        sendResponse({
          type: "CRAWL_RESULT",
          success: true,
          url: snapshot.url,
          casesGenerated: result.cases ? result.cases.length : 0,
          discoveredLinks,
          sessionId,
        });
      } catch (err) {
        sendResponse({
          type: "CRAWL_RESULT",
          success: false,
          url: window.location.href,
          casesGenerated: 0,
          error: err.message,
          sessionId,
        });
      }
    })();

    return true; // keep sendResponse channel open for async
  });

  // ── Auto-notify background of navigation ──────────────────────────────────
  // Fires when the SPA navigates (pushState / replaceState / hashchange)

  let _lastUrl = location.href;

  function notifyNavigation() {
    if (location.href !== _lastUrl) {
      _lastUrl = location.href;
      chrome.runtime.sendMessage({
        type: "PAGE_NAVIGATED",
        url: location.href,
        title: document.title,
      });
    }
  }

  const _origPush = history.pushState.bind(history);
  history.pushState = function (...args) {
    _origPush(...args);
    notifyNavigation();
  };
  const _origReplace = history.replaceState.bind(history);
  history.replaceState = function (...args) {
    _origReplace(...args);
    notifyNavigation();
  };
  window.addEventListener("popstate", notifyNavigation);
  window.addEventListener("hashchange", notifyNavigation);
})();
