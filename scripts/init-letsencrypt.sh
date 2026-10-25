#!/usr/bin/env bash
# First-time Let's Encrypt certificate for production (docker-compose.prod.yml).
#
#   DOMAIN=adviser.example.edu LETSENCRYPT_EMAIL=ops@example.edu ./scripts/init-letsencrypt.sh
#   STAGING=1 ...   use the staging CA first to test without hitting rate limits
#
# nginx cannot start without a certificate and certbot needs nginx up to answer the HTTP-01
# challenge, so: install a throwaway self-signed cert, start nginx, replace it with the real one.
set -euo pipefail
: "${DOMAIN:?Set DOMAIN (must resolve to this host)}"
: "${LETSENCRYPT_EMAIL:?Set LETSENCRYPT_EMAIL (expiry notices)}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export DOMAIN
COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
LIVE="/etc/letsencrypt/live/$DOMAIN"
# nginx runs as uid 101 (unprivileged image): let its group read the keys certbot writes as 0600
PERMS_HOOK="chgrp -R 101 /etc/letsencrypt/live /etc/letsencrypt/archive && chmod -R g+rX /etc/letsencrypt/live /etc/letsencrypt/archive"

echo "==> Temporary self-signed certificate for $DOMAIN"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint sh certbot -c "
  mkdir -p $LIVE &&
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=$DOMAIN \
    -keyout $LIVE/privkey.pem -out $LIVE/fullchain.pem &&
  $PERMS_HOOK"

echo "==> Starting the stack"
"${COMPOSE[@]}" up -d --build

echo "==> Removing the temporary certificate"
"${COMPOSE[@]}" run --rm --no-deps --entrypoint sh certbot -c "
  rm -rf $LIVE /etc/letsencrypt/archive/$DOMAIN /etc/letsencrypt/renewal/$DOMAIN.conf"

echo "==> Requesting the real certificate"
staging_flag=()
[ "${STAGING:-0}" = "1" ] && staging_flag=(--staging)
# --deploy-hook is saved in the renewal config, so renewals keep the key readable for nginx
"${COMPOSE[@]}" run --rm --no-deps --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot -d "$DOMAIN" \
  --email "$LETSENCRYPT_EMAIL" --agree-tos --no-eff-email --non-interactive \
  --deploy-hook "$PERMS_HOOK" "${staging_flag[@]}"

echo "==> Loading it into nginx"
"${COMPOSE[@]}" exec frontend nginx -s reload
echo "Done: https://$DOMAIN"
