# ============================================================================
# Frontend - Dockerfile
# ============================================================================
#
# Serves static HTML/CSS/JS files using nginx web server
#
# Build command:
#   docker build -t frontend:latest .
#
# Run command:
#   docker run -d -p 3000:80 --name frontend frontend:latest
#
# ============================================================================

# Use nginx alpine for lightweight image
FROM nginx:alpine

# Remove default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy our frontend files
COPY index.html /usr/share/nginx/html/
COPY styles.css /usr/share/nginx/html/
COPY app.js /usr/share/nginx/html/

# Copy custom nginx configuration (optional, for SPA routing)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]

# ============================================================================
# BUILD NOTES
# ============================================================================
# Image size: ~25MB (nginx alpine is very small)
#
# Security:
# - Alpine Linux (minimal attack surface)
# - No package manager needed at runtime
# - Read-only root filesystem compatible
#
# Performance:
# - nginx is extremely fast for static files
# - Gzip compression enabled in nginx.conf
# - Browser caching headers configured
# ============================================================================