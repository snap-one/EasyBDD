#!/bin/bash
# Easy BDD MCP Server — run on 192.168.100.191
# Starts the MCP server in SSE/HTTP mode so Claude Desktop can connect remotely.
#
# Usage:
#   ./start_mcp_server.sh          # foreground
#   ./start_mcp_server.sh --daemon  # background (logs to mcp_server.log)

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

HOST="0.0.0.0"
PORT="8080"
LOG="$SCRIPT_DIR/mcp_server.log"

# Activate virtualenv if present
if [ -f "$SCRIPT_DIR/env/bin/activate" ]; then
    source "$SCRIPT_DIR/env/bin/activate"
fi

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Kill any existing instance on this port
EXISTING=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$EXISTING" ]; then
    echo "Stopping existing process on port $PORT (PID $EXISTING)..."
    kill -9 $EXISTING 2>/dev/null
    sleep 1
fi

if [ "$1" == "--daemon" ]; then
    echo "Starting Easy BDD MCP server in background..."
    echo "  Endpoint: http://$(hostname -I | awk '{print $1}'):$PORT/sse"
    echo "  Logs: $LOG"
    nohup python -m easy_bdd mcp-serve --sse --host "$HOST" --port "$PORT" \
        >> "$LOG" 2>&1 &
    echo "  PID: $!"
    echo "$!" > "$SCRIPT_DIR/mcp_server.pid"
else
    echo "Starting Easy BDD MCP server (foreground)..."
    echo "  Endpoint: http://$(hostname -I | awk '{print $1}'):$PORT/sse"
    echo "  Press Ctrl+C to stop"
    echo ""
    python -m easy_bdd mcp-serve --sse --host "$HOST" --port "$PORT"
fi
