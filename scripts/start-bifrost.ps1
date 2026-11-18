# Starts the Bifrost gateway on http://localhost:8080 (needs Node.js).
#
# Provider keys come from .env (GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY). This script writes
# bifrost-data\config.json with every provider whose key is set; Bifrost reads the key values
# from the environment (env.VAR references), so no secret is written to config.json.
#
# The dashboard (http://localhost:8080) is locked until you create an admin account with the setup
# token. The script generates one into .env (BIFROST_SETUP_TOKEN) on first run and prints it.
# Config, the config DB and request logs live in .\bifrost-data
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root "bifrost-data"
New-Item -ItemType Directory -Force -Path $data | Out-Null

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $root ".env.example") $envFile; Write-Host "Created .env from .env.example" }

# Generate a dashboard setup token once.
if (-not (Select-String -Path $envFile -Pattern '^\s*BIFROST_SETUP_TOKEN=\S' -Quiet)) {
    $token = -join ((48..57) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    Add-Content -Path $envFile -Value "`nBIFROST_SETUP_TOKEN=$token" -Encoding ascii
    Write-Host "Generated BIFROST_SETUP_TOKEN in .env"
}

# Load .env into this process so Bifrost can resolve env.VAR references.
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
        [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('"').Trim("'"), "Process")
    }
}

$providerVars = [ordered]@{ gemini = "GEMINI_API_KEY"; groq = "GROQ_API_KEY"; openai = "OPENAI_API_KEY" }
$providers = [ordered]@{}
foreach ($p in $providerVars.Keys) {
    $var = $providerVars[$p]
    $val = [Environment]::GetEnvironmentVariable($var, "Process")
    if ($val -and $val -notmatch 'x{6}') {
        $providers[$p] = @{ keys = @(@{ name = "$p-env"; value = "env.$var"; models = @("*"); weight = 1.0 }) }
    }
}
# Optional: a provider with a deliberately bad key, to demo Bifrost fallback (see README).
if ($env:BIFROST_DEMO_BROKEN_PROVIDER) {
    $providers[$env:BIFROST_DEMO_BROKEN_PROVIDER] = @{ keys = @(@{ name = "broken-demo"; value = "sk-invalid-demo-key"; models = @("*"); weight = 1.0 }) }
    Write-Host "Demo: '$($env:BIFROST_DEMO_BROKEN_PROVIDER)' is configured with an invalid key to force a fallback"
}

$config = [ordered]@{ setup_token = "env.BIFROST_SETUP_TOKEN"; providers = $providers }
$json = $config | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $data "config.json"), $json, (New-Object System.Text.UTF8Encoding($false)))

if ($providers.Count -eq 0) { Write-Warning "No provider key found in .env (GEMINI_API_KEY / GROQ_API_KEY / OPENAI_API_KEY). Add one, or add keys in the dashboard." }
else { Write-Host "Providers from .env: $($providers.Keys -join ', ')" }
Write-Host "Dashboard setup token: $env:BIFROST_SETUP_TOKEN"

npx -y @maximhq/bifrost -app-dir "$data" -port 8080
