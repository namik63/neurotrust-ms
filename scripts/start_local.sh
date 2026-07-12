#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source "$ROOT/.venv/bin/activate"
python -m pip install -r "$ROOT/backend/requirements.txt"

npm --prefix "$ROOT/frontend" install

echo
echo "Starting NeuroTrust-MS locally:"
echo "  Backend:  http://127.0.0.1:8000"
echo "  Frontend: http://127.0.0.1:5173"
echo
echo "Press Ctrl+C here to stop both."
echo

cd "$ROOT/backend"
PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID="$!"

cleanup() {
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

npm --prefix "$ROOT/frontend" run dev
