# Creates the venv on first run, installs deps, and starts StaleGuard on http://localhost:8000
# Uses uv when available (it can fetch a Python if none is installed), else the python on PATH.
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path ".venv")) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        uv venv --python 3.12 .venv
        uv pip install --python .venv\Scripts\python.exe -r requirements.txt
    } else {
        python -m venv .venv
        .\.venv\Scripts\python -m pip install -r requirements.txt
    }
}
if (-not (Test-Path ".env")) { Copy-Item .env.example .env; Write-Host "Created .env - add TAVILY_API_KEY and a provider key, then run scripts\start-bifrost.ps1" }
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
