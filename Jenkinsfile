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
        stage('Placeholder') {
            steps {
                echo 'No stages configured yet.'
            }
        }
    }
}
