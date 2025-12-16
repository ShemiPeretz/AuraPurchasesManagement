#!/bin/bash

set -e

NAMESPACE="ecommerce-system"

deploy() {
    echo "Starting deployment..."

    # Build images
    echo "[1/6] Building Docker images..."
    docker build -t customer-management-api:latest ./CustomerManagementAPI
    docker build -t customer-facing-service:latest ./customerFacingService
    docker build -t frontend:latest ./frontend

    # Install prerequisites
    echo "[3/6] Installing Kubernetes add-ons..."

    # NGINX Ingress
    kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml &> /dev/null || true

    # KEDA
    kubectl create namespace keda
    kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.13.1/keda-2.13.1.yaml &> /dev/null || true
    kubectl apply -f https://github.com/kedacore/http-add-on/releases/download/v0.7.0/keda-http-add-on-0.7.0.yaml &> /dev/null || true

    # Wait for ingress controller
    echo "Waiting for ingress controller..."
    kubectl wait --namespace ingress-nginx \
      --for=condition=ready pod \
      --selector=app.kubernetes.io/component=controller \
      --timeout=120s &> /dev/null || echo "Ingress controller timeout (may still work)"

    # Deploy application
    echo "[4/6] Deploying application..."
    cd k8s

    kubectl apply -f namespace.yaml
    kubectl config set-context --current --namespace=$NAMESPACE
    kubectl apply -f configmap.yaml
    kubectl apply -f kafka.yaml
    kubectl apply -f mongodb.yaml

    kubectl wait --for=condition=ready pod -l app=kafka -n $NAMESPACE --timeout=120s || true
    echo "Waiting for infrastructure..."
    sleep 30

    kubectl apply -f customer-management-api.yaml
    kubectl apply -f customer-facing-service.yaml
    kubectl apply -f frontend.yaml

    # Wait for pods
    echo "[5/6] Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod -l app=customer-management-api -n $NAMESPACE --timeout=120s || true
    kubectl wait --for=condition=ready pod -l app=customer-facing-service -n $NAMESPACE --timeout=120s || true
    kubectl wait --for=condition=ready pod -l app=frontend -n $NAMESPACE --timeout=120s || true

    cd ..

    # Display status
    echo "[6/6] Deployment complete!"
    echo ""
    echo "Checking status..."
    kubectl get pods -n $NAMESPACE
    echo ""
    kubectl get svc -n $NAMESPACE
    echo ""
    kubectl get ingress -n $NAMESPACE
    echo ""
    echo "Access the application:"
    echo "  Frontend: http://localhost"
    echo "  API: http://localhost/api"
    echo ""
    echo "If ingress doesn't work, use port-forward:"
    echo "  kubectl port-forward svc/frontend-service 3000:80 -n $NAMESPACE"
    echo "  kubectl port-forward svc/customer-facing-service 8000:8000 -n $NAMESPACE"
}

delete() {
    echo "Deleting all resources..."
    kubectl delete namespace $NAMESPACE --ignore-not-found=true
    echo "Cleanup complete"
}

status() {
    echo "System Status:"
    echo ""
    kubectl get pods -n $NAMESPACE
    echo ""
    kubectl get svc -n $NAMESPACE
    echo ""
    kubectl get ingress -n $NAMESPACE
    echo ""
    kubectl get hpa -n $NAMESPACE
}

case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    delete|cleanup)
        delete
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 [deploy|delete|status]"
        exit 1
        ;;
esac