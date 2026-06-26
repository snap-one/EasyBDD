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
