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

## Local (TestRail-free) test builder UI

`frontend/local_builder.py` (started via `frontend/start_local_builder.py`,
port 9093) is a filesystem-backed sibling of the TestRail builder — same
case/step model and UI (`frontend/static/testrail_builder.html` serves both;
it detects which backend it's talking to via `/api/local/status` vs
`/api/testrail/status`), but cases/shared-steps/vars are stored as plain YAML
under `tests/cases/` instead of pushed to TestRail. No TestRail credentials
required. Shared logic between the two builders lives in
`frontend/builder_core.py` — don't duplicate case-model/serialization/
validation code into either app; extend `builder_core.py` and import from
both. Persisted run history lives in `frontend/local_runner.py` and
`reports/local_runs/*.json`; the TestRail-import feature
(`/api/local/import/testrail*`) uses `TestRailService` only as a one-shot
data source, never at test-run time.

- Intended to run persistently on `192.168.100.100` as systemd unit
  `easybdd-local-builder.service`, from `/home/jenkins/EasyBDD/frontend`,
  same shape as `easybdd-testrail-builder.service`. Reachable at
  `http://192.168.100.100:9093`. **First-time setup is manual** (no SSH
  access from automated deploys to create a brand-new unit file) — see the
  unit file content in the PR/commit that introduced this section, or ask
  for it again; once the unit exists, push-to-main restarts it automatically
  like every other service (the root `Jenkinsfile`'s "Restart services"
  stage already includes it).
- Port map on `192.168.100.100`: 8080 Jenkins, 8091 TestRail builder, **9093
  local builder**, 8092 easy-bdd-mcp, 4566 Floci, 9001/9002 Jira/Confluence
  MCP, 8765 crawler, 11434 Ollama.
