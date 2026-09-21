# =====================================
# AMAVA / ADK Multi-Service Runner
# =====================================

# ---- ACTIVATE PYTHON VENV ----
# Change path if your venv name differs
. .\.venv\Scripts\Activate.ps1

# ---- CONFIG ----
$SERVER_PORT = 51483
# $NGROK_DOMAIN = "electric-mistakenly-rat.ngrok-free.app"
$ADK_PORT = 1483
$AGENT_ROOT = "agents"

# ---- UVICORN SERVER ----
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; .venv\Scripts\Activate.ps1; uvicorn amava_api.app:app --host 0.0.0.0 --port $SERVER_PORT --reload"
)

# ---- NGROK TUNNEL ----
# Start-Process powershell -ArgumentList @(
#     "-NoExit",
#     "-Command",
#     "ngrok http --url=$NGROK_DOMAIN $SERVER_PORT"
# )

# ---- ADK API SERVER ----
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; .venv\Scripts\Activate.ps1; adk api_server $AGENT_ROOT --allow_origins=http://localhost:$SERVER_PORT --host 0.0.0.0 --port $ADK_PORT"
)

# --- FRONTEND SERVER ---
# Start-Process powershell -ArgumentList @(
#     "-NoExit",
#     "-Command",
#     "cd frontend; npm run dev"
# )

Write-Host "Environment awakened. Services are flowing."
Write-Host "Uvicorn Server: http://localhost:$SERVER_PORT"
Write-Host "ADK API Server: http://localhost:$ADK_PORT"
