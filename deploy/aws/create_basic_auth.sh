#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${USER_NAME:-neurotrust}"
AUTH_INCLUDE="/etc/nginx/neurotrust-ms-basic-auth.conf"
HTPASSWD_FILE="/etc/nginx/.htpasswd"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: run this on the EC2 Ubuntu server, not on your Mac."
  exit 1
fi

if ! command -v htpasswd >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y apache2-utils
fi

echo "Create Nginx password for username: $USER_NAME"
sudo htpasswd -c "$HTPASSWD_FILE" "$USER_NAME"

sudo tee "$AUTH_INCLUDE" >/dev/null <<EOF
auth_basic "NeuroTrust-MS";
auth_basic_user_file $HTPASSWD_FILE;
EOF

sudo nginx -t
sudo systemctl reload nginx

echo
echo "BASIC AUTH ENABLED"
echo "Username: $USER_NAME"
echo "Use the password you just typed."
