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
    }

    post {
        always {
            publishHTML(target: [
                allowMissing: true,
                alwaysLinkToLastBuild: true,
                keepAll: true,
                reportDir: "${PROJECT_DIR}/reports",
                reportFiles: '**/*_report_*.html',
                reportName: 'Easy BDD Report'
            ])
        }
        success {
            echo "Deployment complete — codebase is up to date."
        }
        failure {
            echo "Deployment FAILED. Check the logs above."
        }
    }
}
