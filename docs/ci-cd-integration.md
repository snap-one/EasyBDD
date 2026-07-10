# CI/CD Integration Guide

How to wire Easy BDD into GitHub Actions and Jenkins so that test runs are created automatically on push or firmware detection and executed by Jenkins.

---

## Table of Contents

1. [Overview — How the Pipeline Works](#overview)
2. [GitHub Action: Auto-create Smoke Run on Push](#github-action)
3. [Setting Up GitHub Secrets](#github-secrets)
4. [Jenkinsfile.firmware-wattbox — Firmware-triggered Runs](#jenkinsfilefirmware-wattbox)
5. [Jenkinsfile.create-smoke-run — Jenkins Polling Fallback](#jenkinsfilecreate-smoke-run)
6. [Full Pipeline Walkthrough](#full-pipeline-walkthrough)

---

## Overview

The general pattern:

1. **A trigger event** (git push, firmware upload, scheduled cron) calls `testrail-create-run` to create one or more TestRail runs.
2. **Jenkins** polls TestRail (or is triggered via webhook) and calls `testrail-run` to execute whichever runs have pending tests.
3. Results, HTML reports, and Teams notifications are produced automatically.

This decouples *run creation* from *run execution* — runs can be created by GitHub Actions even if Jenkins is not running, and Jenkins will pick them up on its next poll cycle.

---

## GitHub Action: Auto-create Smoke Run on Push

File: `.github/workflows/create-smoke-run.yml`

This workflow triggers on every push to any branch. It installs Easy BDD, then calls `testrail-create-run` with commit metadata in the description so the TestRail run is traceable back to the exact commit.

```yaml
name: Create Smoke Run on Push

on:
  push:
    branches: ["**"]

jobs:
  create-smoke-run:
    runs-on: ubuntu-latest

    steps:
      - name: Check out code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install Easy BDD
        run: pip install -e .

      - name: Create TestRail smoke run
        env:
          TESTRAIL_URL: ${{ secrets.TESTRAIL_URL }}
          TESTRAIL_USERNAME: ${{ secrets.TESTRAIL_USERNAME }}
          TESTRAIL_API_KEY: ${{ secrets.TESTRAIL_API_KEY }}
        run: |
          python -m easybdd testrail-create-run 59 106662 \
            --given-section "VPS" \
            --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API" \
            --description "Branch: ${{ github.ref_name }}
          Commit: ${{ github.sha }}
          Author: ${{ github.actor }}
          Message: ${{ github.event.head_commit.message }}
          Actions run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
```

### What this does

- Triggers on every push (adjust `branches` to restrict to `main` or specific patterns).
- Creates one run per `Given:` case found in the "VPS" section (per-SKU mode).
- Puts the full commit context in the run description so you can trace it back from TestRail.
- Does **not** execute the tests — Jenkins picks up and runs them.

---

## GitHub Secrets

Go to **Settings → Secrets and variables → Actions** in your repository and add:

| Secret name | Value |
|-------------|-------|
| `TESTRAIL_URL` | `https://yourcompany.testrail.io` |
| `TESTRAIL_USERNAME` | Your TestRail email address |
| `TESTRAIL_API_KEY` | TestRail API key (not your password) |

To generate a TestRail API key: **My Settings → API Keys → Add Key**.

---

## Jenkinsfile.firmware-wattbox

This Jenkinsfile detects changed firmware `.bin` files and creates targeted TestRail runs for each firmware type found.

```groovy
pipeline {
    agent any

    triggers {
        // Poll SCM every 5 minutes, or use a webhook
        pollSCM('H/5 * * * *')
    }

    environment {
        TESTRAIL_URL      = credentials('testrail-url')
        TESTRAIL_USERNAME = credentials('testrail-username')
        TESTRAIL_API_KEY  = credentials('testrail-api-key')
    }

    stages {
        stage('Detect changed firmware') {
            steps {
                script {
                    def changedFiles = sh(
                        script: "git diff --name-only HEAD~1 HEAD | grep '\\.bin\$' || true",
                        returnStdout: true
                    ).trim().split('\n').findAll { it }

                    def hasVps   = changedFiles.any { it.toLowerCase().contains('vps') }
                    def hasWifi  = changedFiles.any { it.toLowerCase().contains('wifi') }
                    def hasNs    = changedFiles.any { it.toLowerCase().contains('ns') }

                    env.HAS_VPS  = hasVps  ? 'true' : 'false'
                    env.HAS_WIFI = hasWifi ? 'true' : 'false'
                    env.HAS_NS   = hasNs   ? 'true' : 'false'

                    echo "Detected firmware types — VPS: ${hasVps}, WiFi: ${hasWifi}, NS: ${hasNs}"
                }
            }
        }

        stage('Create VPS runs') {
            when { environment name: 'HAS_VPS', value: 'true' }
            steps {
                sh """
                    python -m easybdd testrail-create-run 77 52630 \\
                      --given-section "VPS" \\
                      --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API" \\
                      --description "Firmware build: ${env.BUILD_NUMBER}, branch: ${env.GIT_BRANCH}"
                """
            }
        }

        stage('Create WiFi runs') {
            when { environment name: 'HAS_WIFI', value: 'true' }
            steps {
                sh """
                    python -m easybdd testrail-create-run 77 52630 \\
                      --given-section "WiFi" \\
                      --sections "Functions" "Firmware Resiliency" "WiFi Config" \\
                      --description "Firmware build: ${env.BUILD_NUMBER}, branch: ${env.GIT_BRANCH}"
                """
            }
        }

        stage('Create NS runs') {
            when { environment name: 'HAS_NS', value: 'true' }
            steps {
                sh """
                    python -m easybdd testrail-create-run 77 52630 \\
                      --given-section "NS" \\
                      --sections "Functions" "Firmware Resiliency" "NS API" \\
                      --description "Firmware build: ${env.BUILD_NUMBER}, branch: ${env.GIT_BRANCH}"
                """
            }
        }
    }

    post {
        always {
            echo "Run creation complete"
        }
    }
}
```

After this pipeline runs, the newly created TestRail runs will be picked up and executed by the execution pipeline (below) on its next poll cycle.

### Mirroring firmware into Floci

The real `Jenkinsfile.firmware-wattbox` in this repo (which differs slightly
from the illustrative snippet above) also includes a **"Mirror Firmware to
Floci"** stage. It runs right after firmware detection and pushes every
changed `.bin` file into a local [Floci](https://floci.io) instance via
`python -m easybdd floci-upload`, in addition to — not instead of — whatever
already happens with the real S3 bucket. It's independent of TestRail run
creation, so it runs even if a changed file doesn't match a known firmware
type. See [Floci Integration](floci-integration.md) for the `floci.*` YAML
actions, the `floci-upload` CLI, and how to point this stage at your own
bucket/endpoint.

---

## Jenkinsfile.create-smoke-run

Use this as a fallback when GitHub Actions is not available, or to run on a pure Jenkins polling trigger.

The key addition is an **SCM trigger guard**: the pipeline checks whether the commit that triggered the build is the same one that created the runs. This prevents creating duplicate runs if the pipeline is re-triggered for the same commit.

```groovy
pipeline {
    agent any

    triggers {
        pollSCM('H/5 * * * *')
    }

    environment {
        TESTRAIL_URL      = credentials('testrail-url')
        TESTRAIL_USERNAME = credentials('testrail-username')
        TESTRAIL_API_KEY  = credentials('testrail-api-key')
    }

    stages {
        stage('SCM trigger guard') {
            steps {
                script {
                    // Only proceed if this build was triggered by an SCM change
                    // (not a manual or timer-triggered re-run of an old commit)
                    def cause = currentBuild.getBuildCauses('hudson.triggers.SCMTrigger$SCMTriggerCause')
                    if (!cause) {
                        echo "Not an SCM-triggered build — skipping run creation"
                        currentBuild.result = 'NOT_BUILT'
                        return
                    }
                    echo "SCM change detected — proceeding with run creation"
                }
            }
        }

        stage('Create smoke runs') {
            steps {
                sh """
                    python -m easybdd testrail-create-run 59 106662 \\
                      --given-section "VPS" \\
                      --sections "Functions" "Firmware Resiliency" "VPS Web UI" "VPS API" \\
                      --description "Branch: ${env.GIT_BRANCH}
                    Commit: ${env.GIT_COMMIT}
                    Build: ${env.BUILD_URL}"
                """
            }
        }
    }
}
```

---

## Full Pipeline Walkthrough

```
Developer pushes to GitHub
        │
        ▼
GitHub Actions (create-smoke-run.yml)
  └─ Installs easybdd
  └─ Calls testrail-create-run --given-section "VPS" ...
  └─ Creates N TestRail runs (one per SKU)
        │
        ▼
TestRail now has open runs with Untested cases
        │
        ▼ (polling, ~5 min interval)
Jenkins (testrail-run pipeline)
  └─ python -m easybdd testrail-run 59
  └─ Finds runs with pending Untested/Retest cases
  └─ Executes each Feature:/Test: case
  └─ Posts results back to TestRail
  └─ Uploads HTML report as attachment to each result
  └─ Posts Teams notification with pass/fail summary
```

### Key points

- Run creation and run execution are decoupled. If Jenkins is down during the push, the runs wait in TestRail until Jenkins comes back.
- The `BUILD_NUMBER` and `BUILD_URL` env vars are set by Jenkins when executing runs, so report filenames and Teams notification links point to the correct Jenkins build.
- Use `--dry-run` on `testrail-create-run` to preview the runs without creating them during pipeline development.
- To suppress Teams notifications for CI development runs, add a `Var:` case with `no_teams: True` to the run.
