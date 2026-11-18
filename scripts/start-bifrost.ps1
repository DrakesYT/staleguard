# Starts the Bifrost gateway on http://localhost:8080 (needs Node.js).
# First run: open http://localhost:8080 -> Providers -> add your Gemini / Groq / OpenAI keys.
# Config and request logs are kept in .\bifrost-data
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path "$root\bifrost-data" | Out-Null
npx -y @maximhq/bifrost -app-dir "$root\bifrost-data" -port 8080
