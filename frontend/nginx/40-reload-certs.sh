#!/bin/sh
# Reload nginx every CERT_RELOAD_INTERVAL (default 6h) so certificates renewed by certbot are
# served without a restart. A reload re-reads certs and config; open connections are unaffected.
set -eu
interval="${CERT_RELOAD_INTERVAL:-6h}"
[ "$interval" = "0" ] && exit 0
(
  while sleep "$interval"; do
    nginx -s reload 2>/dev/null || true
  done
) &
echo "$0: reloading nginx every $interval to pick up renewed certificates"
