#!/usr/bin/env bash
set -euo pipefail

# Supply Chain AI Platform — Deployment Script
# Usage: ./scripts/deploy.sh <environment> <image_tag>

ENVIRONMENT="${1:-staging}"
IMAGE_TAG="${2:-latest}"
NAMESPACE="supply-chain"
HELM_RELEASE="supply-chain"
HELM_CHART="./infrastructure/kubernetes/helm/supply-chain-api"
TIMEOUT="600s"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()     { echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*"; }
success() { echo -e "${GREEN}✓${NC} $*"; }
warning() { echo -e "${YELLOW}⚠${NC} $*"; }
error()   { echo -e "${RED}✗${NC} $*" >&2; }

if [[ ! "$ENVIRONMENT" =~ ^(development|staging|production)$ ]]; then
    error "Invalid environment: $ENVIRONMENT"
    exit 1
fi

log "Starting deployment to $ENVIRONMENT with image tag $IMAGE_TAG"

for cmd in kubectl helm aws; do
    command -v "$cmd" &>/dev/null || { error "Required: $cmd"; exit 1; }
done

CLUSTER_NAME="supply-chain-${ENVIRONMENT}"
log "Configuring kubectl for cluster: $CLUSTER_NAME"
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "${AWS_REGION:-us-east-1}"

kubectl cluster-info &>/dev/null || { error "Cannot connect to cluster"; exit 1; }
success "Connected to $CLUSTER_NAME"

# Run DB migrations
if [[ -n "${ECR_REGISTRY:-}" ]]; then
    log "Running database migrations..."
    kubectl delete job db-migration -n "$NAMESPACE" --ignore-not-found
    kubectl apply -f infrastructure/kubernetes/jobs/db-migration-job.yaml \
        --dry-run=none 2>/dev/null || \
    kubectl set image job/db-migration migration="${ECR_REGISTRY}/supply-chain/supply-chain-api:${IMAGE_TAG}" \
        -n "$NAMESPACE" 2>/dev/null || true

    if kubectl wait job/db-migration -n "$NAMESPACE" --for=condition=complete --timeout=120s 2>/dev/null; then
        success "Database migrations completed"
    else
        error "Database migrations failed"
        kubectl logs job/db-migration -n "$NAMESPACE" --tail=50 2>/dev/null || true
        exit 1
    fi
fi

# Deploy with Helm
log "Deploying with Helm (image=$IMAGE_TAG)..."
helm upgrade --install "$HELM_RELEASE" "$HELM_CHART" \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --set "api.image.tag=$IMAGE_TAG" \
    --set "worker.image.tag=$IMAGE_TAG" \
    --set "global.environment=$ENVIRONMENT" \
    --atomic \
    --timeout "$TIMEOUT" \
    --wait

success "Helm deployment complete"

# Verify rollout
kubectl rollout status deployment/supply-chain-api -n "$NAMESPACE" --timeout=120s
kubectl rollout status deployment/supply-chain-worker -n "$NAMESPACE" --timeout=120s
success "Rollout verified"

# Health check
API_URL="${API_BASE_URL:-http://localhost:8000}"
sleep 10
for i in {1..5}; do
    curl -sf "${API_URL}/health" &>/dev/null && { success "Health check passed"; break; }
    [[ $i -eq 5 ]] && { error "Health check failed"; exit 1; }
    warning "Attempt $i failed, retrying..."
    sleep 10
done

echo ""
echo "══════════════════════════════════════════════════"
success "Deployment to $ENVIRONMENT complete!"
echo "  Image:    $IMAGE_TAG"
echo "  Cluster:  $CLUSTER_NAME"
echo "══════════════════════════════════════════════════"
