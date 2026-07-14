# Easy BDD MCP Server — Setup Guide

The Easy BDD MCP server exposes the framework to AI assistants (Claude, Cursor, VS Code
Copilot Chat, etc.) via the [Model Context Protocol](https://modelcontextprotocol.io/).
Once connected, the AI can list, read, validate, and run your tests directly from chat.

---

## Two server flavours

| Server | File | Best for |
|--------|------|----------|
| **Framework server** (`easybdd` package) | `easybdd/mcp_server.py` | Full framework access — validate, run, fix, TestRail integration |
| **Frontend server** | `frontend/mcp_server.py` | Test authoring — create/update tests, browse actions, workspace management |

Both speak standard MCP over **STDIO** (default), **Streamable HTTP** (recommended for remote access), or **SSE** (deprecated).  
STDIO is the right choice when the AI client runs on the same machine. Streamable HTTP is for remote servers accessed over a network.

---

## Prerequisites

1. **Python 3.9+** with the project's virtual environment active.
2. **`mcp` package** — installed automatically via the `mcp` extra:

   ```bash
   pip install -e ".[mcp]"
   ```

   Or manually:

   ```bash
   pip install "mcp>=1.0.0"
   ```

3. **`.env` file** at the project root for credentials used by the framework:

   ```dotenv
   # Required for validate_testrail_case tool
   TESTRAIL_URL=https://yourcompany.testrail.io
   TESTRAIL_USERNAME=you@yourcompany.com
   TESTRAIL_API_KEY=your_api_key

   # Any other env vars your tests reference
   DEVICE_PASSWORD=...
   ```

---

## Claude Code (CLI / desktop app)

Add the server to your project's `.claude/settings.json` (project-scoped) or
`~/.claude/settings.json` (global):

```json
{
  "mcpServers": {
    "easy-bdd": {
      "command": "/Users/mark/Projects/easybdd/.venv/bin/python",
      "args": ["-m", "easybdd", "mcp-serve"],
      "cwd": "/Users/mark/Projects/easybdd"
    }
  }
}
```

> **Tip:** Use the absolute path to the venv's Python so the correct environment
> is always used regardless of which shell Claude Code is launched from.

To use the **frontend server** instead (or in addition):

```json
{
  "mcpServers": {
    "easy-bdd-frontend": {
      "command": "/Users/mark/Projects/easybdd/.venv/bin/python",
      "args": ["frontend/mcp_server.py"],
      "cwd": "/Users/mark/Projects/easybdd"
    }
  }
}
```

After editing the config, reload MCP servers with `/mcp` → **Restart** in the Claude
Code UI, or restart the app.

---

## Claude Desktop (macOS / Windows)

There are two ways to connect Claude Desktop: install the packaged **`.mcpb` extension**
(recommended — no manual JSON editing, prompts for TestRail/Ollama config in the UI), or
edit `claude_desktop_config.json` by hand.

### Option A — Install the `.mcpb` extension (recommended)

The project ships a build script that packages the server, its manifest, and metadata
into a single `.mcpb` file Claude Desktop can install directly:

```bash
make build-mcpb
# or: python build_mcpb.py
```

This reads [`manifest.json`](../manifest.json) and zips up the `easybdd/` package plus
project metadata (skipping anything listed in [`.mcpbignore`](../.mcpbignore) — build
artifacts, the venv, firmware/docs/tests that aren't needed to run the server) into
`easy-bdd-<version>.mcpb` at the project root.

To install: open (or drag) `easy-bdd-1.0.0.mcpb` onto the Claude Desktop app. You'll be
prompted for the `user_config` fields declared in `manifest.json` — TestRail URL/username/
API key and the Ollama base URL/model — which get injected as environment variables into
the server process (`TESTRAIL_URL`, `TESTRAIL_USERNAME`, `TESTRAIL_API_KEY`,
`OLLAMA_BASE_URL`, `CRAWLER_AI_MODEL`). Leave any of them blank if you don't use that
integration.

Requires `uv` on the machine running Claude Desktop — the manifest launches the server
with `uv run --directory <extension_dir> --extra mcp python -m easybdd mcp-serve`, so `uv`
resolves and runs the Python environment itself; no separate venv setup needed.

To rebuild after code changes, just re-run `make build-mcpb` and reinstall the `.mcpb`.

### Option B — Manual config

Edit `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "easy-bdd": {
      "command": "/Users/mark/Projects/easybdd/.venv/bin/python",
      "args": ["-m", "easybdd", "mcp-serve"],
      "cwd": "/Users/mark/Projects/easybdd"
    }
  }
}
```

On **Windows**, use forward slashes or escaped backslashes and point to the venv
Python:

```json
{
  "mcpServers": {
    "easy-bdd": {
      "command": "C:/path/to/easybdd/.venv/Scripts/python.exe",
      "args": ["-m", "easybdd", "mcp-serve"],
      "cwd": "C:/path/to/easybdd"
    }
  }
}
```

Restart Claude Desktop to pick up the change.

---

## Cursor

Open **Settings → Features → MCP** and add a new server entry:

| Field | Value |
|-------|-------|
| Name | `easy-bdd` |
| Type | `command` |
| Command | `/Users/mark/Projects/easybdd/.venv/bin/python -m easybdd mcp-serve` |
| Working directory | `/Users/mark/Projects/easybdd` |

Or edit `.cursor/mcp.json` directly (same JSON shape as Claude Code above).

---

## VS Code (GitHub Copilot Chat / Copilot Extensions)

Add to `.vscode/mcp.json` in your workspace (VS Code 1.99+):

```json
{
  "servers": {
    "easy-bdd": {
      "type": "stdio",
      "command": "/Users/mark/Projects/easybdd/.venv/bin/python",
      "args": ["-m", "easybdd", "mcp-serve"],
      "cwd": "/Users/mark/Projects/easybdd"
    }
  }
}
```

---

## Remote access — Streamable HTTP (recommended)

Use this when the MCP server runs on a separate machine (e.g. a Linux CI server)
and your AI client (Claude Desktop, Cursor) runs on a different machine.

### Start the server

```bash
# Foreground
python -m easybdd mcp-serve --streamable-http --host 0.0.0.0 --port 8090

# Background (daemon)
nohup python -m easybdd mcp-serve --streamable-http --host 0.0.0.0 --port 8090 \
  >> mcp_server.log 2>&1 &
```

The server exposes `http://<host>:8090/mcp`.

### Run as a systemd service (Linux)

Create `/etc/systemd/system/easy-bdd-mcp.service`:

```ini
[Unit]
Description=Easy BDD MCP Server
After=network.target

[Service]
Type=simple
User=jenkins
WorkingDirectory=/home/jenkins/Easy_BDD
ExecStart=/home/jenkins/Easy_BDD/env/bin/python -m easybdd mcp-serve --streamable-http --host 0.0.0.0 --port 8090
EnvironmentFile=/home/jenkins/Easy_BDD/.env
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now easy-bdd-mcp.service
sudo systemctl status easy-bdd-mcp.service
```

### Connect Claude Desktop to a remote server

Claude Desktop's config file only accepts stdio (command-based) servers — it cannot
connect to a remote HTTP URL directly. Use **`mcp-remote`** as a bridge.

**Requirements:** Node.js must be installed on the Windows/Mac machine running
Claude Desktop (`winget install OpenJS.NodeJS` on Windows).

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "easy-bdd": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://192.168.100.191:8090/mcp",
        "--transport", "http-only",
        "--allow-http"
      ]
    }
  }
}
```

> `--allow-http` is required for plain `http://` URLs. If your server is on
> `localhost` or `127.0.0.1`, you can omit it. For production, put the server
> behind a reverse proxy with TLS and drop both flags.

Restart Claude Desktop after saving. The `easy-bdd` tools will appear in the
tool picker once the connection is established.

### Verify the endpoint is reachable

```bash
# From the server itself
curl -s http://localhost:8090/mcp
# Expect: 406 Not Acceptable (correct — needs proper MCP client headers)

# From another machine on the network
curl -s http://192.168.100.191:8090/mcp
```

A `404` means the server isn't running or is using the old `--sse` transport.
A `406` confirms the `/mcp` endpoint is live and ready.

---

## SSE transport (deprecated)

SSE transport is deprecated in the MCP specification. Use `--streamable-http`
instead. The `--sse` flag is kept for backwards compatibility only.

```bash
python -m easybdd mcp-serve --sse --port 8080
```

Clients connect to `http://localhost:8080/sse`.

---

## Verifying the connection

Once connected, ask the AI:

> "List the available Easy BDD tests."

It should call `list_tests` and return your test files. If you see a tool-call
error, check:

1. The Python path resolves correctly (`which python` in the project venv).
2. The `mcp` package is installed (`pip show mcp`).
3. The `cwd` in the config matches the project root (where `config/framework.yaml`
   lives).

---

## Available tools (framework server)

| Tool | What it does |
|------|-------------|
| `list_tests` | List test files, optionally filtered by tag |
| `get_test` | Return raw YAML of a single test |
| `validate_test` | Check syntax of a file or inline snippet |
| `get_shared_steps` | Return shared_steps.yaml contents |
| `run_tests` | Dry-run (default) or live-execute tests |
| `get_failure_trace` | Read the execution log from the latest report |
| `preview_fix` | Show auto-correctable fixes without writing |
| `apply_fix` | Write fixes to disk (requires `confirmed=True`) |
| `validate_testrail_case` | Validate BDD syntax in TestRail cases via API |
| `probe_selector` | Test whether CSS/ARIA/text selectors resolve on a live page |
| `fix_test_selectors` | Heal selector issues in a YAML file against a live page |
| `fix_crawled_tests` | Batch-heal selector issues across multiple crawled test files |
| `get_testrail_run_failures` | Fetch failed/retest cases from a TestRail run |
| `repush_yaml_to_testrail` | Re-push a YAML file's steps to a TestRail case's Preconditions |
| `import_playwright_recording` | Convert a Playwright recording to Easy BDD YAML test cases |
| `ollama_chat` | Send a prompt directly to the configured Ollama model |
| `ollama_analyze_test` | Ask Ollama to review an Easy BDD test case and suggest improvements |
| `ollama_generate_tests` | Ask Ollama to generate new Easy BDD test cases for a feature |
| `ollama_improve_testrail_case` | Fetch a TestRail case and improve its steps via Ollama |
| `crawl_device` | Crawl a live device UI with Playwright and generate an Easy BDD/TestRail suite |

## Available prompts (framework server)

Prompts are packaged, multi-step workflows — invoke them from your MCP client's prompt
picker (in Claude Desktop: the `+` menu next to the chat box) rather than asking for them
in plain English.

| Prompt | Arguments | What it does |
|--------|-----------|---------------|
| `generate_tests` | `module`, `description` | Generate complete YAML test cases for a module/feature |
| `debug_failure` | `test_name`, `report_path` | Diagnose a failing test from its execution trace and suggest a fix |
| `validate_and_fix` | `path` | Validate a test file and interactively apply suggested fixes |
| `debug_testrail_run` | `run_id`, `auto_fix` | End-to-end triage of every failure in a TestRail run — validate local YAML, probe live selectors, and (if `auto_fix=true`) apply + re-push corrections |
| `validate_testrail_suite` | `project_id`, `suite_id`, `fix` | Validate every case in a TestRail suite and produce a prioritised fix plan |
| `create_test_from_description` | `feature_description`, `page_url`, `project_id`, `suite_id`, `count` | Generate tests from a plain-English description and optionally push them to TestRail |

Example — debugging a whole failing run in one step:

> Run the `debug_testrail_run` prompt with `run_id=196112`.

## Available tools (frontend server)

| Tool | What it does |
|------|-------------|
| `list_actions` | Browse all actions by category |
| `get_action` | Full parameter details for one action |
| `list_workspaces` | List workspace folders under `tests/cases/` |
| `list_tests` | List tests, optionally by workspace |
| `read_test` | Read a test file |
| `create_test` | Create a new test YAML file |
| `update_test` | Overwrite an existing test YAML file |
| `validate_yaml` | Validate YAML before saving |
| `list_shared_steps` | List shared steps (global + per-workspace) |
| `get_shared_step` | Full definition of one shared step |
| `run_test` | Execute a single test |
| `get_examples` | Curated YAML snippets by category |
