#!/bin/bash
# Easy BDD Server Restart Script
# Stops any running server instances and starts a fresh one

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔄 Easy BDD Server Restart Script"
echo "=================================="
echo ""

# Get the project root directory (where this script is located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Step 1: Find and stop running server processes
echo -e "${YELLOW}Step 1: Stopping existing server processes...${NC}"

# Find processes using port 8000
PIDS=$(lsof -ti:8000 2>/dev/null || true)

if [ -z "$PIDS" ]; then
    echo -e "${GREEN}✓ No server processes found on port 8000${NC}"
else
    echo -e "${YELLOW}Found processes on port 8000: $PIDS${NC}"
    
    # Also find start_builder.py processes
    BUILDER_PIDS=$(ps aux | grep "[p]ython.*start_builder.py" | awk '{print $2}' || true)
    
    if [ ! -z "$BUILDER_PIDS" ]; then
        echo -e "${YELLOW}Found start_builder.py processes: $BUILDER_PIDS${NC}"
        PIDS="$PIDS $BUILDER_PIDS"
    fi
    
    # Kill all found processes
    for PID in $PIDS; do
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}  Stopping process $PID...${NC}"
            kill "$PID" 2>/dev/null || true
        fi
    done
    
    # Wait a moment for processes to stop
    sleep 2
    
    # Force kill if still running
    for PID in $PIDS; do
        if kill -0 "$PID" 2>/dev/null; then
            echo -e "${YELLOW}  Force stopping process $PID...${NC}"
            kill -9 "$PID" 2>/dev/null || true
        fi
    done
    
    # Wait a bit more
    sleep 1
    
    echo -e "${GREEN}✓ Server processes stopped${NC}"
fi

echo ""

# Step 2: Verify port is free
echo -e "${YELLOW}Step 2: Verifying port 8000 is available...${NC}"
if lsof -ti:8000 >/dev/null 2>&1; then
    echo -e "${RED}⚠ Warning: Port 8000 is still in use. You may need to manually stop processes.${NC}"
else
    echo -e "${GREEN}✓ Port 8000 is available${NC}"
fi

echo ""

# Step 3: Start the server
echo -e "${YELLOW}Step 3: Starting server...${NC}"
echo -e "${GREEN}📍 Server will be available at: http://localhost:8000${NC}"
echo -e "${GREEN}📚 API docs will be at: http://localhost:8000/docs${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Start the server
cd frontend
python3 start_builder.py

