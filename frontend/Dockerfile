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

# Build the application, then derive the CSP (inline script hashes) from the built index.html
RUN npm run build && node nginx/generate-csp.mjs dist/index.html > /app/csp.conf

# Stage 2: Production with Nginx (unprivileged image runs as the nginx user; HTTP 8080, HTTPS 8443)
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Our server blocks replace the image's default one (which also listens on 8080)
USER root
# Create the config dirs up front: COPY --chmod would otherwise create them without the x bit
RUN rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /etc/nginx/templates /etc/nginx/snippets \
    && chmod 755 /etc/nginx/templates /etc/nginx/snippets
USER 101

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx configuration: the template is rendered into conf.d at container start (envsubst)
COPY --chmod=644 nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --chmod=644 nginx/security_headers.conf /etc/nginx/snippets/security_headers.conf
COPY --chmod=644 --from=builder /app/csp.conf /etc/nginx/snippets/csp.conf
# Periodic reload so renewed certificates are picked up without a restart
COPY --chmod=755 nginx/40-reload-certs.sh /docker-entrypoint.d/40-reload-certs.sh

# Template defaults; override at runtime. TLS certificates are mounted at /etc/nginx/certs.
ENV TRUSTED_PROXY_CIDR=127.0.0.1/32 \
    PUBLIC_HTTPS_PORT=443 \
    TLS_CERT_FILE=/etc/nginx/certs/fullchain.pem \
    TLS_KEY_FILE=/etc/nginx/certs/privkey.pem \
    CERT_RELOAD_INTERVAL=6h

EXPOSE 8080 8443

# Health check (plain-HTTP endpoint that is not redirected)
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
