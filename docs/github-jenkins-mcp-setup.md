# Connecting AI Clients to GitHub and Jenkins via MCP

This is the flip side of [mcp-setup.md](./mcp-setup.md): instead of exposing *this*
project's Easy BDD server to an AI assistant, this doc covers connecting an AI
assistant (Claude Code, Claude Desktop, VS Code) to **GitHub's** and **Jenkins'**
own remote MCP servers — so the assistant can read/write PRs and issues, and
inspect/trigger Jenkins builds, directly from chat.

Both integrations here are **remote HTTP MCP servers** authenticated with a
static `Authorization` header (Bearer for GitHub, Basic for Jenkins) — no local
process to run, just a URL and a credential.

The self-hosted **Jira** and **Confluence** MCP servers follow the same
static-header pattern but have their own deployment/operations doc:
[atlassian-mcp-setup.md](./atlassian-mcp-setup.md).

> **Security note:** this repo is public. Never commit a real token, API key,
> or internal hostname/IP into a checked-in config file — use a placeholder
> (e.g. `<jenkins_url>`, `<github_token>`) in anything that goes into git, and
> keep the real values in a local, untracked config or your OS keychain.

---

## What each integration gives you

| Server | Endpoint | Auth | Example tools |
|--------|----------|------|---------------|
| **GitHub** | `https://api.githubcopilot.com/mcp/` — GitHub's own hosted remote MCP server, no self-hosting required | `Authorization: Bearer <github_token>` (a GitHub personal access token) | `create_pull_request`, `list_issues`, `search_code`, `get_file_contents`, `merge_pull_request`, `pull_request_review_write` |
| **Jenkins** | `<jenkins_url>/mcp-server/mcp` — requires the **[MCP Server](https://plugins.jenkins.io/mcp-server/)** plugin installed on the Jenkins controller | `Authorization: Basic <base64(username:api_token)>` | `triggerBuild`, `getBuildLog`, `getTestResults`, `getJobScm`, `findJobsWithScmUrl`, `getFlakyFailures` |

### Prerequisites

- **GitHub**: a personal access token with the scopes you need (`repo` for
  private-repo read/write, plus `workflow`/`read:org` etc. depending on which
  tools you use). Generate one at **GitHub → Settings → Developer settings →
  Personal access tokens**.
- **Jenkins**: the **MCP Server** plugin installed (**Manage Jenkins → Plugins**),
  and a Jenkins API token for the account you want the assistant to act as
  (**your user icon → Configure → API Token → Add new Token**). Build the
  Basic auth header as `base64("username:api_token")` — note the **username is
  required**; a blank username with just the token produces a `401`.

---

## Claude Code (CLI and VS Code extension)

Claude Code's own MCP config is a single system shared by the CLI and the
[Claude Code VS Code extension](https://marketplace.visualstudio.com/items?itemName=anthropic.claude-code)
— add a server once via the CLI and it's immediately available in both. Inside
the extension's chat panel, `/mcp` manages servers the same way the CLI does.

Add each server with `claude mcp add`, using `--transport http` and one or more
`--header` flags for auth:

```bash
# GitHub
claude mcp add --transport http github https://api.githubcopilot.com/mcp/ \
  --header "Authorization: Bearer <github_token>"

# Jenkins
claude mcp add --transport http jenkins <jenkins_url>/mcp-server/mcp \
  --header "Authorization: Basic $(echo -n '<username>:<api_token>' | base64)"
```

### Scopes — where the config actually lives

`claude mcp add` writes to one of three places depending on `--scope`
(`-s`), default `local`:

| Scope | Stored in | Use for |
|-------|-----------|---------|
| `local` (default) | `~/.claude.json`, under this project's entry | Personal servers with secrets baked into the header — **never shared**, safe default when the auth header contains a real token |
| `project` | `.mcp.json` at the repo root — **gets checked into git** | Servers the whole team should get automatically — do **not** use this for GitHub/Jenkins as configured above, since the header contains a literal secret |
| `user` | `~/.claude.json`, global (all projects) | Same server useful across every project you work in |

Because both the GitHub and Jenkins configs above embed a real credential
in the `Authorization` header, stick to `local` or `user` scope. If you want
this checked into `.mcp.json` for the team, omit the `headers` field there and
have each teammate add their own credential at `local` scope instead — Claude
Code merges project-scoped and local-scoped entries for the same server name.

The resulting entry looks like this (this is the literal shape Claude Code
writes to `~/.claude.json`):

```json
{
  "mcpServers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp/",
      "headers": { "Authorization": "Bearer <github_token>" }
    },
    "jenkins": {
      "type": "http",
      "url": "<jenkins_url>/mcp-server/mcp",
      "headers": { "Authorization": "Basic <base64_user_colon_token>" }
    }
  }
}
```

Deferred/MCP tools only register at startup — after adding a server, **restart
Claude Code** (or the VS Code window) once before its tools show up.

---

## Claude Desktop

Claude Desktop's config file (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows) is built
around launching a local **command** (stdio) — it does not take a direct
`"type": "http"` + custom-header entry the way Claude Code's config does. For
a remote HTTP server with a static auth header, bridge through
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote), same pattern as the
[remote Easy BDD setup](./mcp-setup.md#connect-claude-desktop-to-a-remote-server):

**Requirements:** Node.js on the machine running Claude Desktop.

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://api.githubcopilot.com/mcp/",
        "--header", "Authorization: Bearer <github_token>"
      ]
    },
    "jenkins": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "<jenkins_url>/mcp-server/mcp",
        "--header", "Authorization: Basic <base64_user_colon_token>",
        "--transport", "http-only",
        "--allow-http"
      ]
    }
  }
}
```

> `--allow-http` is only needed if the Jenkins URL is plain `http://` rather
> than `https://`. Drop it for an HTTPS Jenkins URL.

Restart Claude Desktop after saving. Newer Desktop builds also expose
**Settings → Connectors → Add custom connector**, which is the right path if
your server supports OAuth — GitHub's and Jenkins' setups here use static
header auth instead, so the `mcp-remote` JSON above is the reliable option.

---

## VS Code

There are two independent things named similarly here — use the one that
matches what you actually have installed:

- **Claude Code extension** (the one that shares config with the CLI above):
  once you've run `claude mcp add ...` from a terminal (integrated or
  external), the same servers appear automatically in the extension's chat —
  no separate VS Code-specific config needed. Manage them with `/mcp` inside
  the chat panel.
- **VS Code's native MCP support for GitHub Copilot Chat** (unrelated to
  Claude Code): configured via `.vscode/mcp.json` in the workspace, same shape
  already used for the Easy BDD server in [mcp-setup.md](./mcp-setup.md#vs-code-github-copilot-chat--copilot-extensions):

  ```json
  {
    "servers": {
      "github": {
        "type": "http",
        "url": "https://api.githubcopilot.com/mcp/",
        "headers": { "Authorization": "Bearer ${input:github_token}" }
      },
      "jenkins": {
        "type": "http",
        "url": "<jenkins_url>/mcp-server/mcp",
        "headers": { "Authorization": "Basic ${input:jenkins_basic_auth}" }
      }
    },
    "inputs": [
      { "id": "github_token", "type": "promptString", "password": true },
      { "id": "jenkins_basic_auth", "type": "promptString", "password": true }
    ]
  }
  ```

  The `inputs` block prompts for the secret on first use instead of storing it
  in the file — the right choice here since `.vscode/mcp.json` is normally
  checked into the repo.

---

## Verifying the connection

Once connected, ask the assistant something that only works if the tools are
live:

> "Who am I authenticated as in Jenkins?" (should call `whoAmI`)
>
> "List my open pull requests on this repo." (should call `list_pull_requests`
> or `search_pull_requests`)

If a call comes back `401 Unauthorized`, double-check the header — for
Jenkins specifically, the most common mistake is a Basic-auth value built from
an empty username (`base64(":<token>")` instead of `base64("<username>:<token>")`).
