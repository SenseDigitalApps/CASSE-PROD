#!/usr/bin/env bash
# Enable HTTPS for CASSE backend on EC2 (Amazon Linux / Ubuntu).
# Uses sslip.io so Let's Encrypt can issue a cert without a custom domain:
#   3.95.37.172.sslip.io  →  3.95.37.172
#
# Usage (on the EC2 host, from any directory):
#   bash setup_https_sslip.sh
# Or with a custom domain later:
#   DOMAIN=api.tudominio.com bash setup_https_sslip.sh
#
set -euo pipefail

PUBLIC_IP="${PUBLIC_IP:-3.95.37.172}"
DOMAIN="${DOMAIN:-${PUBLIC_IP}.sslip.io}"
EMAIL="${CERTBOT_EMAIL:-casse@proffesionalsense.com}"
NGINX_CONF="${NGINX_CONF:-/etc/nginx/conf.d/casse-backend.conf}"
BACKEND_DIR="${BACKEND_DIR:-$HOME/CASSE/BACKEND}"

echo "==> Domain: $DOMAIN"
echo "==> Nginx conf: $NGINX_CONF"
echo "==> Backend dir: $BACKEND_DIR"

if [[ ! -f "$NGINX_CONF" ]]; then
  echo "ERROR: Nginx conf not found at $NGINX_CONF"
  exit 1
fi

# --- Install certbot ---
if command -v yum >/dev/null 2>&1; then
  sudo yum install -y certbot python3-certbot-nginx || sudo dnf install -y certbot python3-certbot-nginx
elif command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y certbot python3-certbot-nginx
fi

# --- Ensure HTTP server_name includes domain (needed for ACME + later HTTPS) ---
sudo cp "$NGINX_CONF" "${NGINX_CONF}.bak.$(date +%Y%m%d%H%M%S)"
TMP="$(mktemp)"
sudo sed -E \
  -e "s/^[[:space:]]*server_name .*/    server_name ${PUBLIC_IP} ${DOMAIN};/" \
  "$NGINX_CONF" > "$TMP"
sudo cp "$TMP" "$NGINX_CONF"
rm -f "$TMP"

sudo nginx -t
sudo systemctl reload nginx

# --- Open HTTPS in firewall / security group reminder ---
echo "==> Ensure AWS Security Group allows inbound TCP 443 from 0.0.0.0/0"

# --- Obtain / install certificate ---
sudo certbot --nginx \
  -d "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL" \
  --redirect

sudo nginx -t
sudo systemctl reload nginx

# --- Update Django ALLOWED_HOSTS in .env ---
ENV_FILE="$BACKEND_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^DJANGO_ALLOWED_HOSTS=' "$ENV_FILE"; then
    # Append domain/IP if missing
    CURRENT="$(grep '^DJANGO_ALLOWED_HOSTS=' "$ENV_FILE" | cut -d= -f2-)"
    NEW="$CURRENT"
    [[ "$CURRENT" == *"$DOMAIN"* ]] || NEW="${NEW},${DOMAIN}"
    [[ "$CURRENT" == *"$PUBLIC_IP"* ]] || NEW="${NEW},${PUBLIC_IP}"
    # Normalize leading commas
    NEW="$(echo "$NEW" | sed 's/^,//')"
    sudo sed -i "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=${NEW}|" "$ENV_FILE"
  else
    echo "DJANGO_ALLOWED_HOSTS=${PUBLIC_IP},${DOMAIN},127.0.0.1,localhost" >> "$ENV_FILE"
  fi
  echo "==> Updated DJANGO_ALLOWED_HOSTS"
  grep '^DJANGO_ALLOWED_HOSTS=' "$ENV_FILE"
  cd "$BACKEND_DIR"
  docker-compose up -d --force-recreate api
else
  echo "WARN: $ENV_FILE not found — add $DOMAIN to DJANGO_ALLOWED_HOSTS manually"
fi

echo
echo "==> Done. Test:"
echo "    curl -sI https://${DOMAIN}/api/v1/health/"
echo "    curl -s  https://${DOMAIN}/api/v1/health/"
echo
echo "App URL (already set in Flutter api_config.dart):"
echo "    https://${DOMAIN}"
