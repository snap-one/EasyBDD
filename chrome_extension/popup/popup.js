/**
 * popup.js — Easy BDD Crawler popup controller
 *
 * Responsibilities:
 *  1. On open: ping the backend, load config (TestRail projects, AI provider)
 *  2. Render project/suite dropdowns
 *  3. Start / stop crawl via the background service worker
 *  4. Poll for status updates
 */

"use strict";

// ── DOM refs ──────────────────────────────────────────────────────────────────
const $serverStatus   = document.getElementById("server-status");
const $serverError    = document.getElementById("server-error");
const $configSection  = document.getElementById("config-section");
const $statusSection  = document.getElementById("status-section");
const $doneSection    = document.getElementById("done-section");
const $projectSelect  = document.getElementById("project-select");
const $suiteSelect    = document.getElementById("suite-select");
const $sectionName    = document.getElementById("section-name");
const $aiProvider     = document.getElementById("ai-provider");
const $createRun      = document.getElementById("create-run");
const $btnStart       = document.getElementById("btn-start");
const $btnStop        = document.getElementById("btn-stop");
const $btnReset       = document.getElementById("btn-reset");
const $optionsLink    = document.getElementById("options-link");
const $statPages      = document.getElementById("stat-pages");
const $statCases      = document.getElementById("stat-cases");
const $statState      = document.getElementById("stat-state");
const $errorList      = document.getElementById("error-list");
const $doneCases      = document.getElementById("done-cases");
const $donePushed     = document.getElementById("done-pushed");
const $testrailLink   = document.getElementById("testrail-run-link");
const $doneError      = document.getElementById("done-error");

// ── State ─────────────────────────────────────────────────────────────────────
let _serverUrl = "http://127.0.0.1:8765";
let _pollInterval = null;

// ── Storage helpers ────────────────────────────────────────────────────────────
async function loadSettings() {
  return new Promise((resolve) =>
    chrome.storage.local.get(
      { serverUrl: "http://127.0.0.1:8765", aiProvider: "rules", aiModel: "" },
      resolve
    )
  );
}

// ── Backend helpers ────────────────────────────────────────────────────────────
async function apiGet(path) {
  const resp = await fetch(`${_serverUrl}${path}`, { method: "GET" });
  if (!resp.ok) throw new Error(`GET ${path} → ${resp.status}`);
  return resp.json();
}

// ── Init ───────────────────────────────────────────────────────────────────────
async function init() {
  const settings = await loadSettings();
  _serverUrl = settings.serverUrl || _serverUrl;
  $aiProvider.value = settings.aiProvider || "claude";

  // Ping backend
  try {
    await apiGet("/health");
    setServerStatus("ok");
    await loadConfig();
  } catch (_) {
    setServerStatus("error");
    $serverError.classList.remove("hidden");
    $btnStart.disabled = true;
  }

  // Check if a crawl is in progress or just completed
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (status) => {
    if (status && status.crawling) {
      showCrawlingUI(status);
      startPolling();
    } else if (status && status.lastStatus) {
      // Crawl finished while popup was closed — show the done screen
      handleFinalStatus(status);
    }
  });
}

function setServerStatus(state) {
  $serverStatus.className = "badge";
  if (state === "ok") {
    $serverStatus.textContent = "connected";
    $serverStatus.classList.add("badge-ok");
  } else if (state === "error") {
    $serverStatus.textContent = "offline";
    $serverStatus.classList.add("badge-error");
  } else {
    $serverStatus.textContent = "checking…";
    $serverStatus.classList.add("badge-checking");
  }
}

async function loadConfig() {
  try {
    const config = await apiGet("/config");
    if (config.status !== "ok") throw new Error(config.error || "Config error");

    // Populate project dropdown
    $projectSelect.innerHTML = '<option value="">— select project —</option>';
    for (const p of config.testrail_projects || []) {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      $projectSelect.appendChild(opt);
    }

    // Restore last-used project
    const { lastProjectId, lastSuiteId } = await new Promise((r) =>
      chrome.storage.local.get({ lastProjectId: "", lastSuiteId: "" }, r)
    );
    if (lastProjectId) {
      $projectSelect.value = lastProjectId;
      await loadSuites(lastProjectId, lastSuiteId);
    }

    // AI provider
    if (config.ai_provider) $aiProvider.value = config.ai_provider;

    $btnStart.disabled = !$projectSelect.value;
  } catch (err) {
    console.error("loadConfig error:", err);
  }
}

async function loadSuites(projectId, selectSuiteId = "") {
  $suiteSelect.innerHTML = '<option value="">Create new suite</option>';
  if (!projectId) return;

  try {
    const suites = await apiGet(
      `/config/suites?project_id=${encodeURIComponent(projectId)}`
    );
    for (const s of suites || []) {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = s.name;
      $suiteSelect.appendChild(opt);
    }
    if (selectSuiteId) $suiteSelect.value = selectSuiteId;
  } catch (_) {
    // Suites endpoint optional — ignore if not available
  }
}

// ── Event listeners ────────────────────────────────────────────────────────────
$projectSelect.addEventListener("change", async () => {
  const pid = $projectSelect.value;
  $btnStart.disabled = !pid;
  if (pid) {
    chrome.storage.local.set({ lastProjectId: pid });
    await loadSuites(pid);
  }
});

$suiteSelect.addEventListener("change", () => {
  chrome.storage.local.set({ lastSuiteId: $suiteSelect.value });
});

$btnStart.addEventListener("click", async () => {
  const projectId = parseInt($projectSelect.value, 10);
  if (!projectId) return;

  const suiteId = $suiteSelect.value ? parseInt($suiteSelect.value, 10) : null;
  const settings = await loadSettings();

  // Get current tab URL for base_url
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const baseUrl = tab ? new URL(tab.url).origin : "";

  const config = {
    serverUrl: _serverUrl,
    testrailProjectId: projectId,
    testrailSuiteId: suiteId,
    sectionName: $sectionName.value.trim() || "Auto-generated",
    aiProvider: $aiProvider.value,
    aiModel: settings.aiModel || "",
    createTestRun: $createRun.checked,
    outputDir: "tests/cases/crawled",
    baseUrl,
  };

  showCrawlingUI({ crawling: true, pagesVisited: 0, casesGenerated: 0, errors: [] });

  chrome.runtime.sendMessage({ type: "START_CRAWL", config }, (resp) => {
    if (resp && !resp.ok) {
      $statState.textContent = `Error: ${resp.error}`;
    }
  });

  startPolling();
});

$btnStop.addEventListener("click", () => {
  stopPolling();
  $statState.textContent = "Stopping…";
  chrome.runtime.sendMessage({ type: "STOP_CRAWL" }, handleFinalStatus);
});

$btnReset.addEventListener("click", () => {
  showConfigUI();
});

$optionsLink.addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});

// ── UI state transitions ───────────────────────────────────────────────────────
function showConfigUI() {
  $configSection.classList.remove("hidden");
  $statusSection.classList.add("hidden");
  $doneSection.classList.add("hidden");
  $btnStart.classList.remove("hidden");
  $btnStop.classList.add("hidden");
  $btnReset.classList.add("hidden");
}

function showCrawlingUI(status) {
  $configSection.classList.add("hidden");
  $statusSection.classList.remove("hidden");
  $doneSection.classList.add("hidden");
  $btnStart.classList.add("hidden");
  $btnStop.classList.remove("hidden");
  $btnReset.classList.add("hidden");
  updateStatusUI(status);
}

function showDoneUI(finalStatus) {
  $configSection.classList.add("hidden");
  $statusSection.classList.add("hidden");
  $doneSection.classList.remove("hidden");
  $btnStart.classList.add("hidden");
  $btnStop.classList.add("hidden");
  $btnReset.classList.remove("hidden");

  $doneCases.textContent = finalStatus.casesGenerated || 0;
  $donePushed.textContent = finalStatus.casesPushed || 0;

  if (finalStatus.testRunUrl) {
    $testrailLink.href = finalStatus.testRunUrl;
    $testrailLink.classList.remove("hidden");
  }

  if (finalStatus.error) {
    $doneError.textContent = `⚠ ${finalStatus.error}`;
    $doneError.classList.remove("hidden");
  } else {
    $doneError.classList.add("hidden");
  }
}

function updateStatusUI(status) {
  const visited = status.pagesVisited || 0;
  const pending = status.pendingCount || 0;
  const total   = visited + pending;
  $statPages.textContent = total > 0 ? `${visited} / ${total}` : visited;
  $statCases.textContent = status.casesGenerated || 0;

  if (status.crawling) {
    const pct = total > 0 ? Math.round((visited / total) * 100) : 0;
    $statState.innerHTML =
      `<span class="spinner"></span>Crawling… ${pct > 0 ? pct + "%" : ""}`;
  } else {
    $statState.textContent = "Done";
  }

  if (status.errors && status.errors.length > 0) {
    $errorList.classList.remove("hidden");
    $errorList.innerHTML = status.errors
      .map((e) => `<div>⚠ ${escapeHtml(e)}</div>`)
      .join("");
  }
}

function handleFinalStatus(status) {
  if (!status) {
    showConfigUI();
    return;
  }
  if (status.lastStatus) {
    showDoneUI({
      casesGenerated: status.casesGenerated,
      casesPushed: status.lastStatus.cases_pushed,
      testRunUrl: status.lastStatus.test_run_url,
      error: status.lastStatus.error || null,
    });
  } else {
    showDoneUI({ casesGenerated: status.casesGenerated || 0 });
  }
}

// ── Polling ────────────────────────────────────────────────────────────────────
function startPolling() {
  stopPolling();
  _pollInterval = setInterval(() => {
    chrome.runtime.sendMessage({ type: "GET_STATUS" }, (status) => {
      if (!status) return;
      updateStatusUI(status);
      if (!status.crawling) {
        stopPolling();
        // Fetch final status with pushed count
        chrome.runtime.sendMessage({ type: "GET_STATUS" }, (final) => {
          handleFinalStatus(final);
        });
      }
    });
  }, 2000);
}

function stopPolling() {
  if (_pollInterval) {
    clearInterval(_pollInterval);
    _pollInterval = null;
  }
}

// ── Util ────────────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Boot ───────────────────────────────────────────────────────────────────────
init();

// Listen for live status pushes from the service worker
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "STATUS_UPDATE") {
    updateStatusUI(msg.status);
    if (!msg.status.crawling) {
      stopPolling();
      handleFinalStatus(msg.status);
    }
  }
});
