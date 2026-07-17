pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
        timestamps()
    }

    // Poll every minute for changes on origin/main.
    // Switch to a GitHub webhook trigger once the server has a public endpoint.
    triggers {
        pollSCM('* * * * *')
    }

    environment {
        PROJECT_DIR = '/home/jenkins/EasyBDD'
        VENV        = '/home/jenkins/EasyBDD/env'
        PYTHON      = '/home/jenkins/EasyBDD/env/bin/python'
        PIP         = '/home/jenkins/EasyBDD/env/bin/pip'
        PROJECT_ID  = '59'
        SUITE_ID    = '106662'
    }

    stages {

        stage('Pull latest code') {
            steps {
                sh '''
                    if [ ! -d "${PROJECT_DIR}/.git" ]; then
                        echo "No git repo at ${PROJECT_DIR} — cloning..."
                        rm -rf "${PROJECT_DIR}"
                        git clone https://github.com/snap-one/EasyBDD.git "${PROJECT_DIR}"
                    fi
                '''
                dir("${PROJECT_DIR}") {
                    sh '''
                        git fetch origin
                        git reset --hard origin/main
                    '''
                }
            }
        }

        stage('Bootstrap virtual environment') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''
                        if [ ! -f "${VENV}/bin/pip" ]; then
                            echo "Creating virtual environment..."
                            python3 -m venv "${VENV}"
                        fi
                    '''
                }
            }
        }

        stage('Install / update dependencies') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''
                        ${PIP} install --quiet --upgrade pip
                        ${PIP} install --quiet -r requirements.txt
                        ${PIP} install --quiet -r frontend/requirements_builder.txt
                        ${PIP} install --quiet -e .
                    '''
                }
            }
        }

        stage('Install Playwright browsers') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '${PYTHON} -m playwright install chromium --with-deps'
                }
            }
        }

        stage('Restart services') {
            steps {
                sh '''
                    echo "Restarting dependent services with updated code..."
                    sudo systemctl restart easybdd-testrail-builder || true
                    sudo systemctl restart easy-bdd-mcp || true
                '''
            }
        }

        stage('Validate test suite') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''
                        if [ ! -f .env ]; then
                            echo "WARNING: .env not found — skipping TestRail validation."
                            echo "Copy credentials to ${PROJECT_DIR}/.env to enable this step."
                            exit 0
                        fi
                        ${PYTHON} -m easybdd validate --testrail-suite ${SUITE_ID} --project ${PROJECT_ID}
                    '''
                }
            }
        }

        stage('Decommission legacy EASYBDD checkout') {
            // One-time migration (2026-07-17): easybdd-testrail-builder.service
            // used to run from the stale /var/lib/jenkins/workspace/EASYBDD
            // checkout. Repoint it at PROJECT_DIR, verify the builder answers
            // on :8091, then archive the old directory (rename, not delete).
            // Remove this stage once it has run successfully.
            steps {
                sh '''#!/bin/bash
                    set -euo pipefail
                    OLD=/var/lib/jenkins/workspace/EASYBDD
                    NEW="${PROJECT_DIR}"
                    UNIT=/etc/systemd/system/easybdd-testrail-builder.service

                    if [ ! -e "$OLD" ]; then
                        echo "Old checkout already gone — nothing to do."
                        exit 0
                    fi

                    echo "=== Current unit ==="
                    systemctl cat easybdd-testrail-builder || true

                    echo "=== Required keys present in new .env? (names only) ==="
                    for key in TESTRAIL_URL TESTRAIL_USERNAME TESTRAIL_API_KEY; do
                        if grep -q "^${key}=" "${NEW}/.env"; then
                            echo "  ${key}: present"
                        else
                            echo "  ${key}: MISSING in ${NEW}/.env — aborting, service left untouched"
                            exit 1
                        fi
                    done

                    if grep -q "$OLD" "$UNIT"; then
                        echo "=== Repointing unit at $NEW ==="
                        sudo -n sed -i.pre-decommission "s|${OLD}|${NEW}|g" "$UNIT"
                        sudo -n systemctl daemon-reload
                        sudo -n systemctl restart easybdd-testrail-builder
                    else
                        echo "Unit already points away from $OLD"
                    fi

                    echo "=== Verifying builder on :8091 ==="
                    up=0
                    for i in $(seq 1 10); do
                        if curl -fsS -o /dev/null http://localhost:8091/; then up=1; break; fi
                        sleep 2
                    done
                    if [ "$up" != 1 ]; then
                        echo "Builder did NOT come up — old dir left in place for rollback"
                        systemctl status easybdd-testrail-builder --no-pager || true
                        exit 1
                    fi
                    echo "Builder is UP on :8091"

                    echo "=== Other systemd references to the old path? ==="
                    REFS=$(grep -rl "workspace/EASYBDD" /etc/systemd/system 2>/dev/null || true)
                    if [ -n "$REFS" ]; then
                        echo "Old path still referenced by: $REFS — NOT archiving"
                        exit 1
                    fi

                    echo "=== crontab references (informational) ==="
                    crontab -l 2>/dev/null | grep EASYBDD || echo "  none"

                    STAMP=$(date +%Y%m%d)
                    echo "=== Archiving $OLD -> ${OLD}.decommissioned-${STAMP} ==="
                    mv "$OLD" "${OLD}.decommissioned-${STAMP}"
                    echo "Decommission complete. Delete the archive after a burn-in period."
                '''
            }
        }
    }

    post {
        success {
            echo "Deployment complete — codebase is up to date."
        }
        failure {
            echo "Deployment FAILED. Check the logs above."
        }
    }
}
