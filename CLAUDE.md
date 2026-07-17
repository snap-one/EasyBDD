# Project instructions for Claude

## Branch workflow (192.168.100.100)

`main` is the only branch — commit and push directly to `origin main`.
The former `stage` branch was retired in July 2026 to avoid branch mix-ups;
do not recreate it or any other long-lived branch unless the user asks.

Frontend test-builder details live in `frontend/CLAUDE.md` (loads when working
in that directory). Floci (local S3 emulator) details live in the
`floci-ops` skill (loads on demand).
