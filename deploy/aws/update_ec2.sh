#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/neurotrust-ms}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: run this on the EC2 Ubuntu server, not on your Mac."
  exit 1
fi
if [[ ! -d "$APP_ROOT/backend" || ! -d "$APP_ROOT/frontend" ]]; then
  echo "ERROR: $APP_ROOT does not look like the NeuroTrust-MS project folder."
  exit 1
fi

cd "$APP_ROOT"

echo "== Updating backend dependencies =="
if [[ ! -x backend/.venv/bin/python ]]; then
  python3 -m venv backend/.venv
fi
backend/.venv/bin/python -m pip install --upgrade pip wheel setuptools
backend/.venv/bin/pip install -r backend/requirements.txt

echo "== Rebuilding frontend =="
npm --prefix frontend install
VITE_HOSTED_MODE=true npm --prefix frontend run build

echo "== Refreshing service/nginx files =="
sudo cp "$APP_ROOT/deploy/aws/neurotrust-ms.service" /etc/systemd/system/neurotrust-ms.service
sudo cp "$APP_ROOT/deploy/aws/nginx-neurotrust-ms.conf" /etc/nginx/sites-available/neurotrust-ms
if [[ -f /etc/neurotrust-ms.env ]]; then
  if grep -q '^NEUROTRUST_DEMO_BATCH_ROOT=' /etc/neurotrust-ms.env; then
    sudo sed -i 's#^NEUROTRUST_DEMO_BATCH_ROOT=.*#NEUROTRUST_DEMO_BATCH_ROOT=/var/lib/neurotrust-ms/demo_data/test_1#' /etc/neurotrust-ms.env
  else
    echo 'NEUROTRUST_DEMO_BATCH_ROOT=/var/lib/neurotrust-ms/demo_data/test_1' | sudo tee -a /etc/neurotrust-ms.env >/dev/null
  fi
fi
sudo tee /etc/nginx/neurotrust-ms-basic-auth.conf >/dev/null <<'EOF'
# Server-level basic-auth disabled by default.
# Run /opt/neurotrust-ms/deploy/aws/create_basic_auth.sh only if you want an extra browser password prompt.
EOF
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl restart neurotrust-ms
sudo systemctl reload nginx

echo "== Cleaning expired jobs =="
sudo "$APP_ROOT/deploy/aws/cleanup_jobs.sh" || true

echo
echo "UPDATE COMPLETE"
curl -fsS http://127.0.0.1:8000/api/health || true
echo
