# Start FastAPI backend and Streamlit frontend
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 | Out-Null

$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "  Starting AI Inbox Assistant..." -ForegroundColor Cyan
Write-Host ""

# Backend in a new PowerShell window
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$root'; Write-Host '  [Backend] FastAPI starting...' -ForegroundColor Green; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# Short delay to let the backend start
Start-Sleep -Seconds 3

# Frontend in another PowerShell window
Start-Process powershell -ArgumentList "-NoExit", "-Command", `
    "cd '$root'; Write-Host '  [Frontend] Streamlit starting...' -ForegroundColor Green; streamlit run frontend/streamlit_app.py"

Write-Host "  Backend  -> http://127.0.0.1:8000/docs" -ForegroundColor Yellow
Write-Host "  Frontend -> http://localhost:8501" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Close both PowerShell windows to stop." -ForegroundColor DarkGray
Write-Host ""
