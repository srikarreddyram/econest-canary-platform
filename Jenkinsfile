pipeline {
    agent any

    stages {

        stage('Verify DB Structure') {
            steps {
                echo 'Running pre-flight database checks...'
                sh '''
                    chmod +x deploy_script.sh
                    pip3 install --quiet pandas mlflow scikit-learn 2>/dev/null || true
                    python3 verify_db_structure.py
                '''
            }
        }

        stage('Canary 10%') {
            steps {
                sh './deploy_script.sh 10'
            }
        }

        stage('Evaluate Risk') {
            steps {
                echo 'Querying MLflow Risk Scoring Engine...'
                sh '''
                export MLFLOW_TRACKING_URI=./mlruns
                    python3 evaluate_risk.py
                '''
            }
        }

        stage('Promote 50%') {
            steps {
                sh './deploy_script.sh 50'
            }
        }

        stage('Promote 100%') {
            steps {
                sh './deploy_script.sh 100'
            }
        }
    }

    post {
        failure {
            echo '🚨 CRITICAL: Risk threshold breached! Initiating automatic rollback.'
            sh './deploy_script.sh 0'
        }
        success {
            echo '✅ Deployment completed and validated successfully.'
        }
    }
}