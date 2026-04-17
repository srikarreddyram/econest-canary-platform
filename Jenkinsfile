pipeline {
    agent any
    
    stages {
        stage('Verify DB Structure') {
            steps {
                // Grant execute permissions on Mac
                sh 'chmod +x deploy_script.sh'
                echo 'Running pre-flight database checks...'
                sh '''
                    source venv/bin/activate
                    python verify_db_structure.py
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
                    source venv/bin/activate
                    python evaluate_risk.py
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