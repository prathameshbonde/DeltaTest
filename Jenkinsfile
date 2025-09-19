pipeline {
  agent any
  environment {
    LLM_MODE = 'mock'
    CONFIDENCE_THRESHOLD = '0.6'
    EXTRA_GRADLE_ARGS = ''
    SELECTOR_URL = 'http://localhost:8000/select-tests'
  }
  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }
    stage('Setup') {
      steps {
        sh 'python3 -m pip install --upgrade pip || true'
        sh 'pip3 install -r selector-service/requirements.txt'
      }
    }
    stage('Start Selector Service') {
      steps {
        sh 'nohup python3 -m uvicorn selector-service.app.main:app --host 0.0.0.0 --port 8000 & sleep 3'
      }
    }
    stage('Build') {
      steps {
        sh './gradlew assemble --no-daemon'
      }
    }
    stage('Run Selector') {
      steps {
        sh 'bash tools/run_selector.sh --project-root . --base origin/main --head HEAD'
      }
    }
  }
  post {
    always {
      junit allowEmptyResults: true, testResults: '**/build/test-results/test/*.xml'
      archiveArtifacts artifacts: 'selector_output.json, tools/output/**', allowEmptyArchive: true
    }
    failure {
      echo 'Build failed due to test failures or low confidence.'
    }
  }
}
