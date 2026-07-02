# Easy BDD — Documentation Index

Easy BDD is a YAML-based test framework that runs test cases authored directly in **TestRail**. Tests are defined as `Feature:`, `Shared:`, `Var:`, `Setup:`, and `Teardown:` cases in TestRail, then executed against real devices via Jenkins or the CLI.

---

## Start here

| Doc | What it covers |
|-----|----------------|
| [testrail-integration.md](./testrail-integration.md) | **Core reference.** Case taxonomy, variable injection, auto-auth, data-driven tests, Setup:/Teardown:, scheduling, HTML reports |
| [writing-test-cases.md](./writing-test-cases.md) | Writing steps in TestRail — syntax rules, flush-left YAML, common pitfalls |
| [testrail-templates.md](./testrail-templates.md) | Copy-paste Var:/Shared:/Feature: templates for common workflows — telnet/SSH validation, WebSocket API calls, firmware upgrade orchestration, fault-injection and data-driven loops |
| [SYNTAX_CHEATSHEET.md](./SYNTAX_CHEATSHEET.md) | Quick lookup for all action syntax |
| [troubleshooting.md](./troubleshooting.md) | Common errors and fixes |

---

## Actions and protocols

| Doc | What it covers |
|-----|----------------|
| [actions.md](./actions.md) | All actions: browser, API, SSH, telnet, WoL, LGIP, WebSocket |
| [assertions.md](./assertions.md) | `test.assert`, schema validation, soft assertions |
| [api-authentication.md](./api-authentication.md) | Auto-auth via `login_json`/`token_path`, bearer/basic/API key/OAuth2 |
| [aws-s3-integration.md](./aws-s3-integration.md) | S3 file listing, firmware download, CloudFront URLs |
| [telnet.md](./telnet.md) | `telnet.send` for network devices |
| [ssh-lgip.md](./ssh-lgip.md) | Stateful SSH sessions, LGIP IR control |
| [jsonrpc-websocket.md](./jsonrpc-websocket.md) | JSON-RPC over WebSocket |
| [ovrc-websocket.md](./ovrc-websocket.md) | OvrC-specific WebSocket actions |
| [flexible-success-codes.md](./flexible-success-codes.md) | Custom HTTP success codes for non-standard APIs |

---

## Test authoring patterns

| Doc | What it covers |
|-----|----------------|
| [syntax.md](./syntax.md) | YAML structure, variables, step format |
| [data-driven.md](./data-driven.md) | Data arrays, parameterized tests, iteration |
| [conditional-steps.md](./conditional-steps.md) | `condition:`/`then:`/`else:` logic |
| [soft-assertions.md](./soft-assertions.md) | Collect multiple failures before failing |
| [dot-notation-actions.md](./dot-notation-actions.md) | Action naming conventions (`service.action`) |
| [runner-param-patterns.md](./runner-param-patterns.md) | Known parameter bugs and workarounds |
| [examples.md](./examples.md) | Real test case examples |
| [advanced.md](./advanced.md) | Async execution, retry, setup/cleanup phases |
| [LONG_RUNNING_TESTS.md](./LONG_RUNNING_TESTS.md) | Timeout handling, polling patterns |

---

## Configuration and CI/CD

| Doc | What it covers |
|-----|----------------|
| [ci-cd-integration.md](./ci-cd-integration.md) | Jenkins pipelines, GitHub Actions, TestRail run creation |
| [setup.md](./setup.md) | Installation, environment setup, framework config |
| [CENTRALIZED_VARIABLES.md](./CENTRALIZED_VARIABLES.md) | Variable scopes and resolution order |
| [DEVICE_AGNOSTIC_SETUP.md](./DEVICE_AGNOSTIC_SETUP.md) | Multi-device configs, parameterized device testing |
| [automatic-time-tracking.md](./automatic-time-tracking.md) | Datalake metrics posting |
| [datalake-logger.md](./datalake-logger.md) | Teams notifications, error hints |

---

## Browser testing (secondary)

| Doc | What it covers |
|-----|----------------|
| [BROWSER_CONFIG.md](./BROWSER_CONFIG.md) | Headless mode, viewport, launch args |
| [PLAYWRIGHT_API_INTEGRATION.md](./PLAYWRIGHT_API_INTEGRATION.md) | Playwright selectors, role-based locators |
| [MODERN_FRONTEND_SUCCESS.md](./MODERN_FRONTEND_SUCCESS.md) | Dynamic content, shadow DOM |
