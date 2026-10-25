# Multi-stage build for Frontend
# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Set environment variable for Docker deployment (use relative paths for Nginx proxy)
ENV VITE_BACKEND_URL=""

# Azure AD app registration for Microsoft sign-in (baked into the bundle at build time)
ARG VITE_MSAL_CLIENT_ID=""
ARG VITE_MSAL_TENANT_ID=""
ENV VITE_MSAL_CLIENT_ID=$VITE_MSAL_CLIENT_ID \
    VITE_MSAL_TENANT_ID=$VITE_MSAL_TENANT_ID

# Build the application
RUN npm run build

# Stage 2: Production with Nginx (unprivileged image runs as the nginx user, listens on 8080)
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY --chmod=644 nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
