# Easy BDD MCP — one-command setup for Windows.
#
# Engineers run this in PowerShell (token comes from Mark Fomin):
#   $env:EASYBDD_TOKEN="<token>"; irm http://192.168.100.100:8092/setup.ps1 | iex
# If EASYBDD_TOKEN is not set, the script asks for it interactively.
#
# What it does:
#   1. Checks the Easy BDD MCP server is reachable and the token is valid.
#   2. Configures Claude Code (if installed).
#   3. Configures Claude Desktop via the mcp-remote bridge, installing
#      Node.js with winget if it's missing.
# It never removes existing MCP servers from your config; it only adds/updates
# the "easybdd" entry. A timestamped backup of your config is made first.
#
# Two Windows-specific quirks this script has to work around, both of which
# make the script *report* success while the app silently never picks up the
# config (see anthropics/claude-code#25075 and #26073):
#   - The Claude Desktop installer registers a "Claude.exe" alias under
#     %LOCALAPPDATA%\Microsoft\WindowsApps, which sits ahead of the npm-installed
#     Claude Code CLI on PATH. A plain `claude` lookup can resolve to Desktop
#     instead of the CLI, so `claude mcp add` silently launches the Desktop app
#     instead of registering anything.
#   - Fresh Claude Desktop installs use MSIX packaging, which redirects
#     %APPDATA%\Claude\* to a virtualized path under
#     %LOCALAPPDATA%\Packages\Claude_<hash>\LocalCache\Roaming\Claude\. The app
#     reads its config from the virtualized path, not the documented one, so
#     writing only to %APPDATA%\Claude never actually reaches the app.

$ErrorActionPreference = "Stop"
$McpUrl = if ($env:EASYBDD_MCP_URL) { $env:EASYBDD_MCP_URL } else { "http://192.168.100.100:8092/mcp" }
$Token  = $env:EASYBDD_TOKEN
$Configured = @()

function Say($m)  { Write-Host "==> $m" -ForegroundColor Blue }
function Ok($m)   { Write-Host " OK $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  X $m" -ForegroundColor Red }

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

# Refresh PATH up front: if the user just installed Claude Code (or Node) in
# this same terminal session, a stale PATH would make Get-Command miss it.
Refresh-Path

Say "Easy BDD MCP setup (server: $McpUrl)"

# --- 1. Reachability ---------------------------------------------------------
try {
    Invoke-WebRequest -Uri $McpUrl -Method Get -TimeoutSec 8 -UseBasicParsing | Out-Null
    Ok "Server is reachable."
} catch {
    if ($_.Exception.Response) {
        # Any HTTP response (even 401/4xx/5xx) means the server is reachable.
        Ok "Server is reachable."
    } else {
        Fail "Cannot reach $McpUrl"
        Write-Host "   Make sure you are on the office network or VPN, then run this again."
        return
    }
}

# --- 2. Access token ---------------------------------------------------------
if (-not $Token) {
    $Token = Read-Host "Paste the Easy BDD access token (ask Mark Fomin)"
}
if (-not $Token) {
    Fail "No access token provided."
    Write-Host "   Ask Mark Fomin for the token, then run this again."
    return
}

$initBody = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"setup-check","version":"0"}}}'
$tokenOk = $true
try {
    Invoke-WebRequest -Uri $McpUrl -Method Post -TimeoutSec 8 -UseBasicParsing `
        -Headers @{ Authorization = "Bearer $Token"; Accept = "application/json, text/event-stream" } `
        -ContentType "application/json" -Body $initBody | Out-Null
} catch {
    $resp = $_.Exception.Response
    if ($resp -and [int]$resp.StatusCode -eq 401) { $tokenOk = $false }
    # Any other HTTP error still means the token itself was accepted.
}
if (-not $tokenOk) {
    Fail "The access token was rejected by the server."
    Write-Host "   Double-check it with Mark Fomin and run this again."
    return
}
Ok "Access token accepted."

# --- 3. Claude Code (CLI / IDE) ----------------------------------------------
# Skip the WindowsApps "Claude.exe" alias (that's Desktop, not the CLI - see
# header note) and use whatever real CLI resolves first on PATH, calling it by
# full path so we can't be fooled by alias ordering.
$claudeCliCmd = Get-Command claude -All -ErrorAction SilentlyContinue |
                Where-Object { $_.Source -notlike "*\Microsoft\WindowsApps\*" } |
                Select-Object -First 1

if ($claudeCliCmd) {
    & $claudeCliCmd.Source mcp remove --scope user easybdd *>$null
    & $claudeCliCmd.Source mcp add --scope user --transport http easybdd $McpUrl --header "Authorization: Bearer $Token" *>$null
    # Native commands don't throw into try/catch on non-zero exit - check
    # $LASTEXITCODE explicitly or a failed add silently reports as "OK".
    if ($LASTEXITCODE -eq 0) {
        Ok "Claude Code configured (user scope)."
        $Configured += "Claude Code"
    } else {
        Warn "Claude Code is installed but 'claude mcp add' failed (exit $LASTEXITCODE) - configure it manually later."
    }
} elseif (Get-Command claude -ErrorAction SilentlyContinue) {
    Warn "A 'claude' command was found, but it points to the Claude Desktop app, not the Claude Code CLI (a known Windows PATH conflict - Desktop's WindowsApps alias shadows the CLI). Skipping Claude Code setup - configure it manually with 'claude mcp add' from a terminal where the CLI resolves first."
}

# --- 4. Node.js (needed for the Claude Desktop bridge) ------------------------
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Say "Node.js is required for Claude Desktop - attempting to install it with winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
        Refresh-Path
    }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail "Node.js could not be installed automatically."
    Write-Host "   Install it from https://nodejs.org (choose LTS), then run this again."
    if ($Configured.Count -gt 0) { Warn "($($Configured -join ', ') was still configured successfully.)" }
    return
}
Ok "Node.js found: $(node --version)"

# --- 5. Claude Desktop config -------------------------------------------------
# Fresh (MSIX-packaged) installs redirect %APPDATA%\Claude to a virtualized
# path and read their config from *there*, not from the documented location
# (see header note / anthropics/claude-code#26073). Write both so the config
# reaches the app regardless of which packaging this machine has:
#   - %APPDATA%\Claude\claude_desktop_config.json           (documented path;
#     also what "Edit Config" opens, and what older/non-MSIX installs read)
#   - %LOCALAPPDATA%\Packages\Claude_<hash>\LocalCache\Roaming\Claude\...
#     (the virtualized path MSIX installs actually read from)
$DesktopDir = Join-Path $env:APPDATA "Claude"
New-Item -ItemType Directory -Force -Path $DesktopDir | Out-Null
$ConfigPaths = [System.Collections.Generic.List[string]]::new()
$ConfigPaths.Add((Join-Path $DesktopDir "claude_desktop_config.json"))

$PkgRoot = Join-Path $env:LOCALAPPDATA "Packages"
if (Test-Path $PkgRoot) {
    Get-ChildItem -Path $PkgRoot -Directory -Filter "Claude_*" -ErrorAction SilentlyContinue | ForEach-Object {
        $ConfigPaths.Add((Join-Path $_.FullName "LocalCache\Roaming\Claude\claude_desktop_config.json"))
    }
}

# Token is passed via env and expanded by mcp-remote itself; keeping the header
# argument free of spaces avoids a Claude Desktop arg-parsing bug on Windows.
$serverEntry = [pscustomobject]@{
    command = "npx"
    args    = @("-y", "mcp-remote", $McpUrl, "--allow-http", "--transport", "http-only",
                "--header", 'Authorization:${EASYBDD_AUTH}')
    env     = [pscustomobject]@{ EASYBDD_AUTH = "Bearer $Token" }
}

$WrittenPaths = @()
foreach ($ConfigPath in $ConfigPaths) {
    New-Item -ItemType Directory -Force -Path (Split-Path $ConfigPath -Parent) | Out-Null

    $cfg = $null
    if (Test-Path $ConfigPath) {
        Copy-Item $ConfigPath "$ConfigPath.backup.$(Get-Date -Format yyyyMMddHHmmss)"
        Ok "Backed up existing config: $ConfigPath"
        try { $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json } catch { $cfg = $null }
    }
    if ($null -eq $cfg) { $cfg = [pscustomobject]@{} }
    if (-not $cfg.PSObject.Properties["mcpServers"]) {
        $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{})
    }
    if ($cfg.mcpServers.PSObject.Properties["easybdd"]) {
        $cfg.mcpServers.easybdd = $serverEntry
    } else {
        $cfg.mcpServers | Add-Member -NotePropertyName easybdd -NotePropertyValue $serverEntry
    }

    try {
        $cfg | ConvertTo-Json -Depth 20 | Set-Content -Path $ConfigPath -Encoding UTF8
        Ok "Claude Desktop configured: $ConfigPath"
        $WrittenPaths += $ConfigPath
    } catch {
        Warn "Could not write $ConfigPath - $($_.Exception.Message)"
    }
}

if ($WrittenPaths.Count -gt 0) {
    $Configured += "Claude Desktop"
} else {
    Fail "Could not write any Claude Desktop config file."
}

# Pre-download the bridge so Claude Desktop's first launch isn't slow.
Say "Pre-downloading the mcp-remote bridge (one-time)..."
try { npx -y mcp-remote --help 2>$null | Out-Null } catch {}

# --- Done ----------------------------------------------------------------------
Write-Host ""
Ok "Setup complete - configured: $($Configured -join ' and ')"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. FULLY quit Claude Desktop (system tray -> Quit), then reopen it."
Write-Host "     If Claude Desktop is not installed yet, get it from https://claude.ai/download"
Write-Host "  2. In a new chat, click the tools (sliders) icon under the message box -"
Write-Host "     you should see 'easybdd' listed."
Write-Host "  3. Try asking: 'Using the easybdd tools, list the available tests.'"
