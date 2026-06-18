/**
 * background/service_worker.js
 *
 * MV3 service worker — orchestrates the crawl session.
 *
 * State machine:
 *   idle → crawling → done/error
 *
 * Message protocol (popup ↔ service worker):
 *   popup → SW:  { type: "START_CRAWL", config }
 *   popup → SW:  { type: "STOP_CRAWL" }
 *   popup → SW:  { type: "GET_STATUS" }
 *   SW → popup:  { type: "STATUS_UPDATE", status }
 *
 * Content script → SW:
 *   { type: "PAGE_NAVIGATED", url, title }
 *   { type: "CRAWL_RESULT", ... }
 */

// ── State ─────────────────────────────────────────────────────────────────────

const MAX_PAGES = 25;   // stop auto-crawl after this many pages

let _state = {
  crawling: false,
  sessionId: null,
  serverUrl: "http://127.0.0.1:8765",
  config: null,
  pagesVisited: 0,
  casesGenerated: 0,
  errors: [],
  startOrigin: null,
  pendingUrls: [],       // discovered same-origin URLs queued for crawling
  visitedUrls: new Set(),
  totalDiscovered: 0,   // total unique URLs found (for progress display)
  activeCrawlTabId: null,
  lastStatus: null,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function broadcastStatus() {
  chrome.runtime.sendMessage({ type: "STATUS_UPDATE", status: _statusSnapshot() }).catch(() => {});
}

function _statusSnapshot() {
  return {
    crawling: _state.crawling,
    sessionId: _state.sessionId,
    pagesVisited: _state.pagesVisited,
    casesGenerated: _state.casesGenerated,
    errors: _state.errors.slice(-5),
    pendingCount: _state.pendingUrls.length,
    totalDiscovered: _state.totalDiscovered,
    lastStatus: _state.lastStatus,
  };
}

async function _fetchJson(path, method = "GET", body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(`${_state.serverUrl}${path}`, opts);
  if (!resp.ok) throw new Error(`${method} ${path} → ${resp.status}`);
  return resp.json();
}

// ── Content script injection ──────────────────────────────────────────────────

/** URL schemes where content scripts can never run. */
const _SKIP_URL_PREFIXES = [
  "chrome://", "chrome-extension://", "edge://", "about:",
  "data:", "file://", "view-source:",
];

function _isInjectable(url) {
  if (!url) return false;
  return !_SKIP_URL_PREFIXES.some((p) => url.startsWith(p));
}

/**
 * Ensure the Easy BDD content scripts are loaded in the given tab.
 * 1. Tries a quick PING first (cheap, no side effects if already loaded).
 * 2. If the PING fails (content script absent), injects the scripts.
 * 3. If injection also fails (PDF, restricted page, etc.), returns false.
 *
 * Returns true if the tab is ready to receive CRAWL_PAGE, false otherwise.
 */
async function ensureContentScript(tabId) {
  // Quick ping — resolves immediately if already loaded
  try {
    const pong = await chrome.tabs.sendMessage(tabId, { type: "PING" });
    if (pong && pong.type === "PONG") return true;
  } catch (_) {
    // Content script not loaded — fall through to injection
  }

  // Inject the three content scripts in order
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      files: [
        "content/iframe_handler.js",
        "content/selector_engine.js",
        "content/crawler.js",
      ],
    });
    return true;
  } catch (injectErr) {
    // Tab is a PDF, restricted page, or otherwise can't receive scripts
    console.warn(`[EasyBDD] Could not inject into tab ${tabId}: ${injectErr.message}`);
    return false;
  }
}

// ── Crawl orchestration ───────────────────────────────────────────────────────

async function startCrawl(config) {
  _state.crawling = true;
  _state.config = config;
  _state.serverUrl = config.serverUrl || "http://127.0.0.1:8765";
  _state.pagesVisited = 0;
  _state.casesGenerated = 0;
  _state.errors = [];
  _state.pendingUrls = [];
  _state.visitedUrls = new Set();
  _state.totalDiscovered = 0;
  _state.activeCrawlTabId = null;
  _state.lastStatus = null;   // clear previous session's done-state

  try {
    // Check server is alive
    await _fetchJson("/health");

    // Create session on backend
    const sessionResp = await _fetchJson("/crawl/start", "POST", {
      testrail_project_id: config.testrailProjectId,
      testrail_suite_id: config.testrailSuiteId || null,
      testrail_section_name: config.sectionName || "Auto-generated",
      create_test_run: config.createTestRun !== false,
      ai_provider: config.aiProvider || "claude",
      ai_model: config.aiModel || null,
      output_dir: config.outputDir || "tests/cases/crawled",
      base_url: config.baseUrl || "",
    });

    _state.sessionId = sessionResp.session_id;

    // Get the current active tab — this is the starting point
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs.length === 0) throw new Error("No active tab found");

    const startTab = tabs[0];
    _state.startOrigin = new URL(startTab.url).origin;
    _state.activeCrawlTabId = startTab.id;

    // Crawl starting page, collect its links, then auto-crawl the queue
    broadcastStatus();
    await crawlTabAndQueue(startTab.id);
    await processCrawlQueue();

    // Auto-stop: tell the backend to finalise the session once queue is drained
    await stopCrawl();

  } catch (err) {
    _state.errors.push(`Start failed: ${err.message}`);
    _state.crawling = false;
    broadcastStatus();
  }
}

/**
 * Crawl one tab: snapshot it, count cases, and add any newly discovered
 * same-origin links to the pending queue.
 */
async function crawlTabAndQueue(tabId) {
  if (!_state.crawling) return;

  let tab;
  try {
    tab = await chrome.tabs.get(tabId);
  } catch (_) {
    return; // tab closed
  }
  if (!_isInjectable(tab.url)) return;

  // Mark URL visited before crawling to prevent race re-entry
  const normalUrl = tab.url.split("#")[0];
  if (_state.visitedUrls.has(normalUrl)) return;
  _state.visitedUrls.add(normalUrl);

  const ready = await ensureContentScript(tabId);
  if (!ready) return;

  try {
    const result = await chrome.tabs.sendMessage(tabId, {
      type: "CRAWL_PAGE",
      sessionId: _state.sessionId,
      serverUrl: _state.serverUrl,
    });

    if (result) {
      _state.pagesVisited++;
      _state.casesGenerated += result.casesGenerated || 0;

      if (!result.success && result.error) {
        _state.errors.push(`${result.url}: ${result.error}`);
      }

      // Queue newly discovered same-origin links
      const links = result.discoveredLinks || [];
      for (const link of links) {
        const clean = link.split("#")[0];
        if (
          !_state.visitedUrls.has(clean) &&
          !_state.pendingUrls.includes(clean) &&
          _state.pagesVisited + _state.pendingUrls.length < MAX_PAGES
        ) {
          _state.pendingUrls.push(clean);
          _state.totalDiscovered++;
        }
      }
    }
  } catch (err) {
    _state.errors.push(`Tab crawl error: ${err.message}`);
  }

  broadcastStatus();
}

/**
 * Wait for a tab to finish loading (status === "complete").
 * Times out after 20 seconds to avoid hanging on slow pages.
 */
function waitForTabLoad(tabId) {
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve(); // proceed anyway after timeout
    }, 20_000);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === "complete") {
        clearTimeout(timeout);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

/**
 * Drain the pendingUrls queue: navigate → wait → crawl, until empty or stopped.
 */
async function processCrawlQueue() {
  while (_state.crawling && _state.pendingUrls.length > 0) {
    if (_state.pagesVisited >= MAX_PAGES) {
      console.log(`[EasyBDD] Reached ${MAX_PAGES}-page limit — stopping auto-crawl.`);
      break;
    }

    const nextUrl = _state.pendingUrls.shift();
    const clean = nextUrl.split("#")[0];

    // Double-check it wasn't visited while we were processing another page
    if (_state.visitedUrls.has(clean)) continue;

    const tabId = _state.activeCrawlTabId;
    if (!tabId) break;

    try {
      // Navigate the crawl tab to the next URL
      await chrome.tabs.update(tabId, { url: nextUrl });
      // Wait for the page to finish loading
      await waitForTabLoad(tabId);
      // Extra settle time for SPAs / lazy-loaded content
      await new Promise((r) => setTimeout(r, 1200));
      // Crawl it and collect new links
      await crawlTabAndQueue(tabId);
    } catch (err) {
      _state.errors.push(`Auto-crawl ${nextUrl}: ${err.message}`);
      broadcastStatus();
    }
  }
}

async function stopCrawl() {
  if (!_state.crawling || !_state.sessionId) {
    _state.crawling = false;
    broadcastStatus();
    return;
  }

  try {
    const status = await _fetchJson(
      `/crawl/stop?session_id=${encodeURIComponent(_state.sessionId)}`,
      "POST"
    );
    _state.lastStatus = status;
    console.log("[EasyBDD] Crawl stopped. TestRail run:", status.test_run_url || "none");
  } catch (err) {
    _state.errors.push(`Stop failed: ${err.message}`);
  }

  _state.crawling = false;
  broadcastStatus();
}

// ── SPA navigation handler (pushState / replaceState from content script) ─────
// Only used for in-page SPA navigation that happens BETWEEN queue entries
// (i.e. the page navigates itself during the settle wait). The queue processor
// handles hard navigations; this handles soft ones.

async function handleNavigation(tabId, url) {
  if (!_state.crawling || !_state.sessionId) return;
  // Only the active crawl tab (or, before auto-crawl starts, any tab)
  if (_state.activeCrawlTabId && tabId !== _state.activeCrawlTabId) return;

  try {
    if (new URL(url).origin !== _state.startOrigin) return;
  } catch (_) {
    return;
  }

  const clean = url.split("#")[0];
  if (_state.visitedUrls.has(clean)) return;

  // Don't add to queue — just crawl immediately; the queue processor is idle
  // during the settle delay that lets SPAs finish rendering
  await new Promise((r) => setTimeout(r, 800));
  await crawlTabAndQueue(tabId);
}

// ── Message handler ───────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "START_CRAWL":
      startCrawl(message.config).then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;

    case "STOP_CRAWL":
      stopCrawl().then(() => sendResponse({ ok: true })).catch((e) => sendResponse({ ok: false, error: e.message }));
      return true;

    case "GET_STATUS":
      sendResponse(_statusSnapshot());
      return false;

    case "PAGE_NAVIGATED":
      if (sender.tab) {
        handleNavigation(sender.tab.id, message.url);
      }
      return false;

    case "CRAWL_RESULT":
      // Already handled inline in crawlTab; this is a no-op safety catch
      return false;
  }
});

// NOTE: hard navigation tracking is handled by processCrawlQueue (which navigates
// the tab itself and waits via waitForTabLoad). We do NOT add a global
// chrome.tabs.onUpdated listener here because it would double-crawl every URL
// that the queue processor navigates to.
