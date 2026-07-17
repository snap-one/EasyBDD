---
name: floci-ops
description: Reference for the Floci local S3 emulator on 192.168.100.100 — its systemd service, storage layout, troubleshooting, and how to browse buckets. Use when working with Floci, floci_service.py, S3 data on the Jenkins box, or when asked to browse/inspect Floci buckets.
---

## Floci (local S3 emulator)

Floci (`/usr/local/bin/floci` CLI wrapping the `floci/floci:latest` Docker
container; see `docs/floci-integration.md` and
`easybdd/services/floci_service.py`) runs on `192.168.100.100`.

- Auto-starts on boot via systemd unit `floci.service` (runs as user
  `jenkins`, `After=docker.service`). It's `Type=oneshot` +
  `RemainAfterExit=yes` with `ExecStart=floci start --persist=/data/floci
  --detach` / `ExecStop=floci stop` — deliberately **no** `Restart=`
  directive, since `floci start` errors if the container is already running,
  which would otherwise cause a restart loop.
- Persistent storage lives at `/data/floci` (bind-mounted, disk-backed —
  not the ephemeral in-memory mode). Data sits under
  `/data/floci/s3/<bucket>/...`.
- If Floci data looks missing or the container isn't up after a reboot,
  check `systemctl status floci.service` and `floci doctor` first.

## Browsing Floci buckets

Use Floci's **built-in web console**, served by the emulator itself:
`http://192.168.100.100:4566/_floci/ui` (locally
`http://localhost:4566/_floci/ui`). There is no separate service to manage.
The in-repo "Floci Browser" web UI (`frontend/floci_browser.py`, port 8092,
`easybdd-floci-browser.service`) was retired in July 2026 — do not recreate
or reference it.

- Port map on `192.168.100.100`: 8091 TestRail builder, 8092 Easy BDD MCP
  server (`easy-bdd-mcp.service`, runs from `/home/jenkins/EasyBDD` — its
  systemd unit does `git pull --ff-only` on start, so deploy = push to main
  + `sudo systemctl restart easy-bdd-mcp`), 4566 Floci (S3 endpoint +
  built-in UI).
- The MCP server also serves engineer self-setup over plain HTTP:
  `http://192.168.100.100:8092/onboard` (instructions page), `/setup`
  (macOS/Linux bash installer), `/setup.ps1` (Windows PowerShell installer).
  Script sources: `onboarding/` in this repo.
- MCP auth: `/mcp` requires `Authorization: Bearer $EASYBDD_MCP_TOKEN`
  (token lives in the production `.env`, never in git; the three setup
  routes above stay public). Tool file access is confined to the project
  root, excluding `.env*`, `env/`, `.git/` (`_abs()` in
  `easybdd/mcp_server.py`). Engineers get the token from Mark Fomin and
  pass it as `EASYBDD_TOKEN` when running the setup one-liner.
