#!/bin/bash
# ============================================================================
# Kubernetes Deployment Script
# ============================================================================
#
# Deploys the complete E-Commerce system to Kubernetes
#
# Prerequisites:
# - kubectl configured and connected to cluster
# - Docker images built and pushed to registry (or using local images)
# - Sufficient cluster resources
#
# Usage:
#   ./deploy.sh                 # Deploy everything
#   ./deploy.sh --delete        # Delete everything
#   ./deploy.sh --status        # Check deployment status
#
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="ecommerce-system"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${BLUE}============================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}============================================================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl not found. Please install kubectl first."
        exit 1
    fi
    print_success "kubectl found"
}

# Check cluster connection
check_cluster() {
    if ! kubectl cluster-info &> /dev/null; then
        print_error "Cannot connect to Kubernetes cluster"
        print_info "Please configure kubectl: kubectl config use-context <your-context>"
        exit 1
    fi
    print_success "Connected to Kubernetes cluster"
    kubectl cluster-info | head -1
}

# ============================================================================
# Deployment Functions
# ============================================================================

deploy_all() {
    print_header "Deploying E-Commerce System to Kubernetes"

    # Step 1: Create namespace
    print_info "Step 1/7: Creating namespace..."
    kubectl apply -f "$SCRIPT_DIR/namespace.yaml"
    print_success "Namespace created: $NAMESPACE"
    echo ""

    # Step 2: Create ConfigMap
    print_info "Step 2/7: Creating ConfigMap..."
    kubectl apply -f "$SCRIPT_DIR/configmap.yaml"
    print_success "ConfigMap created"
    echo ""

    # Step 3: Deploy MongoDB
    print_info "Step 3/7: Deploying MongoDB..."
    kubectl apply -f "$SCRIPT_DIR/mongodb.yaml"
    print_success "MongoDB deployed"
    echo ""

    # Step 4: Deploy Kafka & Zookeeper
    print_info "Step 4/7: Deploying Kafka & Zookeeper..."
    kubectl apply -f "$SCRIPT_DIR/kafka.yaml"
    print_success "Kafka & Zookeeper deployed"
    echo ""

    # Wait for infrastructure to be ready
    print_info "Waiting for infrastructure to be ready (this may take 2-3 minutes)..."
    sleep 30

    # Step 5: Deploy Customer Management API
    print_info "Step 5/7: Deploying Customer Management API..."
    kubectl apply -f "$SCRIPT_DIR/customer-management-api.yaml"
    print_success "Customer Management API deployed"
    echo ""

    # Step 6: Deploy Customer Facing Service
    print_info "Step 6/7: Deploying Customer Facing Service..."
    kubectl apply -f "$SCRIPT_DIR/customer-facing-service.yaml"
    print_success "Customer Facing Service deployed"
    echo ""

    # Step 7: Deploy Frontend
    print_info "Step 7/7: Deploying Frontend..."
    kubectl apply -f "$SCRIPT_DIR/frontend.yaml"
    print_success "Frontend deployed"
    echo ""

    print_header "Deployment Complete!"
    print_success "All components have been deployed to namespace: $NAMESPACE"
    echo ""

    print_info "To check deployment status, run:"
    echo "  ./deploy.sh --status"
    echo ""

    print_info "To access the frontend:"
    echo "  kubectl port-forward svc/frontend-service 3000:80 -n $NAMESPACE"
    echo "  Then open: http://localhost:3000"
    echo ""
}

# ============================================================================
# Status Check
# ============================================================================

check_status() {
    print_header "Checking Deployment Status"

    echo ""
    print_info "Namespace:"
    kubectl get namespace $NAMESPACE 2>/dev/null || print_warning "Namespace not found"

    echo ""
    print_info "ConfigMap:"
    kubectl get configmap -n $NAMESPACE

    echo ""
    print_info "Deployments:"
    kubectl get deployments -n $NAMESPACE

    echo ""
    print_info "StatefulSets:"
    kubectl get statefulsets -n $NAMESPACE

    echo ""
    print_info "Services:"
    kubectl get services -n $NAMESPACE

    echo ""
    print_info "Pods:"
    kubectl get pods -n $NAMESPACE

    echo ""
    print_info "Horizontal Pod Autoscalers:"
    kubectl get hpa -n $NAMESPACE

    echo ""
    print_info "Ingress:"
    kubectl get ingress -n $NAMESPACE 2>/dev/null || print_warning "No ingress found"

    echo ""
    print_header "Detailed Pod Status"
    kubectl get pods -n $NAMESPACE -o wide

    echo ""
    print_info "To view logs for a specific pod:"
    echo "  kubectl logs <pod-name> -n $NAMESPACE"
    echo ""

    print_info "To describe a resource:"
    echo "  kubectl describe <resource-type> <resource-name> -n $NAMESPACE"
    echo ""
}

# ============================================================================
# Deletion
# ============================================================================

delete_all() {
    print_header "Deleting E-Commerce System from Kubernetes"

    print_warning "This will delete ALL resources in namespace: $NAMESPACE"
    read -p "Are you sure? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        print_info "Deletion cancelled"
        exit 0
    fi

    print_info "Deleting all resources..."

    kubectl delete -f "$SCRIPT_DIR/frontend.yaml" --ignore-not-found=true
    kubectl delete -f "$SCRIPT_DIR/customer-facing-service.yaml" --ignore-not-found=true
    kubectl delete -f "$SCRIPT_DIR/customer-management-api.yaml" --ignore-not-found=true
    kubectl delete -f "$SCRIPT_DIR/kafka.yaml" --ignore-not-found=true
    kubectl delete -f "$SCRIPT_DIR/mongodb.yaml" --ignore-not-found=true
    kubectl delete -f "$SCRIPT_DIR/configmap.yaml" --ignore-not-found=true
    kubectl delete -f "$SCRIPT_DIR/namespace.yaml" --ignore-not-found=true

    print_success "All resources deleted"
    echo ""
}

# ============================================================================
# Main Script
# ============================================================================

main() {
    # Check prerequisites
    check_kubectl
    check_cluster
    echo ""

    # Parse arguments
    case "${1:-}" in
        --delete|-d)
            delete_all
            ;;
        --status|-s)
            check_status
            ;;
        --help|-h)
            echo "Usage: $0 [OPTION]"
            echo ""
            echo "Options:"
            echo "  (no args)      Deploy all resources"
            echo "  --delete, -d   Delete all resources"
            echo "  --status, -s   Check deployment status"
            echo "  --help, -h     Show this help message"
            echo ""
            ;;
        "")
            deploy_all
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"