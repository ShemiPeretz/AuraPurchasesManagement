# ============================================================================
# Customer Facing Web Server - Dockerfile
# ============================================================================
#
# Multi-stage build for optimized image size and security
# Stage 1: Builder - Install dependencies
# Stage 2: Runtime - Copy only necessary files
#
# Build command:
#   docker build -t CustomerFacingService:latest .
#
# Run command:
#   docker run -p 8000:8000 \
#     -e KAFKA_BOOTSTRAP_SERVERS=kafka:9092 \
#     -e CUSTOMER_MANAGEMENT_API_URL=http://customer-management-api:8001 \
#     CustomerFacingService:latest
#
# ============================================================================

# ============================================================================
# STAGE 1: BUILDER
# ============================================================================
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
# - gcc: Required for compiling some Python packages
# - build-essential: Compilation tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
# - --no-cache-dir: Don't cache downloaded packages (saves space)
# - --user: Install to user directory for easy copying
RUN pip install --no-cache-dir --user -r requirements.txt

# ============================================================================
# STAGE 2: RUNTIME
# ============================================================================
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
# Running as non-root is a security best practice
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy Python dependencies from builder stage
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . ./CustomerFacingService/

# Update PATH to include user-installed packages
ENV PATH=/home/appuser/.local/bin:$PATH

# Switch to non-root user
USER appuser

# Environment variables with defaults
# These can be overridden in Kubernetes ConfigMap/Secret
ENV KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ENV KAFKA_TOPIC=purchases
ENV CUSTOMER_MANAGEMENT_API_URL=http://localhost:8001

# Expose port 8000
EXPOSE 8000

# Health check
# Kubernetes will use /health endpoint, but this is good for Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
# - host 0.0.0.0: Listen on all interfaces (required in container)
# - port 8000: Application port
# - no-reload: Don't use auto-reload in production
CMD ["uvicorn", "CustomerFacingService.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

# ============================================================================
# BUILD NOTES
# ============================================================================
# Image size optimizations:
# - Multi-stage build reduces final image size
# - slim base image (no unnecessary tools)
# - Clean up apt cache
# - Don't include test dependencies in production
#
# Security:
# - Run as non-root user
# - Minimal base image (fewer attack vectors)
# - No unnecessary packages
#
# Performance:
# - Python dependencies pre-installed
# - Fast startup time
# ============================================================================