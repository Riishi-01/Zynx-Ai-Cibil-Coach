#!/bin/bash
# Start the CIBIL Coach web server

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                 CIBIL CREDIT COACH — Web Server                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo

cd "$(dirname "$0")"

# Activate venv
source .venv/bin/activate

echo "Starting FastAPI server..."
echo
echo "🌐 Web interface: http://localhost:8000"
echo "📚 API docs:     http://localhost:8000/docs"
echo
echo "Press Ctrl+C to stop"
echo

PYTHONPATH=/Users/rr/DEV/CIBIL\ Coach python3 -m uvicorn app.web:app --reload --host 0.0.0.0 --port 8000
