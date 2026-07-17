#!/usr/bin/env bash
# Easy BDD MCP — one-command setup for macOS and Linux.
#
# Engineers run (token comes from Mark Fomin):
#   curl -fsSL http://192.168.100.100:8092/setup | EASYBDD_TOKEN=<token> bash
# If EASYBDD_TOKEN is not set, the script asks for it interactively.
#
# What it does:
#   1. Checks the Easy BDD MCP server is reachable and the token is valid.
#   2. Configures Claude Code (if installed) — native HTTP, no extras needed.
#   3. Configures Claude Desktop (if installed) via the mcp-remote bridge,
#      installing Node.js first when possible.
# It never removes existing MCP servers from your config; it only adds/updates
# the "easybdd" entry. A timestamped backup of your config is made first.

set -u

MCP_URL="${EASYBDD_MCP_URL:-http://192.168.100.100:8092/mcp}"
TOKEN="${EASYBDD_TOKEN:-}"
OS="$(uname -s)"
CONFIGURED=""

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ✓ \033[0m%s\n' "$*"; }
warn() { printf '\033[1;33m ! \033[0m%s\n' "$*"; }
fail() { printf '\033[1;31m ✗ %s\033[0m\n' "$*"; }

say "Easy BDD MCP setup (server: $MCP_URL)"

# --- 1. Reachability ---------------------------------------------------------
if curl -s -o /dev/null -m 8 "$MCP_URL"; then
  ok "Server is reachable."
else
  fail "Cannot reach $MCP_URL"
  echo "   Make sure you are on the office network or VPN, then run this again."
  exit 1
fi

# --- 2. Access token ---------------------------------------------------------
if [ -z "$TOKEN" ] && [ -r /dev/tty ]; then
  printf 'Paste the Easy BDD access token (ask Mark Fomin), then press Enter: ' > /dev/tty
  read -r TOKEN < /dev/tty || TOKEN=""
fi
if [ -z "$TOKEN" ]; then
  fail "No access token provided."
  echo "   Ask Mark Fomin for the token, then run:"
  echo "   curl -fsSL ${MCP_URL%/mcp}/setup | EASYBDD_TOKEN=<token> bash"
  exit 1
fi

STATUS=$(curl -s -o /dev/null -m 8 -w '%{http_code}' "$MCP_URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Accept: application/json, text/event-stream' -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"setup-check","version":"0"}}}')
if [ "$STATUS" = "401" ]; then
  fail "The access token was rejected by the server."
  echo "   Double-check it with Mark Fomin and run this again."
  exit 1
fi
ok "Access token accepted."

# --- 2.5 Jenkins MCP (optional; credentials stay on the server) ----------------
# The server hands out the Jenkins MCP endpoint and a ready-made Authorization
# header (gated by the same access token). If Jenkins isn't configured
# server-side, this 404s and we simply skip it.
JENKINS_MCP_URL=""
JENKINS_MCP_AUTH=""
JCONF=$(curl -s -m 8 "${MCP_URL%/mcp}/jenkins-mcp-config" -H "Authorization: Bearer $TOKEN" || true)
case "$JCONF" in
  *'"url"'*)
    JENKINS_MCP_URL=$(printf '%s' "$JCONF" | sed -n 's/.*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    JENKINS_MCP_AUTH=$(printf '%s' "$JCONF" | sed -n 's/.*"authorization"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    ;;
esac
if [ -n "$JENKINS_MCP_URL" ] && [ -n "$JENKINS_MCP_AUTH" ]; then
  ok "Jenkins MCP is enabled on the server — will configure it too."
else
  JENKINS_MCP_URL=""; JENKINS_MCP_AUTH=""
  warn "Jenkins MCP not enabled on the server — skipping that part."
fi

# --- 2.6 Jira MCP (optional; credentials stay on the server) ------------------
# Same idea as Jenkins: the server hands out the self-hosted Jira MCP endpoint
# and a ready-made Authorization header. 404s and is skipped if not configured.
JIRA_MCP_URL=""
JIRA_MCP_AUTH=""
JIRACONF=$(curl -s -m 8 "${MCP_URL%/mcp}/jira-mcp-config" -H "Authorization: Bearer $TOKEN" || true)
case "$JIRACONF" in
  *'"url"'*)
    JIRA_MCP_URL=$(printf '%s' "$JIRACONF" | sed -n 's/.*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    JIRA_MCP_AUTH=$(printf '%s' "$JIRACONF" | sed -n 's/.*"authorization"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    ;;
esac
if [ -n "$JIRA_MCP_URL" ] && [ -n "$JIRA_MCP_AUTH" ]; then
  ok "Jira MCP is enabled on the server — will configure it too."
else
  JIRA_MCP_URL=""; JIRA_MCP_AUTH=""
  warn "Jira MCP not enabled on the server — skipping that part."
fi

# --- 2.7 Confluence MCP (optional; credentials stay on the server) -----------
# Same idea as Jenkins/Jira: the server hands out the self-hosted Confluence
# MCP endpoint and a ready-made Authorization header. 404s and is skipped if
# not configured.
CONFLUENCE_MCP_URL=""
CONFLUENCE_MCP_AUTH=""
CONFCONF=$(curl -s -m 8 "${MCP_URL%/mcp}/confluence-mcp-config" -H "Authorization: Bearer $TOKEN" || true)
case "$CONFCONF" in
  *'"url"'*)
    CONFLUENCE_MCP_URL=$(printf '%s' "$CONFCONF" | sed -n 's/.*"url"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    CONFLUENCE_MCP_AUTH=$(printf '%s' "$CONFCONF" | sed -n 's/.*"authorization"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    ;;
esac
if [ -n "$CONFLUENCE_MCP_URL" ] && [ -n "$CONFLUENCE_MCP_AUTH" ]; then
  ok "Confluence MCP is enabled on the server — will configure it too."
else
  CONFLUENCE_MCP_URL=""; CONFLUENCE_MCP_AUTH=""
  warn "Confluence MCP not enabled on the server — skipping that part."
fi

# --- 3. Claude Code (CLI / IDE) ----------------------------------------------
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user easybdd >/dev/null 2>&1 || true
  if claude mcp add --scope user --transport http easybdd "$MCP_URL" \
       --header "Authorization: Bearer $TOKEN" >/dev/null 2>&1; then
    ok "Claude Code configured (user scope)."
    CONFIGURED="Claude Code"
  else
    warn "Claude Code is installed but 'claude mcp add' failed — configure it manually later."
  fi
  if [ -n "$JENKINS_MCP_URL" ]; then
    claude mcp remove --scope user jenkins >/dev/null 2>&1 || true
    if claude mcp add --scope user --transport http jenkins "$JENKINS_MCP_URL" \
         --header "Authorization: $JENKINS_MCP_AUTH" >/dev/null 2>&1; then
      ok "Claude Code: jenkins MCP configured."
    else
      warn "Could not add the jenkins MCP server to Claude Code."
    fi
  fi
  if [ -n "$JIRA_MCP_URL" ]; then
    claude mcp remove --scope user jira >/dev/null 2>&1 || true
    if claude mcp add --scope user --transport http jira "$JIRA_MCP_URL" \
         --header "Authorization: $JIRA_MCP_AUTH" >/dev/null 2>&1; then
      ok "Claude Code: jira MCP configured."
    else
      warn "Could not add the jira MCP server to Claude Code."
    fi
  fi
  if [ -n "$CONFLUENCE_MCP_URL" ]; then
    claude mcp remove --scope user confluence >/dev/null 2>&1 || true
    if claude mcp add --scope user --transport http confluence "$CONFLUENCE_MCP_URL" \
         --header "Authorization: $CONFLUENCE_MCP_AUTH" >/dev/null 2>&1; then
      ok "Claude Code: confluence MCP configured."
    else
      warn "Could not add the confluence MCP server to Claude Code."
    fi
  fi
fi

# --- 4. Claude Desktop ---------------------------------------------------------
case "$OS" in
  Darwin) DESKTOP_DIR="$HOME/Library/Application Support/Claude" ;;
  Linux)  DESKTOP_DIR="$HOME/.config/Claude" ;;
  *)      DESKTOP_DIR="" ;;
esac

desktop_installed=false
if [ "$OS" = "Darwin" ] && [ -d "/Applications/Claude.app" ]; then
  desktop_installed=true
elif [ -n "$DESKTOP_DIR" ] && [ -d "$DESKTOP_DIR" ]; then
  desktop_installed=true
fi

if ! $desktop_installed; then
  if [ -z "$CONFIGURED" ]; then
    fail "Neither Claude Desktop nor Claude Code found."
    echo "   Install Claude Desktop from https://claude.ai/download (macOS/Windows)"
    echo "   or Claude Code from https://claude.ai/code, then run this again."
    exit 1
  else
    warn "Claude Desktop not found — skipped. ($CONFIGURED was configured.)"
  fi
else
  # Desktop needs Node.js to run the mcp-remote bridge.
  if ! command -v node >/dev/null 2>&1; then
    say "Node.js is required for Claude Desktop — attempting to install it..."
    if [ "$OS" = "Darwin" ] && command -v brew >/dev/null 2>&1; then
      brew install node
    elif command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update -qq && sudo apt-get install -y nodejs npm
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y nodejs npm
    fi
  fi

  if ! command -v node >/dev/null 2>&1; then
    fail "Node.js could not be installed automatically."
    echo "   Install it from https://nodejs.org (choose LTS), then run this again."
    [ -n "$CONFIGURED" ] && warn "($CONFIGURED was still configured successfully.)"
    exit 1
  fi
  ok "Node.js found: $(node --version)"

  mkdir -p "$DESKTOP_DIR"
  CONFIG="$DESKTOP_DIR/claude_desktop_config.json"
  if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$CONFIG.backup.$(date +%Y%m%d%H%M%S)"
    ok "Backed up existing Claude Desktop config."
  fi

  node - "$CONFIG" "$MCP_URL" "$TOKEN" "$JENKINS_MCP_URL" "$JENKINS_MCP_AUTH" "$JIRA_MCP_URL" "$JIRA_MCP_AUTH" "$CONFLUENCE_MCP_URL" "$CONFLUENCE_MCP_AUTH" <<'EOF'
const fs = require("fs");
const [config, url, token, jenkinsUrl, jenkinsAuth, jiraUrl, jiraAuth, confluenceUrl, confluenceAuth] = process.argv.slice(2);
let cfg = {};
try { cfg = JSON.parse(fs.readFileSync(config, "utf8")); } catch (e) {}
if (typeof cfg !== "object" || cfg === null || Array.isArray(cfg)) cfg = {};
cfg.mcpServers = cfg.mcpServers || {};
// Token is passed via env and expanded by mcp-remote itself; keeping the
// header value free of spaces also avoids a Claude Desktop arg-parsing bug.
cfg.mcpServers.easybdd = {
  command: "npx",
  args: ["-y", "mcp-remote", url, "--allow-http", "--transport", "http-only",
         "--header", "Authorization:${EASYBDD_AUTH}"],
  env: { EASYBDD_AUTH: "Bearer " + token },
};
if (jenkinsUrl && jenkinsAuth) {
  cfg.mcpServers.jenkins = {
    command: "npx",
    args: ["-y", "mcp-remote", jenkinsUrl, "--allow-http", "--transport", "http-only",
           "--header", "Authorization:${JENKINS_AUTH}"],
    env: { JENKINS_AUTH: jenkinsAuth },
  };
}
if (jiraUrl && jiraAuth) {
  cfg.mcpServers.jira = {
    command: "npx",
    args: ["-y", "mcp-remote", jiraUrl, "--allow-http", "--transport", "http-only",
           "--header", "Authorization:${JIRA_AUTH}"],
    env: { JIRA_AUTH: jiraAuth },
  };
}
if (confluenceUrl && confluenceAuth) {
  cfg.mcpServers.confluence = {
    command: "npx",
    args: ["-y", "mcp-remote", confluenceUrl, "--allow-http", "--transport", "http-only",
           "--header", "Authorization:${CONFLUENCE_AUTH}"],
    env: { CONFLUENCE_AUTH: confluenceAuth },
  };
}
fs.writeFileSync(config, JSON.stringify(cfg, null, 2) + "\n");
EOF
  ok "Claude Desktop configured: $CONFIG"
  CONFIGURED="${CONFIGURED:+$CONFIGURED and }Claude Desktop"

  # Pre-download the bridge so Claude Desktop's first launch isn't slow.
  say "Pre-downloading the mcp-remote bridge (one-time)..."
  npx -y mcp-remote --help >/dev/null 2>&1 || true
fi

# --- Done ----------------------------------------------------------------------
echo
ok "Setup complete — configured: $CONFIGURED"
echo
echo "Next steps:"
case "$CONFIGURED" in *Desktop*) cat <<'EON'
  1. FULLY quit Claude Desktop (menu bar / system tray -> Quit), then reopen it.
  2. In a new chat, click the tools (sliders) icon under the message box —
     you should see "easybdd" listed.
  3. Try asking: "Using the easybdd tools, list the available tests."
EON
esac
case "$CONFIGURED" in *Code*) cat <<'EON'
  Claude Code: run 'claude mcp list' — easybdd should show as connected.
EON
esac
