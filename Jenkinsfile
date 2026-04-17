pipeline {
    agent any

    parameters {
        string(
            name: 'REPO_URL',
            defaultValue: 'https://github.com/srikarreddyram/econest-canary-platform.git',
            description: 'GitHub repository to deploy through the canary pipeline'
        )
        booleanParam(
            name: 'FORCE_ROLLBACK',
            defaultValue: false,
            description: 'If true, immediately run rollback and skip all other stages'
        )
    }

    stages {

        // ── Stage 0: Checkout ─────────────────────────────────────
        stage('Checkout') {
            steps {
                echo "Pulling source from: ${params.REPO_URL}"

                // Clean workspace
                deleteDir()

                // Clone repo from frontend input
                git branch: 'main', url: "${params.REPO_URL}"

                // Ensure scripts exist + are executable
                sh '''
                if [ -f deploy_script.sh ]; then chmod +x deploy_script.sh; fi
                if [ -f verify_db_structure.py ]; then echo "DB script found"; fi
                if [ -f evaluate_risk.py ]; then echo "Risk script found"; fi
                '''
            }
        }

        // ── Stage 1: Rollback Gate ────────────────────────────────
        stage('Rollback Gate') {
            when { expression { params.FORCE_ROLLBACK == true } }
            steps {
                echo '⚠️ FORCE_ROLLBACK detected'
                sh './deploy_script.sh 0'
                error('Rollback complete. Marking build FAILED.')
            }
        }

        // ── Stage 2: Install Dependencies ─────────────────────────
        stage('Install Dependencies') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                echo 'Installing dependencies...'
                sh '''
                    pip3 install --quiet pandas mlflow scikit-learn || \
                    pip3 install pandas mlflow scikit-learn
                '''
                sh 'python3 -c "import mlflow, pandas; print(\'Dependencies OK\')"'
            }
        }

        // ── Stage 3: Verify DB ───────────────────────────────────
        stage('Verify DB Structure') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                echo "Running DB checks..."
                sh 'python3 verify_db_structure.py'
            }
            post {
                failure {
                    echo '❌ DB check failed'
                }
            }
        }

        // ── Stage 4: Canary 10% ──────────────────────────────────
        stage('Canary 10%') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                sh './deploy_script.sh 10'
            }
        }

        // ── Stage 5: Evaluate Risk ───────────────────────────────
        stage('Evaluate Risk') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                echo 'Evaluating MLflow risk...'
                sh '''
                    export MLFLOW_TRACKING_URI=./mlruns
                    python3 evaluate_risk.py
                '''
            }
            post {
                failure {
                    echo '❌ Risk failed — will rollback'
                }
            }
        }

        // ── Stage 6: Promote 50% ─────────────────────────────────
        stage('Promote 50%') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                sh './deploy_script.sh 50'
            }
        }

        // ── Stage 7: Promote 100% ────────────────────────────────
        stage('Promote 100%') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                sh './deploy_script.sh 100'
            }
        }
    }

    // ── Post ────────────────────────────────────────────────────
    post {
        failure {
            echo '🚨 Pipeline failed → auto rollback'
            sh './deploy_script.sh 0'
        }
        success {
            echo "✅ Deployment successful for ${params.REPO_URL}"
        }
        always {
            echo "Finished at: ${new Date()}"
        }
    }
}