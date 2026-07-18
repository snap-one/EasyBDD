# Self-hosted Jira and Confluence MCP servers (mcp-atlassian)

This is the server-side companion to the `jira` and `confluence` MCP entries
that the [onboarding one-liner](../ONBOARDING.md) configures for engineers.
It covers how the two [mcp-atlassian](https://github.com/sooperset/mcp-atlassian)
instances are deployed on `192.168.100.100`, how credentials flow, and how to
operate them. Engineers connecting a client don't need this page — the setup
script does everything; see [ONBOARDING.md](../ONBOARDING.md).

> **Security note:** this repo is public. Never commit a real Atlassian site
> URL, account email, or API token — use placeholders (`<your-site>`,
> `<atlassian_email>`, `<api_token>`) in anything that goes into git. Real
> values live only in the production `.env` on the server.

---

## How it fits together

Two **separate** mcp-atlassian containers run on the box — one serving Jira
tools, one serving Confluence tools. mcp-atlassian can serve both from a
single process, but they are deliberately split so each can be enabled,
disabled, upgraded, or pointed at a different host independently.

| MCP entry | Container | Host port | Endpoint | Site env var (in container) |
|-----------|-----------|-----------|----------|------------------------------|
| `jira` | `mcp-jira` | 9001 | `http://192.168.100.100:9001/mcp` | `JIRA_URL` |
| `confluence` | `mcp-confluence` | 9002 | `http://192.168.100.100:9002/mcp` | `CONFLUENCE_URL` |

Credential flow — no Atlassian token ever lands on an engineer's machine by
hand, and none is baked into the containers:

1. The containers run in mcp-atlassian's **multi-user mode**: they are started
   with only the Atlassian site URL and expect credentials per request via an
   `Authorization: Basic base64(email:api_token)` header.
2. The Atlassian account email and API token live in the production `.env` of
   the Easy BDD MCP server (`JIRA_USERNAME` / `JIRA_API_TOKEN`,
   `CONFLUENCE_USERNAME` / `CONFLUENCE_API_TOKEN`).
3. The token-gated `/jira-mcp-config` and `/confluence-mcp-config` routes on
   the Easy BDD server (`easybdd/mcp_server.py`) hand out the endpoint URL
   plus a ready-made `Authorization` header to the onboarding scripts, which
   write it into each engineer's Claude Code / Claude Desktop config. This
   mirrors the existing Jenkins MCP pattern
   ([github-jenkins-mcp-setup.md](./github-jenkins-mcp-setup.md)).

---

## Server deployment (admin)

Both instances run as plain Docker containers on `192.168.100.100` — no
systemd units (unlike `floci.service` / `easy-bdd-mcp.service`);
`--restart unless-stopped` brings them back after a reboot as long as the
Docker daemon starts and nobody explicitly stopped them.

```bash
docker run -d --name mcp-jira --restart unless-stopped -p 9001:9000 \
  -e JIRA_URL=https://<your-site>.atlassian.net \
  ghcr.io/sooperset/mcp-atlassian:latest --transport streamable-http --port 9000

docker run -d --name mcp-confluence --restart unless-stopped -p 9002:9000 \
  -e CONFLUENCE_URL=https://<your-site>.atlassian.net/wiki \
  ghcr.io/sooperset/mcp-atlassian:latest --transport streamable-http --port 9000
```

Notes:

- Inside each container mcp-atlassian listens on port 9000; the host port
  mapping (`9001:9000` / `9002:9000`) is what distinguishes the two.
- Only the site URL is passed in. Because no `JIRA_API_TOKEN` /
  `CONFLUENCE_API_TOKEN` is set on the container, mcp-atlassian requires the
  per-request Basic auth header — which the hand-out routes supply.
- If the box has a host firewall, ports 9001 and 9002 must be reachable from
  the engineering network, same as 8092.

### Wiring the hand-out routes

In the production `.env` used by `easy-bdd-mcp.service`
(`/home/jenkins/EasyBDD/.env`), set:

```bash
JIRA_MCP_URL=http://192.168.100.100:9001/mcp
JIRA_USERNAME=<atlassian_email>
JIRA_API_TOKEN=<api_token>

CONFLUENCE_MCP_URL=http://192.168.100.100:9002/mcp
CONFLUENCE_USERNAME=<atlassian_email>
CONFLUENCE_API_TOKEN=<api_token>
```

then `sudo systemctl restart easy-bdd-mcp`. The API token is an Atlassian
Cloud API token (create at **id.atlassian.com → Security → API tokens**) for
an account with the Jira/Confluence access you want assistants to have.

Each trio is independent: if the three `JIRA_*` values aren't all set,
`/jira-mcp-config` returns 404 and the onboarding scripts quietly skip the
`jira` entry (same for `CONFLUENCE_*`), and the `/onboard` page shows the
integration as "not enabled".

---

## Client setup (engineers)

Nothing manual — the [onboarding one-liner](../ONBOARDING.md) fetches the
config from the hand-out routes and adds the `jira` and `confluence` servers
to Claude Code and Claude Desktop automatically, alongside `easybdd` and
`jenkins`.

For a hand-rolled setup (e.g. another MCP client), the shape is the same as
the Jenkins entry in
[github-jenkins-mcp-setup.md](./github-jenkins-mcp-setup.md):

```bash
claude mcp add --scope user --transport http jira http://192.168.100.100:9001/mcp \
  --header "Authorization: Basic $(echo -n '<atlassian_email>:<api_token>' | base64)"
```

---

## Operations

**Verify from anywhere on the network** — a bare GET returns HTTP 406 with an
`mcp-session-id` header when the server is healthy (406 is the streamable-HTTP
MCP server rejecting a non-MCP request, which is expected):

```bash
curl -sS -D - -o /dev/null http://192.168.100.100:9001/mcp
curl -sS -D - -o /dev/null http://192.168.100.100:9002/mcp
```

Connection refused instead means the container isn't running.

**On the box:**

```bash
docker ps --filter name=mcp-           # both containers should be Up
docker logs --tail 50 mcp-jira         # startup + per-request logs
docker restart mcp-jira                # bounce one instance

# Upgrade to the latest mcp-atlassian
docker pull ghcr.io/sooperset/mcp-atlassian:latest
docker rm -f mcp-jira mcp-confluence
# ...then re-run the two `docker run` commands above
```

**Disable an integration:** stop/remove its container and unset its three
variables in the production `.env` (then restart `easy-bdd-mcp`) so the
hand-out route 404s and onboarding skips it again.

**Troubleshooting:**

- `claude mcp list` shows `Failed to connect` → the container is down or the
  port is blocked; run the curl checks above. This exact symptom occurs when
  the `.env` hand-out is configured but the containers were never started.
- Tools connect but Jira/Confluence calls fail with 401/403 → the API token
  in the production `.env` is wrong, expired, or the account lacks access;
  fix the `.env`, restart `easy-bdd-mcp`, and have affected engineers re-run
  the onboarding one-liner to pick up the new header.
