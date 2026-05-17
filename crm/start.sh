#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "📦 Installation des dépendances backend..."
cd "$SCRIPT_DIR/backend"
pip install -r requirements.txt -q

echo "📦 Installation des dépendances frontend..."
cd "$SCRIPT_DIR/frontend"
npm install --silent

echo "🔨 Build du frontend..."
npm run build

echo "🚀 Démarrage du CRM One System sur http://localhost:8000"
cd "$SCRIPT_DIR/backend"
uvicorn main:app --host 0.0.0.0 --port 8000
