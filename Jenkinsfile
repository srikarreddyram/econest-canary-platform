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

        // ── Stage 0: Checkout ────────────────────────────────────────────────
        stage('Checkout') {
            echo "Pulling source from: ${params.REPO_URL}"

            // Clean previous workspace (IMPORTANT)
            deleteDir()

        // Clone the repo passed from frontend
            git branch: 'main',
            url: "${params.REPO_URL}"

        // Make scripts executable if present
        sh '''
            if [ -f deploy_script.sh ]; then chmod +x deploy_script.sh; fi
            if [ -f verify_db_structure.py ]; then echo "DB script found"; fi
            if [ -f evaluate_risk.py ]; then echo "Risk script found"; fi
        '''
        }

        // ── Stage 1: Rollback Gate (emergency path) ──────────────────────────
        stage('Rollback Gate') {
            when { expression { params.FORCE_ROLLBACK == true } }
            steps {
                echo '⚠️  FORCE_ROLLBACK flag detected. Executing emergency rollback.'
                sh '/Users/tejsr/Projects/econest-canary-platform/deploy_script.sh 0'
                error('Rollback complete. Build marked FAILED for audit trail.')
            }
        }

        // ── Stage 2: Install Dependencies ───────────────────────────────────
        stage('Install Dependencies') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                echo 'Installing Python dependencies globally via pip3...'
                sh '''
                    pip3 install --quiet --break-system-packages \
                        pandas mlflow scikit-learn 2>/dev/null || \
                    pip3 install --quiet \
                        pandas mlflow scikit-learn
                '''
                sh 'python3 -c "import mlflow, pandas; print(\'Dependencies OK\')"'
            }
        }

        // ── Stage 3: Verify DB Structure ─────────────────────────────────────
        stage('Verify DB Structure') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                echo "Running pre-flight database checks for: ${params.REPO_URL}"
                sh 'python3 verify_db_structure.py'
            }
            post {
                failure { echo '❌ DB schema check failed. Pipeline halted before any traffic shift.' }
            }
        }

        // ── Stage 4: Canary 10% ──────────────────────────────────────────────
        stage('Canary 10%') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                sh '/Users/tejsr/Projects/econest-canary-platform/deploy_script.sh 10'
            }
        }

        // ── Stage 5: Evaluate Risk (MLflow) ──────────────────────────────────
        stage('Evaluate Risk') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                echo 'Querying MLflow Risk Scoring Engine...'
                sh '''
                    export MLFLOW_TRACKING_URI=./mlruns
                    python3 evaluate_risk.py
                '''
            }
            post {
                failure {
                    echo '❌ Risk threshold breached after 10% canary. Automated rollback will fire.'
                }
            }
        }

        // ── Stage 6: Promote 50% ─────────────────────────────────────────────
        stage('Promote 50%') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                sh '/Users/tejsr/Projects/econest-canary-platform/deploy_script.sh 50'
            }
        }

        // ── Stage 7: Promote 100% ────────────────────────────────────────────
        stage('Promote 100%') {
            when { expression { params.FORCE_ROLLBACK == false } }
            steps {
                sh '/Users/tejsr/Projects/econest-canary-platform/deploy_script.sh 100'
            }
        }
    }

    // ── Post Pipeline ────────────────────────────────────────────────────────
    post {
        failure {
            echo '🚨 CRITICAL: Pipeline failure detected. Initiating automatic rollback to 0%.'
            sh '/Users/tejsr/Projects/econest-canary-platform/deploy_script.sh 0'
        }
        success {
            echo '✅ Econest canary deployment completed and validated successfully.'
            echo "Repository: ${params.REPO_URL}"
        }
        always {
            echo "Pipeline finished at: ${new Date()}"
        }
    }
}