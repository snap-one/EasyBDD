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
                    sudo systemctl restart easybdd-local-builder || true
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

        stage('Ensure manual-run job exists') {
            // Creates the "EasyBDD - Manual Run" pipeline job that the test
            // builder's "Run on Jenkins" button triggers (idempotent — skips
            // when the job already exists). Runs on the server so Jenkins
            // credentials come from the production .env and never leave the
            // box. See scripts/create_manual_run_job.py.
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''#!/bin/bash
                        set -euo pipefail
                        set -a; . .env; set +a
                        python3 scripts/create_manual_run_job.py
                    '''
                }
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
