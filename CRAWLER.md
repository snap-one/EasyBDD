# Easy BDD Crawler

Auto-generates Easy BDD test cases from a live web UI and pushes them to TestRail.
Supports three modes — pick the one that fits your workflow.

---

## Modes at a glance

| Mode | How it crawls | API key needed? | Best for |
|---|---|---|---|
| **Chrome extension** | Extension in your existing Chrome session | No (rule-based) | Already logged-in apps, SPAs |
| **Playwright browser** | Headed Chromium opened by Easy BDD | No (rule-based) | No Chrome extension install, CI |
| **AI-enhanced** (either mode) | Same as above + Claude/Ollama analysis | Yes (Claude) or local GPU (Ollama) | Richer, context-aware tests |
| **CRX converter** | Converts an existing recording file | None | Already have a Playwright/CRX recording |

---

## Mode 1 — Chrome extension

1. You navigate to a web app in Chrome while already logged in.
2. Click **Start Crawl** in the extension popup.
3. The extension crawls the page (and every same-origin page it can reach), capturing interactive elements.
4. Snapshots are sent to the local Python server, which generates Easy BDD YAML test cases.
5. YAML files are written to `tests/cases/crawled/` and pushed to TestRail as Feature: cases.
6. Optionally, a TestRail test run is created covering all generated cases.
7. Run those cases immediately with `python -m easy_bdd testrail-run --project <id>`.

---

## Mode 2 — Playwright browser (no Chrome extension required)

```bash
python -m easy_bdd crawler playwright \
    --url https://app.example.com/login \
    --project 12 \
    --provider rules        # no API key needed
```

**What happens:**
1. A headed Chromium window opens automatically.
2. If the start URL looks like a login page, you have 120 seconds to log in manually.
3. From that point, every page you navigate to is automatically snapshotted using
   Playwright's **accessibility tree** (no content script injection, no DOM scraping).
4. Tests are generated, YAML files written, and cases pushed to TestRail — same pipeline as Mode 1.
5. Close the browser window (or press Ctrl+C) to finish.

**Options:**

```
--url            Starting URL (required)
--project        TestRail project ID (required)
--suite          TestRail suite ID (default: create new)
--section        Section name (default: "Auto-generated")
--provider       rules | claude | ollama  (default: rules)
--model          AI model override (optional)
--output         Output directory (default: tests/cases/crawled)
--no-run         Skip creating a TestRail test run
--login-timeout  Seconds to wait for login (default: 120)
```

**Why accessibility tree instead of DOM?**

Playwright's `page.accessibility.snapshot()` returns the same ARIA tree that
Playwright's own locators use internally — so every selector it produces is
a stable `role=button[name="Save"]` style selector, not a fragile CSS path.
It also crosses same-origin iframes automatically and handles SPA navigation
without any JavaScript injection.

---

---

## Mode 3 — CRX / Playwright recording converter

Convert an existing recording file to Easy BDD YAML without running a crawl.

**Supported input formats:**

| Extension | Source |
|---|---|
| `.ts` / `.js` | Chrome DevTools Recorder → **Export as Playwright test** |
| `.json` | Chrome DevTools Recorder → **Export** (native JSON) |
| `.py` | `playwright codegen --target python` |

```bash
# Convert a single TypeScript recording
python -m easy_bdd crawler convert-crx my_recording.ts

# Convert to a specific output directory
python -m easy_bdd crawler convert-crx my_recording.ts --output tests/cases/

# Convert multiple files at once
python -m easy_bdd crawler convert-crx recordings/*.ts --output tests/cases/
```

**How to record in Chrome DevTools:**

1. Open Chrome DevTools → **Recorder** panel (three-dot menu → More tools → Recorder)
2. Click **Start new recording**, interact with the page, click **End recording**
3. Click the **Export** button:
   - **Export as Playwright test** → saves `.ts` → use with `convert-crx`
   - **Export** (JSON format) → saves `.json` → also works with `convert-crx`

**What gets converted:**

| Playwright API | Easy BDD step |
|---|---|
| `page.goto(url)` | `browser.open: {url: ...}` |
| `page.getByRole(role, {name})` | `browser.click/fill: {role, name}` |
| `page.getByLabel(label)` | `browser.fill: {label, value}` |
| `page.getByPlaceholder(ph)` | `browser.fill: {selector: '[placeholder="..."]', value}` |
| `page.getByTestId(id)` | `browser.click: {selector: '[data-testid="..."]'}` |
| `page.getByText(text)` | `browser.click: {text}` |
| `page.locator(sel)` | `browser.click/fill: {selector}` |
| `page.frameLocator(fr).getBy*(...)` | `browser.click: {selector: 'frame >> inner'}` |
| `page.keyboard.press(key)` | `browser.press_key: {key}` |
| `page.getByRole(...).selectOption(v)` | `browser.select_option: {role, name, value}` |
| `expect(loc).toBeVisible()` | `browser.wait_for_element: {state: visible}` |
| `expect(loc).toHaveText(t)` | `browser.assert_text: {selector, text}` |
| `page.screenshot()` | `browser.screenshot` |

---

## Setup

### 1. Install dependencies

```bash
pip install fastapi uvicorn anthropic --break-system-packages
```

Or add to your virtualenv — `fastapi` and `uvicorn` are already in `requirements.txt`;
`anthropic` was added in this update.

### 2. Configure credentials

Add to your `.env` file:

```env
# TestRail (already required by Easy BDD)
TESTRAIL_URL=https://your-instance.testrail.com/
TESTRAIL_USERNAME=automation@example.com
TESTRAIL_API_KEY=your-api-key

# AI provider (pick one)
ANTHROPIC_API_KEY=sk-ant-...          # for Claude
CRAWLER_AI_PROVIDER=claude             # "claude" | "ollama" (default: claude)
CRAWLER_AI_MODEL=claude-haiku-4-5-20251001   # optional override

# For Ollama (local):
# CRAWLER_AI_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# CRAWLER_AI_MODEL=llama3
```

### 3. Start the crawler server

```bash
python -m easy_bdd crawler start
# Server running at http://127.0.0.1:8765

# Custom host/port:
python -m easy_bdd crawler start --host 0.0.0.0 --port 9000
```

### 4. Load the Chrome extension

1. Open Chrome → `chrome://extensions/`
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select the `chrome_extension/` folder in this repo
4. The Easy BDD icon appears in your toolbar

### 5. Configure the extension (one-time)

Click the extension icon → **⚙ Settings**:

| Setting | Default | Notes |
|---|---|---|
| Server URL | `http://127.0.0.1:8765` | Where the crawler server is running |
| AI provider | `claude` | `claude` or `ollama` |
| Model override | *(blank)* | Leave blank to use `CRAWLER_AI_MODEL` from `.env` |
| Default section name | `Auto-generated` | TestRail section label |
| Output directory | `tests/cases/crawled` | Relative to the Easy BDD repo root |

---

## Usage

1. Log in to the web app you want to test.
2. Click the Easy BDD Crawler icon.
3. Select a **TestRail project** and optionally a **suite**.
4. Click **Start Crawl**.
5. Browse naturally — the extension crawls every same-origin page you visit
   and also auto-follows same-origin links it discovers.
6. Click **Stop & Push** when done.
7. Generated YAML files appear in `tests/cases/crawled/`.
8. A TestRail test run link is shown in the popup.

---

## Generated test format

Each crawled page produces one or more YAML files like:

```yaml
name: Login form — happy path
description: Verifies user can log in with valid credentials
tags: [browser, crawled, smoke]

variables:
  base_url: https://your-app.example.com
  username: ${USERNAME}
  password: ${PASSWORD}

steps:
  - browser.open:
      url: ${base_url}/login

  - browser.fill:
      selector: "#email"        # Fallback selectors: label:"Email" | text:"Email" (score=0.85)
      value: ${username}

  - browser.fill:
      selector: "#password"
      value: ${password}

  - browser.click:
      role: button
      name: Sign In

  - browser.screenshot:
      name: after-login

  - browser.assert_text:
      selector: h1
      text: Dashboard
```

Selector fallback comments are embedded so engineers can upgrade fragile selectors.

---

## Self-healing selectors

When a selector breaks at runtime, the framework tries three strategies in order:

1. **Fallback chain** — tries the alternative selectors stored in test metadata (ARIA, label, text, ID)
2. **AI re-locate** — sends the broken selector + current page HTML to the AI to suggest a new one
3. **Visual similarity** — finds an element at roughly the same screen position using bounding box comparison

Enable by setting `ANTHROPIC_API_KEY` (or `CRAWLER_AI_PROVIDER=ollama`) in `.env`.
No config change is needed in existing YAML tests — healing runs automatically.

---

## TestRail structure created

```
Project (existing, selected in popup)
  └── Suite  "Auto-generated (Easy BDD Crawler)"  [new or reused]
        └── Section  "Auto-generated / login"      [one per URL path]
              ├── Feature: Login form — happy path
              ├── Feature: Login form — empty fields validation
              └── Feature: Password reset flow
  └── Run  "Crawler Run — 2026-06-18 14:32"        [optional]
```

Cases use the **Feature: prefix** format — the `testrail_runner` executes them
directly without needing a local YAML file.

---

## Iframe handling

Elements inside same-origin iframes are automatically detected and included.
Generated selectors use the Easy BDD `iframe >> selector` syntax:

```yaml
- browser.fill:
    selector: "iframe#config-frame >> [name='hostname']"
    value: ${new_hostname}
```

Cross-origin iframes are listed in the snapshot but cannot be introspected
due to browser security policies.

---

## Troubleshooting

**Extension says "Backend not reachable"**
→ Run `python -m easy_bdd crawler start` and ensure the port matches the Settings page.

**No cases generated**
→ Check that `ANTHROPIC_API_KEY` or Ollama is running. Look at the server terminal for AI errors.

**TestRail push fails**
→ Verify `TESTRAIL_URL`, `TESTRAIL_USERNAME`, `TESTRAIL_API_KEY` in `.env`.
Check that the project supports multiple suites (TestRail project type).

**Generated selectors are fragile (nth-child)**
→ Run `python -m easy_bdd selector-audit tests/cases/crawled/` to find upgrade opportunities.
Adding `data-testid` attributes to your app's HTML is the most effective long-term fix.
