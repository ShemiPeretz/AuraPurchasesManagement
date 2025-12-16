FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY ../requirements.txt .

# Install Python dependencies
# - --no-cache-dir: Don't cache downloaded packages (saves space)
# - --user: Install to user directory for easy copying
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Copy Python dependencies from builder stage
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . ./CustomerManagementAPI/


ENV PYTHONPATH="${PYTHONPATH}:/app"

# Update PATH to include user-installed packages
ENV PATH=/home/appuser/.local/bin:$PATH

# Switch to non-root user
USER appuser

# Environment variables with defaults
# These can be overridden in Kubernetes ConfigMap/Secret
ENV MONGODB_URI=mongodb://localhost:27017
ENV MONGODB_DB_NAME=ecommerce
ENV MONGODB_COLLECTION=purchases
ENV KAFKA_BOOTSTRAP_SERVERS=localhost:9092
ENV KAFKA_TOPIC=purchases
ENV KAFKA_GROUP_ID=customer-management-group

# Expose port 8001
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

# Run the application
CMD ["uvicorn", "CustomerManagementAPI.main:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
