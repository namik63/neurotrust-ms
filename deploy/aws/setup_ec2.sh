#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/neurotrust-ms}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
NODE_MAJOR_REQUIRED="${NODE_MAJOR_REQUIRED:-20}"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-http://localhost}"
JOB_ROOT="${JOB_ROOT:-/var/lib/neurotrust-ms/jobs}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: run this on the EC2 Ubuntu server, not on your Mac."
  exit 1
fi
if [[ ! -d "$APP_ROOT/backend" || ! -d "$APP_ROOT/frontend" ]]; then
  echo "ERROR: $APP_ROOT does not look like the NeuroTrust-MS project folder."
  echo "Expected: $APP_ROOT/backend and $APP_ROOT/frontend"
  exit 1
fi

echo "== Installing system packages =="
sudo apt-get update
sudo apt-get install -y nginx python3 python3-venv python3-pip curl ca-certificates rsync

if ! command -v node >/dev/null 2>&1 || ! node -e "process.exit(Number(process.versions.node.split('.')[0]) >= Number(process.env.NODE_MAJOR_REQUIRED || $NODE_MAJOR_REQUIRED) ? 0 : 1)" >/dev/null 2>&1; then
  echo "== Installing Node.js $NODE_MAJOR_REQUIRED =="
  curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR_REQUIRED}.x" | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "== Creating runtime folders =="
sudo mkdir -p "$JOB_ROOT" /var/log/neurotrust-ms
sudo chown -R ubuntu:ubuntu /var/lib/neurotrust-ms /var/log/neurotrust-ms

echo "== Writing hosted environment =="
sudo tee /etc/neurotrust-ms.env >/dev/null <<EOF
HOSTED_MODE=true
HOSTING_MODE=aws_ec2
MAX_BATCH_CASES=5
MAX_CONCURRENT_JOBS=1
JOB_TTL_HOURS=4
MAX_UPLOAD_MB=2048
STORAGE_DIR=$JOB_ROOT
NEUROTRUST_ACCESS_DB=/var/lib/neurotrust-ms/access_log.sqlite3
ACCESS_SESSION_HOURS=${ACCESS_SESSION_HOURS:-8}
NEUROTRUST_DEMO_BATCH_ROOT=${NEUROTRUST_DEMO_BATCH_ROOT:-/var/lib/neurotrust-ms/demo_data/test_1}
NEUROTRUST_ADMIN_SAFETY_KEY=${NEUROTRUST_ADMIN_SAFETY_KEY:-}
NEUROTRUST_ADMIN_SECOND_FACTOR=${NEUROTRUST_ADMIN_SECOND_FACTOR:-}
VIEWER_ASSETS_ON_DEMAND=true
UVICORN_WORKERS=1
FRONTEND_ORIGIN=$PUBLIC_ORIGIN
EOF
sudo chmod 640 /etc/neurotrust-ms.env

echo "== Python backend setup =="
cd "$APP_ROOT/backend"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel setuptools
.venv/bin/pip install -r requirements.txt

echo "== Frontend build =="
cd "$APP_ROOT"
npm --prefix frontend install
VITE_HOSTED_MODE=true npm --prefix frontend run build

echo "== Installing systemd service and Nginx site =="
sudo cp "$APP_ROOT/deploy/aws/neurotrust-ms.service" /etc/systemd/system/neurotrust-ms.service
sudo tee /etc/nginx/neurotrust-ms-basic-auth.conf >/dev/null <<'EOF'
# Server-level basic-auth disabled by default.
# Run /opt/neurotrust-ms/deploy/aws/create_basic_auth.sh only if you want an extra browser password prompt.
EOF
sudo cp "$APP_ROOT/deploy/aws/nginx-neurotrust-ms.conf" /etc/nginx/sites-available/neurotrust-ms
sudo ln -sf /etc/nginx/sites-available/neurotrust-ms /etc/nginx/sites-enabled/neurotrust-ms
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable neurotrust-ms
sudo systemctl restart neurotrust-ms
sudo systemctl restart nginx

echo
echo "SETUP COMPLETE"
echo "Open: $PUBLIC_ORIGIN/"
echo "Health: $PUBLIC_ORIGIN/api/health"
echo
echo "Useful checks:"
echo "  sudo systemctl status neurotrust-ms --no-pager"
echo "  sudo journalctl -u neurotrust-ms -n 80 --no-pager"
echo "  sudo nginx -t"
echo
echo "Optional extra server-level password gate:"
echo "  sudo $APP_ROOT/deploy/aws/create_basic_auth.sh"
