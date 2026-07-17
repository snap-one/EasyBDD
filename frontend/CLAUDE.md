## Test builder UI

`frontend/testrail_builder.py` (started via `frontend/start_testrail_builder.py`,
port 8091) is the current, non-deprecated web UI test builder — it pushes
cases directly into TestRail via `TestRailService`. Do not confuse it with
`frontend/test_builder_app.py` / `start_builder.py`, which is an older,
deprecated app with only copy-paste YAML export and no real TestRail push.

- Runs persistently on `192.168.100.100` as systemd unit
  `easybdd-testrail-builder.service`, from `/home/jenkins/EasyBDD/frontend`,
  enabled at boot, auto-restarts on failure. Reachable at
  `http://192.168.100.100:8091`.
- Deploy = push to main: the `EasyBDD` Jenkins job pulls into
  `/home/jenkins/EasyBDD` and restarts the service automatically. The old
  `/var/lib/jenkins/workspace/EASYBDD` checkout was decommissioned in July
  2026 (archived as `EASYBDD.decommissioned-*`) — do not reference or
  recreate it.
- See `ONBOARDING.md` "Production instance" section for more detail.
