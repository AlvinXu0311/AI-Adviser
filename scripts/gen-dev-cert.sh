#!/usr/bin/env bash
# Self-signed TLS certificate for local HTTPS (browsers will warn; use a real CA cert in production).
# Writes certs/fullchain.pem and certs/privkey.pem, which docker-compose mounts into nginx.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"
mkdir -p "$DIR"
openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout "$DIR/privkey.pem" -out "$DIR/fullchain.pem" \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 644 "$DIR/fullchain.pem" "$DIR/privkey.pem"  # nginx runs as uid 101 inside the container
echo "Wrote $DIR/fullchain.pem and $DIR/privkey.pem"
