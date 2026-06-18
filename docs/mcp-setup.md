# Easy BDD MCP Server — Setup Guide

The Easy BDD MCP server exposes the framework to AI assistants (Claude, Cursor, VS Code
Copilot Chat, etc.) via the [Model Context Protocol](https://modelcontextprotocol.io/).
Once connected, the AI can list, read, validate, and run your tests directly from chat.

---

## Two server flavours

| Server | File | Best for |
|--------|------|----------|
| **Framework server** (`easy_bdd` package) | `easy_bdd/mcp_server.py` | Full framework access — validate, run, fix, TestRail integration |
| **Frontend server** | `frontend/mcp_server.py` | Test authoring — create/update tests, browse actions, workspace management |

Both speak standard MCP over **STDIO** (default) or **SSE** (HTTP).  
STDIO is the right choice for desktop AI clients; SSE is for web-based or remote clients.

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
      "command": "/Users/mark/Projects/easy_bdd/.venv/bin/python",
      "args": ["-m", "easy_bdd", "mcp-serve"],
      "cwd": "/Users/mark/Projects/easy_bdd"
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
      "command": "/Users/mark/Projects/easy_bdd/.venv/bin/python",
      "args": ["frontend/mcp_server.py"],
      "cwd": "/Users/mark/Projects/easy_bdd"
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
      "command": "/Users/mark/Projects/easy_bdd/.venv/bin/python",
      "args": ["-m", "easy_bdd", "mcp-serve"],
      "cwd": "/Users/mark/Projects/easy_bdd"
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
      "command": "C:/path/to/easy_bdd/.venv/Scripts/python.exe",
      "args": ["-m", "easy_bdd", "mcp-serve"],
      "cwd": "C:/path/to/easy_bdd"
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
| Command | `/Users/mark/Projects/easy_bdd/.venv/bin/python -m easy_bdd mcp-serve` |
| Working directory | `/Users/mark/Projects/easy_bdd` |

Or edit `.cursor/mcp.json` directly (same JSON shape as Claude Code above).

---

## VS Code (GitHub Copilot Chat / Copilot Extensions)

Add to `.vscode/mcp.json` in your workspace (VS Code 1.99+):

```json
{
  "servers": {
    "easy-bdd": {
      "type": "stdio",
      "command": "/Users/mark/Projects/easy_bdd/.venv/bin/python",
      "args": ["-m", "easy_bdd", "mcp-serve"],
      "cwd": "/Users/mark/Projects/easy_bdd"
    }
  }
}
```

---

## SSE transport (web clients / remote access)

Start the server in SSE mode:

```bash
python -m easy_bdd mcp-serve --sse --port 8080
# or bind to a specific interface:
python -m easy_bdd mcp-serve --sse --host 127.0.0.1 --port 8080
```

Then configure your client to connect to `http://localhost:8080/sse`.

> SSE mode has no built-in authentication — run it behind a firewall or proxy
> if the port is not loopback-only.

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
