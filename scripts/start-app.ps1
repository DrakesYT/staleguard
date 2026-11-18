# Creates the venv on first run, installs deps, and starts StaleGuard on http://localhost:8000
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install -r requirements.txt
}
if (-not (Test-Path ".env")) { Copy-Item .env.example .env; Write-Host "Created .env - add your TAVILY_API_KEY" }
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
