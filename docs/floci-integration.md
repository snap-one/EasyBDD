# Floci Integration

**Use a local, free AWS-emulated S3 bucket alongside your existing real S3 bucket**

---

## Table of Contents

1. [Overview](#overview)
2. [What Is Floci?](#what-is-floci)
3. [Quick Start](#quick-start)
4. [Available Actions](#available-actions)
5. [Configuration](#configuration)
6. [CLI: `floci-upload`](#cli-floci-upload)
7. [Web UI: Floci Browser](#web-ui-floci-browser)
8. [CI/CD: Mirroring Firmware into Floci](#cicd-mirroring-firmware-into-floci)
9. [Relationship to the AWS/S3 Actions](#relationship-to-the-awss3-actions)
10. [Troubleshooting](#troubleshooting)

---

## Overview

Easy BDD's `floci.*` actions give you the same S3 operations as the existing
`aws.*`/`s3.*` actions (list, get-latest, upload, delete, version-aware
sorting, folder-prefix discovery) — but aimed at a local
[Floci](https://floci.io) instance instead of real AWS.

This is purely additive: nothing about `aws.*`/`s3.*` changes. Use `floci.*`
when you want a fast, free, local S3-compatible bucket — for CI runs that
shouldn't depend on real AWS credentials, for local development, or to mirror
firmware in addition to whatever already lands in your real S3 bucket.

---

## What Is Floci?

[Floci](https://floci.io) is a free, open-source local emulator for AWS
services. It speaks the real AWS wire protocol on a single endpoint (default
`http://localhost:4566`), so the same boto3/AWS CLI calls that hit real AWS
work against it unmodified — no real credentials required.

If Floci is already running on this server (as a Docker container, typically
named `floci`), it's reachable at `http://localhost:4566` and healthy when:

```bash
curl http://localhost:4566/_localstack/health
```

---

## Quick Start

```yaml
steps:
  - floci.upload:
      bucket_name: "wattbox"
      local_file_path: "Firmware/wattbox/upgrade_moip_4.7.0.bin"
      s3_key: "wattbox/upgrade_moip_4.7.0.bin"
      store_as: "uploaded_url"

  - floci.get_latest:
      bucket_name: "wattbox"
      folder_prefix: "wattbox/"
      file_extension: ".bin"
      store_filename_as: "fw_file"
      store_version_as: "fw_version"
      store_url_as: "fw_url"

  - test.assert:
      expression: "fw_version is not None"
      message: "Should extract firmware version"
```

The bucket is created automatically on first use — Floci starts empty on
every fresh container, unlike real S3 where buckets are provisioned out of
band.

---

## Available Actions

Identical parameter sets to their `aws.*` counterparts (see
[AWS S3 Integration](aws-s3-integration.md#available-actions) for full
parameter tables) — only the action prefix changes:

| Action | Legacy alias | Equivalent AWS action |
|---|---|---|
| `floci.list_files` | `floci list firmware files` | `aws.list_files` |
| `floci.get_latest` | `floci get latest firmware` | `aws.get_latest` |
| `floci.upload` | — | `aws.upload` |
| `floci.delete_folder` | — | `aws.delete_folder` |

Because a test's `bucket_name`/`folder_prefix` values usually mirror the real
S3 layout, switching a test between real S3 and Floci is normally just
swapping the action prefix (`aws.` → `floci.`), with everything else —
including `discover_prefix`, `specific_version`, `download_dir`, version
sorting — working the same way.

---

## Configuration

Floci needs no real AWS credentials. In priority order, the endpoint
resolves as:

1. `endpoint_url` passed to `FlociService(...)` (used internally by the
   `floci-upload` CLI's `--endpoint-url` flag)
2. `FlociService.configure_global_credentials(endpoint_url=...)`
3. `FLOCI_ENDPOINT_URL` environment variable
4. Default: `http://localhost:4566`

Credentials resolve the same way, falling back to the dummy identity
`test`/`test` (env vars `FLOCI_ACCESS_KEY_ID` / `FLOCI_SECRET_ACCESS_KEY` if
you need something else — Floci doesn't validate them either way).

```yaml
variables:
  floci_access_key_id: "test"
  floci_secret_access_key: "test"

steps:
  - floci.list_files:
      bucket_name: "wattbox"
      folder_prefix: "wattbox/"
```

---

## CLI: `floci-upload`

For scripting/CI use outside of a YAML test (see the Jenkins stage below),
upload one or more local files directly:

```bash
python -m easybdd floci-upload <bucket_name> <file_path>... [options]
```

| Flag | Description |
|---|---|
| `--key-prefix PREFIX` | Prefix prepended to each object key |
| `--flatten` | Use just the file's basename as the key (drop directory structure) |
| `--endpoint-url URL` | Floci endpoint (default: `$FLOCI_ENDPOINT_URL` or `http://localhost:4566`) |
| `--region REGION` | Region passed to boto3 (default: `us-east-1`; Floci doesn't validate it) |

```bash
# Mirror a firmware file, preserving its relative path as the object key
python -m easybdd floci-upload wattbox wattbox/upgrade_moip_4.7.0.bin

# Mirror several files at once, dropping directory structure
python -m easybdd floci-upload wattbox wattbox/a.bin wattbox/b.bin --flatten
```

Run `python -m easybdd floci-upload ?` for full contextual help.

---

## CLI: `floci-delete`

Removes object(s) from a Floci bucket by the same repo-relative path
`floci-upload` would key them under — the path does **not** need to exist on
disk, so this works for files already deleted/renamed away in git:

```bash
python -m easybdd floci-delete <bucket_name> <path>... [options]
```

| Flag | Description |
|---|---|
| `--key-prefix PREFIX` | Prefix prepended to each key — must match what was passed to `floci-upload` for the same file |
| `--flatten` | Use just the basename as the key — must match `--flatten` used at upload time |
| `--endpoint-url URL` | Floci endpoint (default: `$FLOCI_ENDPOINT_URL` or `http://localhost:4566`) |
| `--region REGION` | Region passed to boto3 (default: `us-east-1`; Floci doesn't validate it) |

```bash
# Remove a firmware file that no longer exists in the repo
python -m easybdd floci-delete wattbox wattbox/upgrade_moip_4.7.0.bin
```

Deleting a key that isn't present in the bucket is not an error (matches S3
delete semantics). Run `python -m easybdd floci-delete ?` for full contextual
help.

---

## Web UI: Floci Browser

An S3-console-style web UI for browsing Floci bucket contents —
`frontend/floci_browser.py`, served as a single self-contained page (same
FastAPI + vanilla-JS pattern as the TestRail Test Builder).

What it does:

- **Bucket sidebar** — every bucket on the endpoint, with creation dates.
- **Folder navigation** — breadcrumb + one-level prefix listing
  (`Delimiter='/'`), sortable by name / size / last-modified, with a filter
  box and paged "Load more" for large folders.
- **Object preview** — click any object for metadata (size, last modified,
  content type, ETag, direct Floci object URL) plus inline previews of text
  files and images.
- **Download / upload** — stream any object down, or upload files into the
  current folder.
- **Delete** — single objects or whole folders (recursive), always behind a
  confirmation dialog.

Run it locally:

```bash
python frontend/start_floci_browser.py            # http://localhost:8092
python frontend/start_floci_browser.py --port 9000
```

The endpoint is resolved exactly like `FlociService` resolves it:
`FLOCI_ENDPOINT_URL` in the environment or project `.env`, defaulting to
`http://localhost:4566`. Point it at a remote Floci with e.g.
`FLOCI_ENDPOINT_URL=http://192.168.100.100:4566`. Port default is `8092`
(`FLOCI_BROWSER_PORT` env var) — 8090 is the MCP server, 8091 the TestRail
builder.

### Production instance

The browser runs persistently on the Floci host as the
`easybdd-floci-browser` systemd service — open **http://192.168.100.100:8092**.
To install (or refresh) the service on the server:

```bash
sudo bash scripts/install_floci_browser_service.sh
```

The script writes `/etc/systemd/system/easybdd-floci-browser.service`
(runs as `jenkins` from the repo checkout, after `floci.service`, enabled at
boot, auto-restarts), reusing the same python interpreter as the
`easybdd-testrail-builder` service. After pulling new code:

```bash
sudo systemctl restart easybdd-floci-browser
```

---

## CI/CD: Mirroring Firmware into Floci

[Jenkinsfile.firmware-wattbox](../Jenkinsfile.firmware-wattbox) already
detects which `.bin` firmware files changed in a firmware-repo commit (to
create targeted TestRail runs). A **"Mirror Firmware to Floci"** stage runs
right after detection and splits those changed files into two groups:

- Files still present on disk are pushed into Floci via `floci-upload`,
  preserving each file's relative repo path as its object key so the Floci
  bucket's layout matches the real S3 bucket's layout.
- Files no longer present on disk (deleted, or renamed away — `git diff
  --name-only` lists both the old and new path for a rename) are removed
  from Floci via `floci-delete`, using that same repo-relative path as the
  key, so Floci doesn't accumulate stale firmware the repo no longer has.

This stage is independent of both the real S3 upload path and TestRail run
creation — it runs whenever there are changed `.bin` files in the commit,
regardless of whether any of them matched a known firmware type.

Configure the target bucket and endpoint via the `environment` block:

```groovy
environment {
    FLOCI_BUCKET       = 'wattbox'   // match your real S3 bucket name
    FLOCI_ENDPOINT_URL = 'http://localhost:4566'
}
```

To adapt this pattern for another firmware repo/Jenkinsfile, copy the
"Mirror Firmware to Floci" stage and point `FLOCI_BUCKET` at that product's
bucket name.

---

## Relationship to the AWS/S3 Actions

- **Real S3 is untouched.** `aws.*`/`s3.*` actions, credentials resolution,
  and URL formats are exactly as they were — Floci support was added as a
  new, separate service (`FlociService`) and action prefix (`floci.*`), not
  a modification of the AWS path.
- **Independent buckets.** Uploading to Floci does not read from or write to
  the real S3 bucket, and vice versa. There's no sync/coupling between them.
- **Same underlying logic.** Both share the S3 operation implementations in
  [`aws_service.py`](../easybdd/services/aws_service.py) —
  [`floci_service.py`](../easybdd/services/floci_service.py) only overrides
  *where* boto3 connects (endpoint) and *what* identity it uses
  (dummy credentials, auto-created bucket), plus how object URLs are built
  (Floci returns a real, resolvable `http://<endpoint>/<bucket>/<key>` URL
  instead of a `*.s3.amazonaws.com` host that wouldn't work against a local
  emulator).

---

## Troubleshooting

### Connection refused / timeout

```
Error: Could not connect to the endpoint URL: "http://localhost:4566/..."
```

**Solution:** Confirm Floci is running:

```bash
docker ps --filter name=floci
curl http://localhost:4566/_localstack/health
```

### Bucket not found

Floci starts empty — `floci.upload` auto-creates the bucket, but
`floci.list_files` / `floci.get_latest` against a bucket that's never been
written to will simply return no results (matching real S3 behavior against
an empty/non-existent prefix), not an error.

### Wrong endpoint in a multi-host setup

If Floci runs somewhere other than the test/CI host, either set
`FLOCI_ENDPOINT_URL` in the environment, or pass `--endpoint-url` to
`floci-upload` / call
`FlociService.configure_global_credentials(endpoint_url=...)` before running
YAML tests.

---

## Next Steps

- [AWS S3 Integration](aws-s3-integration.md) — full parameter reference (shared by Floci)
- [CI/CD Integration](ci-cd-integration.md) — how firmware detection and TestRail runs are wired together
