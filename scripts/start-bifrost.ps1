# Starts the Bifrost gateway on http://localhost:8080 (needs Node.js).
#
# Provider keys come from .env (GEMINI_API_KEY, GROQ_API_KEY, OPENAI_API_KEY). This script writes
# bifrost-data\config.json with every provider whose key is set; Bifrost reads the key values
# from the environment (env.VAR references), so no secret is written to config.json.
#
# The dashboard (http://localhost:8080) is locked until you create an admin account with the setup
# token. The script generates one into .env (BIFROST_SETUP_TOKEN) on first run and prints it.
# It also generates the app's virtual key (BIFROST_VIRTUAL_KEY) with a daily budget, BIFROST_BUDGET_USD
# (default 1.00). Every inference call must carry it; StaleGuard sends it in the x-bf-vk header.
# Config, the config DB and request logs live in .\bifrost-data
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root "bifrost-data"
New-Item -ItemType Directory -Force -Path $data | Out-Null

$envFile = Join-Path $root ".env"
if (-not (Test-Path $envFile)) { Copy-Item (Join-Path $root ".env.example") $envFile; Write-Host "Created .env from .env.example" }

function New-Secret([int]$n) { -join (1..$n | ForEach-Object { [char]((48..57) + (97..122) | Get-Random) }) }

# Generate a dashboard setup token and the app's virtual key once.
if (-not (Select-String -Path $envFile -Pattern '^\s*BIFROST_SETUP_TOKEN=\S' -Quiet)) {
    Add-Content -Path $envFile -Value "`nBIFROST_SETUP_TOKEN=$(New-Secret 32)" -Encoding ascii
    Write-Host "Generated BIFROST_SETUP_TOKEN in .env"
}
if (-not (Select-String -Path $envFile -Pattern '^\s*BIFROST_VIRTUAL_KEY=\S' -Quiet)) {
    Add-Content -Path $envFile -Value "BIFROST_VIRTUAL_KEY=sk-bf-$(New-Secret 32)" -Encoding ascii
    Write-Host "Generated BIFROST_VIRTUAL_KEY in .env"
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
        # Free tiers rate-limit per minute (Gemini 15 req/min, Groq 8k tokens/min per model). Retry a 429
        # briefly with backoff, then let the request fall back to the next model in the chain.
        $providers[$p] = [ordered]@{
            keys           = @(@{ name = "$p-env"; value = "env.$var"; models = @("*"); weight = 1.0 })
            network_config = [ordered]@{ max_retries = 2; retry_backoff_initial = 1500; retry_backoff_max = 8000 }
        }
    }
}

# Governance: the app authenticates with one virtual key that has a daily USD budget (Bifrost prices every
# call from its model catalog) and an hourly rate limit. Inference without a valid virtual key is refused.
$budget = 1.0
if ($env:BIFROST_BUDGET_USD) { $budget = [double]::Parse($env:BIFROST_BUDGET_USD, [Globalization.CultureInfo]::InvariantCulture) }
$vkProviders = @($providers.Keys | ForEach-Object {
    [ordered]@{ provider = $_; allowed_models = @("*"); key_ids = @("*"); weight = 1.0 }
})
$governance = [ordered]@{
    rate_limits  = @([ordered]@{ id = "staleguard-hourly"; request_max_limit = 600; request_reset_duration = "1h";
                                 token_max_limit = 2000000; token_reset_duration = "1h" })
    budgets      = @([ordered]@{ id = "staleguard-daily"; max_limit = $budget; reset_duration = "1d";
                                 virtual_key_id = "staleguard-app" })
    virtual_keys = @([ordered]@{
        id = "staleguard-app"; name = "StaleGuard app"; description = "Used by the StaleGuard API for every LLM call"
        value = "env.BIFROST_VIRTUAL_KEY"; is_active = $true; calendar_aligned = $true
        rate_limit_id = "staleguard-hourly"; provider_configs = $vkProviders
        metadata = [ordered]@{ project = "staleguard" }
    })
}

$config = [ordered]@{
    setup_token = "env.BIFROST_SETUP_TOKEN"
    client      = [ordered]@{ enforce_auth_on_inference = $true }
    providers   = $providers
    governance  = $governance
}
$json = $config | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $data "config.json"), $json, (New-Object System.Text.UTF8Encoding($false)))

if ($providers.Count -eq 0) { Write-Warning "No provider key found in .env (GEMINI_API_KEY / GROQ_API_KEY / OPENAI_API_KEY). Add one, or add keys in the dashboard." }
else { Write-Host "Providers from .env: $($providers.Keys -join ', ')" }
Write-Host "Virtual key 'staleguard-app': daily budget `$$budget, 600 requests / 2M tokens per hour"
Write-Host "Dashboard setup token: $env:BIFROST_SETUP_TOKEN"

npx -y @maximhq/bifrost -app-dir "$data" -port 8080
