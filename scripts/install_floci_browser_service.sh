#!/usr/bin/env bash
# Install (or refresh) the easybdd-floci-browser systemd service.
#
# Run on the server hosting Floci (e.g. 192.168.100.100), from the repo root:
#   sudo bash scripts/install_floci_browser_service.sh
#
# Overrides (env vars): FLOCI_BROWSER_PORT (default 8092),
# FLOCI_BROWSER_USER (default jenkins), FLOCI_BROWSER_PYTHON (default: the
# python the easybdd-testrail-builder service uses, else `command -v python3`).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FLOCI_BROWSER_PORT:-8092}"
RUN_USER="${FLOCI_BROWSER_USER:-jenkins}"
UNIT_PATH=/etc/systemd/system/easybdd-floci-browser.service

# Reuse whatever python the testrail-builder service runs with — its
# FastAPI/uvicorn/boto3 environment is known-good for the frontend apps.
PYTHON="${FLOCI_BROWSER_PYTHON:-}"
if [ -z "$PYTHON" ] && [ -f /etc/systemd/system/easybdd-testrail-builder.service ]; then
  PYTHON="$(sed -n 's/^ExecStart=\([^ ]*\).*/\1/p' /etc/systemd/system/easybdd-testrail-builder.service | head -1)"
fi
PYTHON="${PYTHON:-$(command -v python3)}"

echo "Installing ${UNIT_PATH}"
echo "  repo:   ${REPO_ROOT}"
echo "  python: ${PYTHON}"
echo "  user:   ${RUN_USER}, port: ${PORT}"

cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=Easy BDD Floci Browser (web UI for the local Floci S3 emulator)
After=network.target floci.service

[Service]
Type=simple
User=${RUN_USER}
WorkingDirectory=${REPO_ROOT}
EnvironmentFile=-${REPO_ROOT}/.env
ExecStart=${PYTHON} ${REPO_ROOT}/frontend/start_floci_browser.py --port ${PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now easybdd-floci-browser.service
systemctl --no-pager --full status easybdd-floci-browser.service
