# Easy BDD — Onboarding Guide

Start-to-finish setup for every feature in this repo, written for someone with zero
memory of the project. Follow the sections in order the first time; after that, jump
to whichever section you need.

**What this repo is:** a YAML-based BDD test framework where test cases are authored
in **TestRail** (or locally as `.yaml` files) and executed against real
devices/APIs/browsers via a Python CLI, a web-based Test Builder, an MCP server (so AI
assistants can drive it), and a Chrome-extension-powered crawler that auto-generates
tests from a live UI.

---

## 0. Repo map

| Path | What it is |
|---|---|
| `easybdd/` | The core framework — CLI (`__main__.py`), runner, MCP server, crawler backend |
| `frontend/` | Web UIs: TestRail Test Builder (current) + legacy web builder (deprecated) |
| `chrome_extension/` | Browser extension used by the crawler's "Mode 1" |
| `tests/cases/` | Local YAML test files (if not authoring in TestRail) |
| `config/` | `framework.yaml` (framework config) + device inventory (`devices/`, `device_groups/`) |
| `docs/` | Deep-dive reference docs — this guide links out to them rather than repeating them |
| `Jenkinsfile*` | CI pipelines for running/syncing tests, firmware upgrades, TestRail runs |
| `Firmware/` | Firmware binaries used as test fixtures (not a service — nothing to "set up") |
| `reports/` | Test output: screenshots, videos, HTML reports, TestRail sync artifacts |

---

## 1. Core framework — install and run your first test

```bash
git clone <repository-url>
cd Easy_BDD

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install --upgrade pip
pip install -e .
playwright install chromium
```

Verify:

```bash
python -m easybdd --help
python -m easybdd run tests/cases/ --headed   # runs whatever's in tests/cases/
```

Create `.env` from the template and fill in what you need (TestRail creds are required
for almost everything else in this guide):

```bash
cp .env.example .env
```

Minimum useful `.env` for TestRail-backed work:

```env
TESTRAIL_URL=https://your-instance.testrail.io
TESTRAIL_USERNAME=you@yourcompany.com
TESTRAIL_API_KEY=your_api_key
TESTRAIL_RUNNING_STATUS_ID=7   # check Administration > Statuses in your TestRail instance
```

Common day-to-day commands (see `Makefile` for the full list):

```bash
make run              # python -m easybdd run tests/cases/
make run-tags TAGS=smoke
make validate         # validate all local YAML test files
make test             # unit tests (pytest tests/unit/)
make quality          # lint + type-check + security
```

> Note: `QUICK_START.md` and `docs/setup.md` at the repo root predate some of this and
> reference a generic `Automation-Framework` template — treat this file and `docs/`
> as the current source of truth.

**Next:** [docs/syntax.md](docs/syntax.md) for how to write a test,
[docs/SYNTAX_CHEATSHEET.md](docs/SYNTAX_CHEATSHEET.md) for a quick action lookup.

---

## 2. TestRail integration — the primary authoring surface

Tests are meant to live in TestRail as `Feature:`, `Shared:`, `Var:`, `Setup:`, and
`Teardown:` cases, not as local YAML files. Full reference:
[docs/testrail-integration.md](docs/testrail-integration.md).

Once `.env` has `TESTRAIL_URL` / `TESTRAIL_USERNAME` / `TESTRAIL_API_KEY` set (step 1):

```bash
# Run every case in a TestRail run whose name matches TESTRAIL_RUN_PREFIX
make run-testrail PROJECT=<project_id>

# Create a new TestRail run from a suite
make create-run PROJECT=<project_id> SUITE=<suite_id>
```

Writing steps directly in TestRail: [docs/writing-test-cases.md](docs/writing-test-cases.md).

---

## 3. TestRail Test Builder (web UI) — current recommended editor

This is the actively maintained web UI for authoring TestRail cases. (The older
`frontend/start_builder.py` / `python -m easybdd` local-YAML builder is **deprecated**
— it prints a deprecation notice on startup. Don't use it for new work.)

```bash
pip install -r frontend/requirements_builder.txt
python frontend/start_testrail_builder.py --port 8091
```

Open `http://localhost:8091`. Requires the same `TESTRAIL_URL` / `TESTRAIL_USERNAME` /
`TESTRAIL_API_KEY` in `.env` as step 2.

Use it to browse runs, mark tests for retest, and edit cases without hand-writing YAML
in the TestRail web UI.

### Production instance

The builder also runs persistently on the main Jenkins server
(`<jenkins_url>`) as a systemd service, so nobody needs to run it locally —
just open **<jenkins_url>:8091**.

- Service unit: `/etc/systemd/system/easybdd-testrail-builder.service`
- Runs from `/var/lib/jenkins/workspace/EASY_BDD/frontend` (the same checkout
  Jenkins pipelines use for `EASY_BDD_DIR`), as the `jenkins` user
- Loads TestRail credentials from `/var/lib/jenkins/workspace/EASY_BDD/.env`
- Enabled at boot (`systemctl enable`) and auto-restarts on failure

To pick up new code after a `git pull` in that checkout:

```bash
sudo systemctl restart easybdd-testrail-builder
```

Check status / logs:

```bash
sudo systemctl status easybdd-testrail-builder
journalctl -u easybdd-testrail-builder -f
```

### Floci Browser (web UI, port 8092)

A second web app in the same style: an S3-console-like browser for the local
[Floci](docs/floci-integration.md) S3 emulator — browse buckets and folders,
preview/download objects, upload, and delete (with confirmation).

```bash
python frontend/start_floci_browser.py    # http://localhost:8092
```

Endpoint comes from `FLOCI_ENDPOINT_URL` (env or `.env`), default
`http://localhost:4566`. It also runs persistently on the Floci host as the
`easybdd-floci-browser` systemd service — open **http://192.168.100.100:8092**.
Install/refresh it on the server with
`sudo bash scripts/install_floci_browser_service.sh`; manage it with the same
`systemctl`/`journalctl` commands as above (unit name
`easybdd-floci-browser`). Full details:
[docs/floci-integration.md](docs/floci-integration.md#web-ui-floci-browser).

---

## 4. MCP server — let an AI assistant drive the framework

Exposes the framework as MCP tools (`list_tests`, `run_tests`, `validate_test`,
TestRail sync, crawler, Ollama helpers, etc.) so Claude/Cursor/Copilot can run and fix
tests from chat. Full reference: [docs/mcp-setup.md](docs/mcp-setup.md).

**Fastest path — local, same machine as your AI client (STDIO):**

```bash
pip install -e ".[mcp]"
```

Add to `.claude/settings.json` (or your client's MCP config):

```json
{
  "mcpServers": {
    "easy-bdd": {
      "command": "/absolute/path/to/Easy_BDD/.venv/bin/python",
      "args": ["-m", "easybdd", "mcp-serve"],
      "cwd": "/absolute/path/to/Easy_BDD"
    }
  }
}
```

**Remote server (client on a different machine) — Streamable HTTP:**

```bash
python -m easybdd mcp-serve --streamable-http --host 0.0.0.0 --port 8090
```

Then bridge Claude Desktop to it with `mcp-remote` (requires Node.js on the client
machine) — see [docs/mcp-setup.md](docs/mcp-setup.md#remote-access--streamable-http-recommended)
for the exact `claude_desktop_config.json` block and the systemd unit for running it as
a persistent service.

**Packaged install (no manual JSON, prompts for TestRail/Ollama config in-app):**

```bash
make build-mcpb
```

Produces `easy-bdd-<version>.mcpb` at the repo root — drag it onto Claude Desktop to
install.

Verify it's working by asking your AI client: *"List the available Easy BDD tests."*

---

## 5. Crawler + Chrome extension — auto-generate tests from a live UI

Full reference: [CRAWLER.md](CRAWLER.md). Three modes; the extension is only needed
for Mode 1.

**Backend server (needed for every mode):**

```bash
pip install fastapi uvicorn anthropic --break-system-packages   # or into your venv
```

Add to `.env`:

```env
CRAWLER_AI_PROVIDER=claude            # or "ollama"
ANTHROPIC_API_KEY=sk-ant-...          # if using claude
# OLLAMA_BASE_URL=http://localhost:11434   # if using ollama
```

```bash
python -m easybdd crawler start                       # http://127.0.0.1:8765
```

**Mode 1 — Chrome extension (crawl your own logged-in session):**

1. `chrome://extensions/` → enable **Developer mode** → **Load unpacked** → select
   `chrome_extension/`.
2. Click the Easy BDD icon → gear icon → confirm server URL is `http://127.0.0.1:8765`.
3. Log into the app you want to test, click **Start Crawl**, browse naturally, click
   **Stop & Push**. YAML lands in `tests/cases/crawled/` and gets pushed to TestRail.

**Mode 2 — Playwright browser (no extension, good for CI):**

```bash
python -m easybdd crawler playwright --url https://app.example.com/login --project <id> --provider rules
```

**Mode 3 — convert an existing recording (Chrome DevTools Recorder export or
`playwright codegen` output):**

```bash
python -m easybdd crawler convert-crx my_recording.ts --output tests/cases/
```

---

## 6. Device inventory — testing against real hardware

Devices and device groups (switches, PDUs, cameras, etc.) are defined under
`config/devices/` and `config/device_groups/` as YAML (see `device_template.yaml` for
the schema). Parameterizing a test to run against every device in a group is covered in
[docs/DEVICE_AGNOSTIC_SETUP.md](docs/DEVICE_AGNOSTIC_SETUP.md).

`Firmware/` holds firmware binaries used as fixtures for upgrade tests
(`Jenkinsfile.firmware-wattbox`) — there's no service to install, just files the tests
reference.

---

## 7. CI/CD — Jenkins pipelines

Each `Jenkinsfile.*` at the repo root is a separate Jenkins pipeline:

| File | Purpose |
|---|---|
| `Jenkinsfile` | Main pipeline |
| `Jenkinsfile.branch` | Per-branch build |
| `Jenkinsfile.project` | Project-scoped run |
| `Jenkinsfile.custom` | Ad-hoc custom run |
| `Jenkinsfile.testrail-all` | Run everything against TestRail |
| `Jenkinsfile.testrail-convert` | Convert/import into TestRail |
| `Jenkinsfile.testrail-sync` | Sync results back to TestRail |
| `Jenkinsfile.firmware-wattbox` | Firmware upgrade test pipeline |

Setting up a *new* pipeline (job config, credentials, agent labels) is a Jenkins-side
task, not a repo-side one — talk to whoever administers your Jenkins instance for
credentials/agent access. Once a job exists pointing at one of these files, no
additional repo setup is needed; the pipeline calls the same `make`/`python -m easybdd`
commands documented above. See [docs/ci-cd-integration.md](docs/ci-cd-integration.md)
for the GitHub Actions equivalent and TestRail-run-creation details.

---

## 8. Where to go next

- Full docs index: [docs/README.md](docs/README.md)
- Action reference (every `service.action` you can use in a step): [docs/actions.md](docs/actions.md)
- Assertions: [docs/assertions.md](docs/assertions.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- Contributing (code style, PR process): [CONTRIBUTING.md](CONTRIBUTING.md)
