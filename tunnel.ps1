# Start GitHub MCP server with ngrok tunnel for personal remote access
# Usage: .\tunnel.ps1 [-Port 8080] [-ReadOnly]

param(
    [int]$Port = $( if ($env:MCP_PORT) { $env:MCP_PORT } else { 8080 } ),
    [switch]$ReadOnly
)

$ErrorActionPreference = "Stop"

# Check prerequisites
if (-not (Get-Command ngrok -ErrorAction SilentlyContinue)) {
    Write-Host "❌ ngrok not found. Install from: https://ngrok.com/download" -ForegroundColor Red
    Write-Host "   Then run: ngrok config add-authtoken YOUR_TOKEN"
    exit 1
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "❌ GitHub CLI (gh) not found. Install from: https://cli.github.com/" -ForegroundColor Red
    exit 1
}

# Generate API key if not set
if (-not $env:MCP_API_KEY) {
    $env:MCP_API_KEY = python -c "import secrets; print(secrets.token_urlsafe(32))"
    Write-Host "🔑 Generated MCP_API_KEY: $env:MCP_API_KEY" -ForegroundColor Yellow
    Write-Host "   Save this - you'll need it to connect from Claude."
}

Write-Host ""
Write-Host "🚀 Starting GitHub MCP Server on port $Port..." -ForegroundColor Green
if ($ReadOnly) {
    $env:READ_ONLY = "true"
    Write-Host "   Mode: READ-ONLY" -ForegroundColor Yellow
} else {
    Write-Host "   Mode: FULL ACCESS" -ForegroundColor Cyan
}

# Start server
$env:MCP_TRANSPORT = "sse"
$env:MCP_PORT = $Port
$serverJob = Start-Process python -ArgumentList "server.py" -NoNewWindow -PassThru

Start-Sleep -Seconds 2

# Start ngrok
Write-Host "🌐 Starting ngrok tunnel..." -ForegroundColor Green
$ngrokJob = Start-Process ngrok -ArgumentList "http $Port" -NoNewWindow -PassThru

Start-Sleep -Seconds 3

# Get tunnel URL
try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
    $ngrokUrl = $tunnels.tunnels[0].public_url
} catch {
    $ngrokUrl = "Check http://127.0.0.1:4040"
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "✅ MCP Server is running!" -ForegroundColor Green
Write-Host ""
Write-Host "   Local:  http://localhost:$Port/sse"
Write-Host "   Tunnel: $ngrokUrl/sse"
Write-Host ""
Write-Host "   API Key: $env:MCP_API_KEY" -ForegroundColor Yellow
Write-Host ""
Write-Host "   Add to Claude.ai MCP settings:"
Write-Host "   URL: $ngrokUrl/sse"
Write-Host "   Header: Authorization: Bearer $env:MCP_API_KEY"
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop"

# Wait and cleanup
try {
    $serverJob | Wait-Process
} finally {
    Write-Host "`n🛑 Shutting down..." -ForegroundColor Yellow
    Stop-Process -Id $serverJob.Id -ErrorAction SilentlyContinue
    Stop-Process -Id $ngrokJob.Id -ErrorAction SilentlyContinue
    Write-Host "Done."
}
