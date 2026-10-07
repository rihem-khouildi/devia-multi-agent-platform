pipeline {
    agent any

    environment {
        PROJECT_NAME = "devia-ci-${BUILD_NUMBER}"
        COMPOSE_PROJECT_NAME = "${PROJECT_NAME}"

        // Ports utilisés uniquement par Jenkins pour éviter les conflits
        BACKEND_PORT = "8001"
        FRONTEND_PORT = "5174"

        // Health check local Jenkins/Docker
        BACKEND_URL = "http://host.docker.internal:${BACKEND_PORT}/health"

        // Docker Hub
        REGISTRY = "rihem202"
        BACKEND_IMAGE = "${REGISTRY}/codeagent-backend"
        FRONTEND_IMAGE = "${REGISTRY}/codeagent-frontend"

        // Azure
        AZURE_RESOURCE_GROUP = "devia-cicd"
        AZURE_BACKEND_APP   = "devia-backend-app"
        AZURE_FRONTEND_APP  = "devia-frontend-app"

        // Valeur temporaire, remplacée après le checkout Git
        DOCKER_TAG = "latest"

        // Backend Azure App Service
        AZURE_BACKEND_URL = "https://your-backend-url.example.com/health"
    }

    options {
        skipDefaultCheckout(true)
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 45, unit: 'MINUTES')
        disableConcurrentBuilds()
        timestamps()
    }

    stages {

        // ── 1. CHECKOUT ───────────────────────────────────────────────
        stage('Checkout') {
            steps {
                echo 'Récupération du code depuis GitHub...'
                checkout scm

                script {
                    def commitSha = sh(
                        script: 'git rev-parse --short=7 HEAD',
                        returnStdout: true
                    ).trim()

                    env.DOCKER_TAG = "${env.BUILD_NUMBER}-${commitSha}"
                    echo "Image tag utilisé : ${env.DOCKER_TAG}"
                }
            }
        }

        // ── 2. PREPARE ENV ────────────────────────────────────────────
        stage('Prepare Environment') {
            steps {
                echo 'Préparation du fichier .env pour Docker Compose...'
                sh '''
                    if [ ! -f .env ]; then
                        if [ -f .env.example ]; then
                            echo "Création du fichier .env à partir de .env.example..."
                            cp .env.example .env
                        else
                            echo "ERREUR: .env.example est introuvable."
                            echo "Ajoute un fichier .env.example à la racine du projet."
                            exit 1
                        fi
                    fi

                    echo "Vérification du fichier .env :"
                    ls -la .env
                '''
            }
        }

        // ── 3. SONARQUBE ANALYSIS ─────────────────────────────────────
        stage('SonarQube Analysis') {
            steps {
                echo 'Analyse de la qualité du code avec SonarQube...'
                withCredentials([string(credentialsId: 'sonarqube-token', variable: 'SONAR_TOKEN')]) {
                    sh '''
                        docker run --rm \
                            -e SONAR_HOST_URL="http://host.docker.internal:9000" \
                            -e SONAR_TOKEN="$SONAR_TOKEN" \
                            -v "$PWD:/usr/src" \
                            sonarsource/sonar-scanner-cli \
                            -Dsonar.projectKey=codeagent \
                            -Dsonar.projectName=CodeAgent \
                            -Dsonar.sources=. \
                            -Dsonar.exclusions="**/node_modules/**,**/.venv/**,**/output/**,**/dist/**,**/__pycache__/**,**/.pytest_cache/**,**/.tools/**,**/.git/**,**/target/**,**/rapport_pfe_Rihem/**,**/powerpoint/**,**/uploaded-projects/**,**/*.pyc,**/devia_local.db,**/base-spring-project/**" \
                            -Dsonar.python.version=3.11
                    '''
                }
            }
        }

        // ── 4. DOCKER CHECK ───────────────────────────────────────────
        stage('Docker Check') {
            steps {
                echo 'Vérification Docker et Docker Compose...'
                sh '''
                    docker --version
                    docker compose version
                    docker ps
                '''
            }
        }

        // ── 4. BUILD DOCKER IMAGES ───────────────────────────────────
        stage('Build Docker Images') {
            steps {
                echo 'Construction des images backend et frontend...'
                sh '''
                    VITE_API_URL=https://your-backend-url.example.com \
                        docker compose build
                '''
            }
        }

        // ── 5. TAG DOCKER IMAGES ─────────────────────────────────────
        stage('Tag Docker Images') {
            steps {
                echo 'Tag des images Docker pour Docker Hub...'
                sh '''
                    echo "Images locales disponibles :"
                    docker images | grep ${COMPOSE_PROJECT_NAME} || true

                    docker tag ${COMPOSE_PROJECT_NAME}-backend:latest ${BACKEND_IMAGE}:${DOCKER_TAG}
                    docker tag ${COMPOSE_PROJECT_NAME}-backend:latest ${BACKEND_IMAGE}:latest

                    docker tag ${COMPOSE_PROJECT_NAME}-frontend:latest ${FRONTEND_IMAGE}:${DOCKER_TAG}
                    docker tag ${COMPOSE_PROJECT_NAME}-frontend:latest ${FRONTEND_IMAGE}:latest

                    echo "Images taggées :"
                    docker images | grep ${REGISTRY} || true
                '''
            }
        }

        // ── 6. PUSH DOCKER IMAGES ─────────────────────────────────────
        stage('Push Docker Images') {
            steps {
                echo 'Publication des images vers Docker Hub...'

                withCredentials([usernamePassword(
                    credentialsId: 'docker-hub-creds',
                    usernameVariable: 'DOCKERHUB_USER',
                    passwordVariable: 'DOCKERHUB_TOKEN'
                )]) {
                    sh '''
                        echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USER" --password-stdin

                        docker push ${BACKEND_IMAGE}:${DOCKER_TAG}
                        docker push ${BACKEND_IMAGE}:latest

                        docker push ${FRONTEND_IMAGE}:${DOCKER_TAG}
                        docker push ${FRONTEND_IMAGE}:latest

                        docker logout
                    '''
                }
            }
        }

        // ── 7. DEPLOY TO AZURE ────────────────────────────────────────
        stage('Deploy to Azure') {
            steps {
                echo 'Déploiement des images sur Azure App Service...'
                withCredentials([azureServicePrincipal(
                    credentialsId: 'azure-sp-creds',
                    subscriptionIdVariable: 'AZURE_SUBSCRIPTION_ID',
                    clientIdVariable:       'AZURE_CLIENT_ID',
                    clientSecretVariable:   'AZURE_CLIENT_SECRET',
                    tenantIdVariable:       'AZURE_TENANT_ID'
                )]) {
                    sh '''
                        az login --service-principal \
                            -u "$AZURE_CLIENT_ID" \
                            -p "$AZURE_CLIENT_SECRET" \
                            --tenant "$AZURE_TENANT_ID"

                        az account set --subscription "$AZURE_SUBSCRIPTION_ID"

                        echo ">>> Déploiement backend : ${BACKEND_IMAGE}:${DOCKER_TAG}"
                        az webapp config container set \
                            --name "$AZURE_BACKEND_APP" \
                            --resource-group "$AZURE_RESOURCE_GROUP" \
                            --container-image-name "${BACKEND_IMAGE}:${DOCKER_TAG}"

                        az webapp restart \
                            --name "$AZURE_BACKEND_APP" \
                            --resource-group "$AZURE_RESOURCE_GROUP"

                        echo ">>> Déploiement frontend : ${FRONTEND_IMAGE}:${DOCKER_TAG}"
                        az webapp config container set \
                            --name "$AZURE_FRONTEND_APP" \
                            --resource-group "$AZURE_RESOURCE_GROUP" \
                            --container-image-name "${FRONTEND_IMAGE}:${DOCKER_TAG}"

                        az webapp restart \
                            --name "$AZURE_FRONTEND_APP" \
                            --resource-group "$AZURE_RESOURCE_GROUP"

                        az logout
                    '''
                }
            }
        }

        // ── 8. AZURE BACKEND HEALTH CHECK ─────────────────────────────
        stage('Azure Backend Health Check') {
            steps {
                echo 'Vérification du backend déployé sur Azure App Service...'
                sh '''
                    echo "Attente du redémarrage / rafraîchissement Azure..."
                    sleep 60

                    echo "Test de l'endpoint Azure : ${AZURE_BACKEND_URL}"
                    curl -f ${AZURE_BACKEND_URL}
                '''
            }
        }

        // ── 9. START APPLICATION LOCAL ────────────────────────────────
        stage('Start Application Local') {
            steps {
                echo "Démarrage local de l’application avec Docker Compose..."
                sh '''
                    docker compose down -v || true
                    docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
                    docker compose ps
                '''
            }
        }

        // ── 10. LOCAL HEALTH CHECK ────────────────────────────────────
        stage('Local Health Check') {
            steps {
                echo 'Vérification que le backend local répond...'
                sh '''
                    echo "Attente du démarrage du backend local..."
                    sleep 25

                    echo "Test de l'endpoint local health : ${BACKEND_URL}"
                    curl -f ${BACKEND_URL}
                '''
            }
        }

        // ── 11. SHOW CONTAINERS ───────────────────────────────────────
        stage('Show Containers') {
            steps {
                echo "Affichage de l’état des conteneurs locaux..."
                sh '''
                    docker compose ps
                '''
            }
        }
    }

    post {
        always {
            echo 'Archivage des logs et nettoyage...'

            sh '''
                docker compose -f docker-compose.yml -f docker-compose.monitoring.yml logs --no-color > docker-compose.log || true
                docker compose -f docker-compose.yml -f docker-compose.monitoring.yml down -v || true

                if [ "${DOCKER_TAG}" != "latest" ]; then
                    docker rmi ${BACKEND_IMAGE}:${DOCKER_TAG} || true
                    docker rmi ${FRONTEND_IMAGE}:${DOCKER_TAG} || true
                fi

                docker rmi ${BACKEND_IMAGE}:latest || true
                docker rmi ${FRONTEND_IMAGE}:latest || true
            '''

            archiveArtifacts artifacts: 'docker-compose.log', allowEmptyArchive: true
        }

        success {
            echo "Pipeline CI/CD terminé avec succès."
            echo "Images publiées :"
            echo "${BACKEND_IMAGE}:${DOCKER_TAG}"
            echo "${BACKEND_IMAGE}:latest"
            echo "${FRONTEND_IMAGE}:${DOCKER_TAG}"
            echo "${FRONTEND_IMAGE}:latest"
            echo "Backend Azure : ${AZURE_BACKEND_URL}"
        }

        failure {
            echo "Pipeline échoué. Vérifie les logs Jenkins."
        }
    }
}