# Purchase Management System - Deployment Guide

## Quick Start

### Automated Deployment
```bash
chmod +x deploy-system.sh
./deploy-system.sh
```

### Manual Deployment
Follow the steps below for complete control over the deployment process.

---

## Manual Deployment Steps

### Prerequisites
- Docker Desktop with Kubernetes enabled
- kubectl CLI tool installed
- Minimum 8GB RAM, 4 CPU cores available

### Step 1: Build Docker Images

```bash
# Build Customer Management API
cd customer-management-service
docker build -t customer-management-api:latest .
cd ..

# Build Customer Facing Service
cd customer-facing-service
docker build -t customer-facing-service:latest .
cd ..

# Build Frontend
cd frontend
docker build -t frontend:latest .
cd ..

# Load Kafka image
docker pull confluentinc/cp-kafka:latest

# Load MongoDB image
docker pull mongo:7

docker load
```

### Step 2: Load Images into Kubernetes

**For Docker Desktop:**
Images are automatically available.

**For Minikube:**
```bash
minikube image load customer-management-api:latest
minikube image load customer-facing-service:latest
minikube image load frontend:latest
minikube image load confluentinc/cp-kafka:latest
minikube image load mongo:7
```

### Step 3: Install Required Kubernetes Add-ons

**Install KEDA:**
```bash
kubectl create namespace keda
```
```bash
kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.13.1/keda-2.13.1.yaml
```
**Apply the official KEDA HTTP Add-on v0.7.0:**
```bash
kubectl apply -f https://github.com/kedacore/http-add-on/releases/download/v0.7.0/keda-add-ons-http-0.7.0.yaml
```
### Step 4: Deploy Application to Kubernetes

```bash
cd k8s

# Deploy in order
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f mongodb.yaml
kubectl apply -f kafka.yaml

# Wait for infrastructure
kubectl wait --for=condition=ready pod -l app=mongodb -n ecommerce-system --timeout=120s
kubectl wait --for=condition=ready pod -l app=kafka -n ecommerce-system --timeout=120s

# Deploy application services
kubectl apply -f customer-management-api.yaml
kubectl apply -f customer-facing-service.yaml
kubectl apply -f frontend.yaml
```

### Step 5: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n ecommerce-system

# Check services
kubectl get svc -n ecommerce-system

# Check ingress
kubectl get ingress -n ecommerce-system

# Check HPA status
kubectl get hpa -n ecommerce-system

# Check KEDA status
kubectl describe httpscaledobject customer-facing-service-http-scaledobject -n ecommerce-system
```

### Step 6: Access the Application

**Frontend:**
```bash
# Open in browser
open http://localhost
```

**API:**
```bash
# Test API endpoint
curl http://api.localhost/health
```

**If localhost doesn't work, use port-forward:**
```bash
# Frontend
kubectl port-forward svc/frontend-service 3000:80 -n ecommerce-system

# API
kubectl port-forward svc/customer-facing-service 8000:8000 -n ecommerce-system

# Then access:
# Frontend: http://localhost:3000
# API: http://localhost:8000
```

---

## Testing the System

```bash
# Check health
curl http://api.localhost/health

# List items
curl http://api.localhost/items

# Make a purchase
curl -X POST http://api.localhost/buy \
  -H "Content-Type: application/json" \
  -d '{"username":"john_doe","user_id":"user_123"}'

# Wait for Kafka processing
sleep 3

# Get purchases
curl http://api.localhost/purchases/user_123
```

---

## Monitoring

```bash
# View pod logs
kubectl logs -f -l app=customer-facing-service -n ecommerce-system
kubectl logs -f -l app=customer-management-api -n ecommerce-system

# Monitor HPA
kubectl get hpa -n ecommerce-system --watch

# View pod metrics
kubectl top pods -n ecommerce-system
```

---

## Cleanup

```bash
# Delete all resources
kubectl delete namespace ecommerce-system

# Or use the deployment script
./deploy-system.sh --delete
```

---

## Troubleshooting

**Pods not starting:**
```bash
kubectl describe pod <pod-name> -n ecommerce-system
kubectl logs <pod-name> -n ecommerce-system
```

**Ingress not working:**
```bash
kubectl get ingress -n ecommerce-system
kubectl describe ingress frontend-ingress -n ecommerce-system
```

**Services not communicating:**
```bash
kubectl get endpoints -n ecommerce-system
kubectl exec -it <pod-name> -n ecommerce-system -- curl http://customer-facing-service:8000/health
```

---

## Architecture

```
Browser → Ingress → Frontend (nginx)
Browser → Ingress → Customer Facing Service → Kafka → Customer Management API → MongoDB
Browser → Ingress → Customer Facing Service → Customer Management API (getAllUserBuys) → MongoDB
```

## Autoscaling Configuration

- **Customer Management API**: 
  - Kafka lag - Scale when lag > 50 messages per pod
  - CPU Scaling: on 70% cpu 
- **Customer Facing Service**: 
  - HTTP request rate scaling: Scales when there are 100+ pending/queued requests
  - 
---

## URLs

- Frontend: http://localhost
- API: http://localhost/api