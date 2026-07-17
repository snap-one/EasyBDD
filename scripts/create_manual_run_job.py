#!/usr/bin/env python3
"""Create the "EasyBDD - Manual Run" Jenkins job (one-time setup).

This is the parameterized pipeline job (built from Jenkinsfile.manual) that
the test builder's "Run on Jenkins" button triggers — see
docs/ci-cd-integration.md. Designed to run ON the Jenkins server (e.g. from
the deploy pipeline) so credentials come from the production .env and never
leave the box.

Reads from the environment:
    JENKINS_URL         (default http://localhost:8080)
    JENKINS_USERNAME    required
    JENKINS_API_TOKEN   required
    JENKINS_MANUAL_JOB  job name (default "EasyBDD - Manual Run")

Idempotent: exits 0 without changes if the job already exists. The SCM
section (repo URL, credentials id, branch) is copied from the existing
"EasyBDD" deploy job so the two can never drift apart. Parameters are
pre-declared in the job config so the very first buildWithParameters call
works; Jenkinsfile.manual re-syncs them on every run anyway.

After creating the job, queues one FIND_ONLY=true smoke build — it only
checks for an active TestRail run, it does not execute tests.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import quote

PROJECT_CHOICES = [
    "59 - JDM Automation",
    "74 - Audio",
    "76 - Routers",
    "77 - Power",
    "78 - Surveillance",
    "79 - Switches",
    "80 - Access Points",
    "81 - Media Distribution",
]

CONFIG_TEMPLATE = """<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <actions/>
  <description>Manually execute a specific TestRail run. Used by the test builder's "Run on Jenkins" button (docs/ci-cd-integration.md). Created by scripts/create_manual_run_job.py.</description>
  <keepDependencies>false</keepDependencies>
  <properties>
    <hudson.model.ParametersDefinitionProperty>
      <parameterDefinitions>
        <hudson.model.ChoiceParameterDefinition>
          <name>PROJECT_ID</name>
          <description>TestRail project to run tests for</description>
          <choices class="java.util.Arrays$ArrayList"><a class="string-array">{choices}</a></choices>
        </hudson.model.ChoiceParameterDefinition>
        <hudson.model.StringParameterDefinition>
          <name>RUN_ID</name>
          <description>Optional: specific TestRail run ID (leave blank to auto-discover)</description>
          <defaultValue></defaultValue>
          <trim>true</trim>
        </hudson.model.StringParameterDefinition>
        <hudson.model.StringParameterDefinition>
          <name>RUN_PREFIX</name>
          <description>Run name prefix to match (ignored if RUN_ID is specified)</description>
          <defaultValue>EASYBDD:</defaultValue>
          <trim>true</trim>
        </hudson.model.StringParameterDefinition>
        <hudson.model.BooleanParameterDefinition>
          <name>FIND_ONLY</name>
          <description>Check if run exists without executing tests</description>
          <defaultValue>false</defaultValue>
        </hudson.model.BooleanParameterDefinition>
      </parameterDefinitions>
    </hudson.model.ParametersDefinitionProperty>
  </properties>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
    {scm_xml}
    <scriptPath>Jenkinsfile.manual</scriptPath>
    <lightweight>true</lightweight>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>"""


def main() -> int:
    url = os.environ.get("JENKINS_URL", "http://localhost:8080").rstrip("/")
    username = os.environ.get("JENKINS_USERNAME", "")
    api_token = os.environ.get("JENKINS_API_TOKEN", "")
    job = os.environ.get("JENKINS_MANUAL_JOB", "EasyBDD - Manual Run")

    if not (username and api_token):
        print("JENKINS_USERNAME / JENKINS_API_TOKEN not set — skipping.")
        return 0

    basic = base64.b64encode(f"{username}:{api_token}".encode()).decode()
    hdr = {"Authorization": "Basic " + basic}

    def req(u, data=None, headers=None, method=None):
        r = urllib.request.Request(
            u, data=data, headers={**hdr, **(headers or {})}, method=method
        )
        return urllib.request.urlopen(r, timeout=30)

    job_url = f"{url}/job/{quote(job, safe='')}"
    try:
        req(job_url + "/api/json")
        print(f"Job '{job}' already exists — nothing to do.")
        return 0
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise

    # Copy the SCM block from the deploy job so repo URL/credentials match.
    src = ET.fromstring(req(f"{url}/job/EasyBDD/config.xml").read().decode())
    scm = src.find("definition/scm")
    if scm is None:
        print("Could not find <scm> in the EasyBDD job config.", file=sys.stderr)
        return 1
    scm_xml = ET.tostring(scm, encoding="unicode")

    config = CONFIG_TEMPLATE.format(
        choices="".join(f"<string>{c}</string>" for c in PROJECT_CHOICES),
        scm_xml=scm_xml,
    )

    crumb = json.loads(req(f"{url}/crumbIssuer/api/json").read().decode())
    crumb_hdr = {crumb["crumbRequestField"]: crumb["crumb"]}

    req(
        f"{url}/createItem?name=" + quote(job),
        data=config.encode(),
        headers={"Content-Type": "application/xml", **crumb_hdr},
        method="POST",
    )
    print(f"Created job '{job}'.")

    resp = req(
        job_url
        + "/buildWithParameters?PROJECT_ID="
        + quote(PROJECT_CHOICES[0])
        + "&FIND_ONLY=true&RUN_PREFIX="
        + quote("EASYBDD:"),
        data=b"",
        headers=crumb_hdr,
        method="POST",
    )
    print("Smoke build queued:", resp.headers.get("Location", "(no queue url)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
