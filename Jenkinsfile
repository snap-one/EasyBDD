// ── Configure project IDs here ──────────────────────────────────────────────
def TESTRAIL_PROJECTS = [50, 81, 78, 77, 79, 80, 76, 74, 59]   // add or remove project IDs as needed
// ────────────────────────────────────────────────────────────────────────────

def WORKSPACE = '/var/lib/jenkins/workspace/EASY_BDD'

pipeline {
    agent any

    triggers {
        cron('H/5 * * * *')
    }

    options {
        buildDiscarder(logRotator(daysToKeepStr: '7', numToKeepStr: '2016'))
        timestamps()
        timeout(time: 10, unit: 'MINUTES')
        disableConcurrentBuilds()
    }

    stages {
        stage('Run TestRail Projects') {
            steps {
                script {
                    // Build one parallel branch per project ID
                    def branches = TESTRAIL_PROJECTS.collectEntries { projectId ->
                        ["Project ${projectId}": {
                            ws(WORKSPACE) {
                                sh """#!/bin/bash
                                    set -a && . ${WORKSPACE}/.env && set +a
                                    . ${WORKSPACE}/env/bin/activate
                                    python -m easy_bdd testrail-run ${projectId} || true
                                """
                            }
                        }]
                    }
                    parallel branches
                }
            }
        }
    }

    post {
        always {
            script {
                // Collect run names from every project that found an active run
                def found = []
                TESTRAIL_PROJECTS.each { projectId ->
                    def propsFile = "${WORKSPACE}/reports/run_${projectId}.properties"
                    if (fileExists(propsFile)) {
                        def props = readProperties file: propsFile
                        def runName = props['RUN_NAME'] ?: ''
                        def runUrl  = props['RUN_URL']  ?: ''
                        if (runName) {
                            found << [name: runName, url: runUrl]
                        }
                    }
                }

                if (found) {
                    currentBuild.displayName = "#${BUILD_NUMBER} — " + found.collect { it.name }.join(' | ')
                    currentBuild.description = found.collect { "<a href=\"${it.url}\">${it.name}</a>" }.join('<br>')
                }
            }
        }
    }
}
