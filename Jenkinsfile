pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 10, unit: 'MINUTES')
        disableConcurrentBuilds()
        timestamps()
    }

    triggers {
        githubPush()
    }

    environment {
        PROJECT_DIR = '/home/jenkins/Easy_BDD'
        VENV        = '/home/jenkins/Easy_BDD/env'
        PYTHON      = '/home/jenkins/Easy_BDD/env/bin/python'
        PIP         = '/home/jenkins/Easy_BDD/env/bin/pip'
        // TestRail smoke suite — same project/suite used by
        // Jenkinsfile.create-smoke-run and the GitHub Action in
        // docs/ci-cd-integration.md. Cases here are authored via the
        // web UI test builder / directly in TestRail, not as local YAML.
        PROJECT_ID  = '59'
        SUITE_ID    = '106662'
    }

    stages {

        stage('Pull latest code') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''
                        git fetch origin
                        git reset --hard origin/$(git rev-parse --abbrev-ref HEAD)
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

        stage('Validate test suite') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''
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
            echo "Deployment complete — codebase is up to date and validates cleanly."
        }
        failure {
            echo "Update FAILED. Check the logs above. The previous codebase is still in place."
        }
    }
}
