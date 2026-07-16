#!/usr/bin/env bash
# Easy BDD MCP — one-command setup for macOS and Linux.
#
# Engineers run:
#   curl -fsSL http://192.168.100.100:8092/setup | bash
#
# What it does:
#   1. Checks the Easy BDD MCP server is reachable.
#   2. Configures Claude Code (if installed) — native HTTP, no extras needed.
#   3. Configures Claude Desktop (if installed) via the mcp-remote bridge,
#      installing Node.js first when possible.
# It never removes existing MCP servers from your config; it only adds/updates
# the "easybdd" entry. A timestamped backup of your config is made first.

set -u

MCP_URL="${EASYBDD_MCP_URL:-http://192.168.100.100:8092/mcp}"
OS="$(uname -s)"
CONFIGURED=""

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ✓ \033[0m%s\n' "$*"; }
warn() { printf '\033[1;33m ! \033[0m%s\n' "$*"; }
fail() { printf '\033[1;31m ✗ %s\033[0m\n' "$*"; }

say "Easy BDD MCP setup (server: $MCP_URL)"

# --- 1. Reachability -------------------------------------------------------
if curl -s -o /dev/null -m 8 "$MCP_URL"; then
  ok "Server is reachable."
else
  fail "Cannot reach $MCP_URL"
  echo "   Make sure you are on the office network or VPN, then run this again."
  exit 1
fi

# --- 2. Claude Code (CLI / IDE) --------------------------------------------
if command -v claude >/dev/null 2>&1; then
  claude mcp remove --scope user easybdd >/dev/null 2>&1 || true
  if claude mcp add --scope user --transport http easybdd "$MCP_URL" >/dev/null 2>&1; then
    ok "Claude Code configured (user scope)."
    CONFIGURED="Claude Code"
  else
    warn "Claude Code is installed but 'claude mcp add' failed — configure it manually later."
  fi
fi

# --- 3. Claude Desktop ------------------------------------------------------
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

  node - "$CONFIG" "$MCP_URL" <<'EOF'
const fs = require("fs");
const [config, url] = process.argv.slice(2);
let cfg = {};
try { cfg = JSON.parse(fs.readFileSync(config, "utf8")); } catch (e) {}
if (typeof cfg !== "object" || cfg === null || Array.isArray(cfg)) cfg = {};
cfg.mcpServers = cfg.mcpServers || {};
cfg.mcpServers.easybdd = {
  command: "npx",
  args: ["-y", "mcp-remote", url, "--allow-http", "--transport", "http-only"],
};
fs.writeFileSync(config, JSON.stringify(cfg, null, 2) + "\n");
EOF
  ok "Claude Desktop configured: $CONFIG"
  CONFIGURED="${CONFIGURED:+$CONFIGURED and }Claude Desktop"

  # Pre-download the bridge so Claude Desktop's first launch isn't slow.
  say "Pre-downloading the mcp-remote bridge (one-time)..."
  npx -y mcp-remote --help >/dev/null 2>&1 || true
fi

# --- Done -------------------------------------------------------------------
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
