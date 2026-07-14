# Project instructions for Claude

## Branch workflow (192.168.100.100)

When working in this repo on `192.168.100.100`, always commit changes to the
`stage` branch first (`git checkout stage`, creating it from `origin/stage`
if needed). Only merge/push to `origin main` after the user explicitly
confirms the change has been tested and works on `stage`.

## Test builder UI

`frontend/testrail_builder.py` (started via `frontend/start_testrail_builder.py`,
port 8091) is the current, non-deprecated web UI test builder — it pushes
cases directly into TestRail via `TestRailService`. Do not confuse it with
`frontend/test_builder_app.py` / `start_builder.py`, which is an older,
deprecated app with only copy-paste YAML export and no real TestRail push.

- Runs persistently on `192.168.100.100` as systemd unit
  `easybdd-testrail-builder.service`, from
  `/var/lib/jenkins/workspace/EASY_BDD/frontend`, enabled at boot,
  auto-restarts on failure. Reachable at `http://192.168.100.100:8091`.
- After pulling new code into that checkout, run
  `sudo systemctl restart easybdd-testrail-builder` to pick it up.
- See `ONBOARDING.md` "Production instance" section for more detail.

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
