Param(
  [string]$Root = "$PSScriptRoot\slh_stack-main"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Section($t){ Write-Host "`n=== $t ===" -ForegroundColor Cyan }
function Write-Ok($t){ Write-Host "✔ $t" -ForegroundColor Green }
function Write-Warn($t){ Write-Host "⚠ $t" -ForegroundColor Yellow }

if (!(Test-Path $Root)) { throw "Path not found: $Root" }
Push-Location $Root

# 1) Read or create .env
$envFile = Join-Path $Root ".env"
if (!(Test-Path $envFile)) {
  Copy-Item ".env.example" $envFile -Force
  Write-Warn "Created .env from .env.example — please fill values if needed."
}

# Helper: get or prompt .env key
function Get-OrPrompt([string]$Key, [string]$Prompt, [switch]$Secret){
  $val = $null
  if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw -Encoding UTF8
    if ($content -match "^\s*$Key\s*=\s*(.*)$"){ $val = ($Matches[1]).Trim() }
  }
  if (!$val) {
    if ($Secret) { $val = Read-Host -AsSecureString $Prompt | ConvertFrom-SecureString -AsPlainText }
    else { $val = Read-Host $Prompt }
    if ($val) {
      if (Test-Path $envFile) {
        $c = Get-Content $envFile -Raw -Encoding UTF8
        if ($c -match "^\s*$Key\s*=") {
          $c = $c -replace "^\s*$Key\s*=.*$", "$Key=$val"
        } else {
          $c += "`r`n$Key=$val"
        }
        [System.IO.File]::WriteAllText($envFile, $c, [System.Text.UTF8Encoding]::new($false))
      }
    }
  }
  return $val
}

Write-Section "Config"
$TOKEN  = Get-OrPrompt "TELEGRAM_BOT_TOKEN" "Enter TELEGRAM_BOT_TOKEN" -Secret
$PUBLIC = Get-OrPrompt "BOT_WEBHOOK_PUBLIC_BASE" "Public base URL (https):"
if (!$PUBLIC.StartsWith("https://")) { throw "BOT_WEBHOOK_PUBLIC_BASE must start with https://" }
$PATH   = Get-OrPrompt "BOT_WEBHOOK_PATH" "Webhook path (default /tg):"
if (!$PATH) { $PATH = "/tg" }
$SECRET = Get-OrPrompt "BOT_WEBHOOK_SECRET" "Webhook secret (letters/digits/_- only):"
if (!($SECRET -match '^[A-Za-z0-9_-]+$')){ throw "Invalid BOT_WEBHOOK_SECRET" }
$PORT   = Get-OrPrompt "BOT_PORT" "Listen port (default 8080):"
if (!$PORT){ $PORT = "8080" }

# 2) Export env for current session
$pairs = @{
  "BOT_MODE"="webhook";
  "BOT_WEBHOOK_PUBLIC_BASE"=$PUBLIC;
  "BOT_WEBHOOK_PATH"=$PATH;
  "BOT_WEBHOOK_SECRET"=$SECRET;
  "BOT_PORT"=$PORT;
  "TELEGRAM_BOT_TOKEN"=$TOKEN;
  "SLH_API_BASE"=(Get-OrPrompt "SLH_API_BASE" "SLH API base (keep default if unsure):");
}
foreach($k in $pairs.Keys){ $env:$k = $pairs[$k] }

Write-Ok "Session env set. URL = $PUBLIC$PATH"

# 3) Python venv + deps
Write-Section "Python environment"
$venv = Join-Path $Root ".venv"
if (!(Test-Path $venv)){
  py -3 -m venv $venv
  Write-Ok "Virtualenv created"
}
$pyExe = Join-Path $venv "Scripts\python.exe"
& $pyExe -m pip install --upgrade pip wheel
& $pyExe -m pip install -r (Join-Path $Root "requirements.txt")

# 4) Preflight: show getMe
Write-Section "Telegram getMe"
$me = Invoke-RestMethod -Method Post -Uri ("https://api.telegram.org/bot{0}/getMe" -f $TOKEN)
$me | ConvertTo-Json -Depth 6

# 5) Set webhook (delete + set)
Write-Section "Configure Webhook"
$url = "$PUBLIC$PATH"
Invoke-RestMethod -Method Post -Uri ("https://api.telegram.org/bot{0}/deleteWebhook" -f $TOKEN) | Out-Null
$sw = Invoke-RestMethod -Method Post -Uri ("https://api.telegram.org/bot{0}/setWebhook" -f $TOKEN) -Body @{ url=$url; secret_token=$SECRET }
$info = Invoke-RestMethod -Method Get -Uri ("https://api.telegram.org/bot{0}/getWebhookInfo" -f $TOKEN)
$info | ConvertTo-Json -Depth 6

# 6) Run bot (webhook mode). Press Ctrl+C to stop.
Write-Section "Run bot"
Write-Host "Listening on 0.0.0.0:$PORT  →  $url"
& $pyExe -X utf8 ".\bot\run_admin_bot.py"
Pop-Location
