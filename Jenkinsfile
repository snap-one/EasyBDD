pipeline {
    agent any

    options {
        // Keep last 10 builds; abort if a run takes longer than 10 minutes
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 10, unit: 'MINUTES')
        // Don't run concurrent builds (prevents two pulls fighting each other)
        disableConcurrentBuilds()
        timestamps()
    }

    triggers {
        // Fires when GitHub sends a push webhook to Jenkins.
        // In the job config: enable "GitHub hook trigger for GITScm polling".
        githubPush()
    }

    environment {
        PROJECT_DIR = '/var/lib/jenkins/workspace/EASY_BDD'
        VENV        = '/var/lib/jenkins/workspace/EASY_BDD/env'
        PYTHON      = '/var/lib/jenkins/workspace/EASY_BDD/env/bin/python'
        PIP         = '/var/lib/jenkins/workspace/EASY_BDD/env/bin/pip'
    }

    stages {

        stage('Pull latest code') {
            steps {
                dir("${PROJECT_DIR}") {
                    sh '''
                        git fetch origin
                        git reset --hard origin/main
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

    }

    post {
        success {
            echo "Deployment complete — codebase is up to date."
        }
        failure {
            echo "Update FAILED. Check the logs above. The previous codebase is still in place."
        }
    }
}
