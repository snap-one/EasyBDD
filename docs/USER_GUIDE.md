# Easy BDD — Quick Start for TestRail Authors

This guide gets you from zero to running tests in TestRail. For complete reference, see [testrail-integration.md](./testrail-integration.md).

---

## 1. How tests work

Tests live in TestRail. Each case has a prefix that tells the runner what to do with it:

| Prefix | Role | When it runs |
|--------|------|-------------|
| `Var: Name` | Suite variables | Always — loaded first |
| `Setup: Name` | Pre-test setup | Before each pending Feature: case |
| `Feature: Name` | Inline test steps | When Untested or Retest |
| `Shared: Name` | Reusable step block | Referenced by other cases |
| `Teardown: Name` | Post-test cleanup | After all Feature: cases |

---

## 2. Write variables (`Var:` case)

Put suite-level variables in the **Preconditions** field of a `Var:` case:

```
url: http://192.168.1.100:8001/api
username: admin
password: secret
login_path: /system/login
login_json: {'user': '${username}', 'password': '${password}'}
token_path: restful_res.token
mac_for_report: AA:BB:CC:DD:EE:FF
```

---

## 3. Write a test (`Feature:` case)

Put steps in the **Preconditions** field. Parameters can be flush-left — the runner re-indents them automatically:

```
- websocket.send:
method: dxGetAbout
url: '${url}'
store_as: last_response
- test.assert:
expression: "'error' not in str(last_response)"
```

---

## 4. Auto-authentication

Set `login_path`, `login_json`, and `token_path` in your `Var:` case (see above) and the runner handles token acquisition and injection automatically. No login step needed in each Feature: case.

See [api-authentication.md](./api-authentication.md) for full details.

---

## 5. Run from Jenkins

Trigger the `EASY_BDD_CUSTOM_RUN` job, select project/suite, and Jenkins picks up the active TestRail run. Results are posted back to TestRail and an HTML report is attached.

See [ci-cd-integration.md](./ci-cd-integration.md) for pipeline setup.

---

## 6. Key references

- **[testrail-integration.md](./testrail-integration.md)** — complete TestRail authoring guide
- **[SYNTAX_CHEATSHEET.md](./SYNTAX_CHEATSHEET.md)** — all action syntax at a glance
- **[actions.md](./actions.md)** — full action reference (API, SSH, telnet, WoL, WebSocket, S3, browser)
- **[troubleshooting.md](./troubleshooting.md)** — when things go wrong
- **[runner-param-patterns.md](./runner-param-patterns.md)** — known parameter bugs to avoid
