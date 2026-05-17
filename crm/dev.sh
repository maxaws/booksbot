#!/usr/bin/env bash
# Lance le backend et le frontend en mode développement (hot reload)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

trap 'kill 0' EXIT

echo "🚀 Backend FastAPI sur http://localhost:8000"
cd "$SCRIPT_DIR/backend"
uvicorn main:app --reload --port 8000 &

echo "⚡ Frontend Vite sur http://localhost:5173"
cd "$SCRIPT_DIR/frontend"
npm run dev
