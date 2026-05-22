#!/bin/bash
# Start FastAPI backend and Streamlit frontend

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  Starting AI Inbox Assistant..."
echo ""

# Backend in background
echo "  [Backend] FastAPI starting..."
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Short delay to let the backend start
sleep 3

# Frontend in background
echo "  [Frontend] Streamlit starting..."
streamlit run "$ROOT/frontend/streamlit_app.py" &
FRONTEND_PID=$!

echo ""
echo "  Backend  -> http://127.0.0.1:8000/docs"
echo "  Frontend -> http://localhost:8501"
echo ""
echo "  Press Ctrl+C to stop both."
echo ""

# Wait and forward Ctrl+C to both processes
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait $BACKEND_PID $FRONTEND_PID
