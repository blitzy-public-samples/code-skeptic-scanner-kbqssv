#!/bin/bash

set -e

# Authenticate with Google Cloud
echo "Authenticating with Google Cloud..."
gcloud auth activate-service-account --key-file=${GCP_SERVICE_ACCOUNT_KEY}
gcloud config set project ${GCP_PROJECT_ID}

# Build and push Docker images
echo "Building and pushing Docker images..."
docker build -t gcr.io/${GCP_PROJECT_ID}/backend:${VERSION} ./backend
docker build -t gcr.io/${GCP_PROJECT_ID}/frontend:${VERSION} ./frontend
docker push gcr.io/${GCP_PROJECT_ID}/backend:${VERSION}
docker push gcr.io/${GCP_PROJECT_ID}/frontend:${VERSION}

# Apply Kubernetes configurations
echo "Applying Kubernetes configurations..."
kubectl apply -f k8s/

# Update Firestore security rules
echo "Updating Firestore security rules..."
firebase deploy --only firestore:rules

# Run database migrations
echo "Running database migrations..."
kubectl exec -it $(kubectl get pods -l app=backend -o jsonpath="{.items[0].metadata.name}") -- python manage.py migrate

# Perform smoke tests
echo "Performing smoke tests..."
# HUMAN ASSISTANCE NEEDED
# Add appropriate smoke tests here. This could involve curl commands to check API endpoints,
# or running a separate test suite. Example:
# curl -f http://${BACKEND_URL}/health || exit 1

# Update DNS records (if applicable)
# HUMAN ASSISTANCE NEEDED
# This step depends on your DNS provider and specific requirements.
# You may need to use a DNS provider's API or CLI tool to update records.
# Example using Google Cloud DNS:
# gcloud dns record-sets transaction start --zone=${DNS_ZONE}
# gcloud dns record-sets transaction add ${BACKEND_IP} --name=${BACKEND_DOMAIN} --ttl=300 --type=A --zone=${DNS_ZONE}
# gcloud dns record-sets transaction execute --zone=${DNS_ZONE}

echo "Deployment completed successfully!"