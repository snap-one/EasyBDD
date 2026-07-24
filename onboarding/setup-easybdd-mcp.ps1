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
#   4. Configures VS Code GitHub Copilot's MCP user config.
# It never removes existing MCP servers from your config; it only adds/updates
# the "easybdd" entry. A timestamped backup of your config is made first.

$ErrorActionPreference = "Stop"
$McpUrl = if ($env:EASYBDD_MCP_URL) { $env:EASYBDD_MCP_URL } else { "http://192.168.100.100:8092/mcp" }
$Token  = $env:EASYBDD_TOKEN
$Configured = @()

function Say($m)  { Write-Host "==> $m" -ForegroundColor Blue }
function Ok($m)   { Write-Host " OK $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  ! $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "  X $m" -ForegroundColor Red }

function Ensure-JsonObject($obj) {
    if ($null -eq $obj) { return [pscustomobject]@{} }
    if ($obj -is [System.Collections.IDictionary]) {
        $newObj = [pscustomobject]@{}
        foreach ($k in $obj.Keys) {
            $newObj | Add-Member -NotePropertyName ([string]$k) -NotePropertyValue $obj[$k]
        }
        return $newObj
    }
    if ($obj -is [System.Management.Automation.PSCustomObject]) { return $obj }
    return [pscustomobject]@{}
}

function Ensure-NotePropertyObject($obj, $propertyName) {
    if (-not $obj.PSObject.Properties[$propertyName] -or
        $null -eq $obj.$propertyName -or
        -not ($obj.$propertyName -is [System.Management.Automation.PSCustomObject]) -and
        -not ($obj.$propertyName -is [System.Collections.IDictionary])) {
        if ($obj.PSObject.Properties[$propertyName]) {
            $obj.$propertyName = [pscustomobject]@{}
        } else {
            $obj | Add-Member -NotePropertyName $propertyName -NotePropertyValue ([pscustomobject]@{})
        }
    }
}

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

# --- 2.5 Jenkins MCP (optional; credentials stay on the server) ----------------
# The server hands out the Jenkins MCP endpoint and a ready-made Authorization
# header (gated by the same access token). If Jenkins isn't configured
# server-side, this 404s and we simply skip it.
$JenkinsUrl = ""
$JenkinsAuth = ""
try {
    $jconf = Invoke-RestMethod -Uri "$($McpUrl -replace '/mcp$','')/jenkins-mcp-config" `
        -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 8 -UseBasicParsing
    if ($jconf.url -and $jconf.authorization) {
        $JenkinsUrl  = $jconf.url
        $JenkinsAuth = $jconf.authorization
        Ok "Jenkins MCP is enabled on the server - will configure it too."
    }
} catch {
    Warn "Jenkins MCP not enabled on the server - skipping that part."
}

# --- 2.6 Jira MCP (optional; credentials stay on the server) ------------------
# Same idea as Jenkins: the server hands out the self-hosted Jira MCP endpoint
# and a ready-made Authorization header. 404s and is skipped if not configured.
$JiraUrl = ""
$JiraAuth = ""
try {
    $jiraConf = Invoke-RestMethod -Uri "$($McpUrl -replace '/mcp$','')/jira-mcp-config" `
        -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 8 -UseBasicParsing
    if ($jiraConf.url -and $jiraConf.authorization) {
        $JiraUrl  = $jiraConf.url
        $JiraAuth = $jiraConf.authorization
        Ok "Jira MCP is enabled on the server - will configure it too."
    }
} catch {
    Warn "Jira MCP not enabled on the server - skipping that part."
}

# --- 2.7 Confluence MCP (optional; credentials stay on the server) -----------
# Same idea as Jenkins/Jira: the server hands out the self-hosted Confluence
# MCP endpoint and a ready-made Authorization header. 404s and is skipped if
# not configured.
$ConfluenceUrl = ""
$ConfluenceAuth = ""
try {
    $confConf = Invoke-RestMethod -Uri "$($McpUrl -replace '/mcp$','')/confluence-mcp-config" `
        -Headers @{ Authorization = "Bearer $Token" } -TimeoutSec 8 -UseBasicParsing
    if ($confConf.url -and $confConf.authorization) {
        $ConfluenceUrl  = $confConf.url
        $ConfluenceAuth = $confConf.authorization
        Ok "Confluence MCP is enabled on the server - will configure it too."
    }
} catch {
    Warn "Confluence MCP not enabled on the server - skipping that part."
}

# --- 3. Claude Code (CLI / IDE) ----------------------------------------------
if (Get-Command claude -ErrorAction SilentlyContinue) {
    try {
        claude mcp remove --scope user easybdd 2>$null | Out-Null
    } catch {}
    try {
        claude mcp add --scope user --transport http easybdd $McpUrl --header "Authorization: Bearer $Token" | Out-Null
        Ok "Claude Code configured (user scope)."
        $Configured += "Claude Code"
    } catch {
        Warn "Claude Code is installed but 'claude mcp add' failed - configure it manually later."
    }
    if ($JenkinsUrl) {
        try {
            claude mcp remove --scope user jenkins 2>$null | Out-Null
        } catch {}
        try {
            claude mcp add --scope user --transport http jenkins $JenkinsUrl --header "Authorization: $JenkinsAuth" | Out-Null
            Ok "Claude Code: jenkins MCP configured."
        } catch {
            Warn "Could not add the jenkins MCP server to Claude Code."
        }
    }
    if ($JiraUrl) {
        try {
            claude mcp remove --scope user jira 2>$null | Out-Null
        } catch {}
        try {
            claude mcp add --scope user --transport http jira $JiraUrl --header "Authorization: $JiraAuth" | Out-Null
            Ok "Claude Code: jira MCP configured."
        } catch {
            Warn "Could not add the jira MCP server to Claude Code."
        }
    }
    if ($ConfluenceUrl) {
        try {
            claude mcp remove --scope user confluence 2>$null | Out-Null
        } catch {}
        try {
            claude mcp add --scope user --transport http confluence $ConfluenceUrl --header "Authorization: $ConfluenceAuth" | Out-Null
            Ok "Claude Code: confluence MCP configured."
        } catch {
            Warn "Could not add the confluence MCP server to Claude Code."
        }
    }
}

# --- 3.5 GitHub Copilot in VS Code (native MCP) ------------------------------
# Writes VS Code user-level MCP config so Copilot Chat can use easybdd tools.
$VsCodeUserDir = if ($env:EASYBDD_VSCODE_USER_DIR) {
    $env:EASYBDD_VSCODE_USER_DIR
} elseif (Test-Path (Join-Path $env:APPDATA "Code\User")) {
    Join-Path $env:APPDATA "Code\User"
} elseif (Test-Path (Join-Path $env:APPDATA "Code - Insiders\User")) {
    Join-Path $env:APPDATA "Code - Insiders\User"
} else {
    Join-Path $env:APPDATA "Code\User"
}

New-Item -ItemType Directory -Force -Path $VsCodeUserDir | Out-Null
$VsCodeConfigPath = Join-Path $VsCodeUserDir "mcp.json"

$vCfg = $null
if (Test-Path $VsCodeConfigPath) {
    Copy-Item $VsCodeConfigPath "$VsCodeConfigPath.backup.$(Get-Date -Format yyyyMMddHHmmss)"
    Ok "Backed up existing VS Code MCP config."
    try { $vCfg = Get-Content $VsCodeConfigPath -Raw | ConvertFrom-Json } catch { $vCfg = $null }
}
$vCfg = Ensure-JsonObject $vCfg
Ensure-NotePropertyObject -obj $vCfg -propertyName "servers"

$easybddVsCodeEntry = [pscustomobject]@{
    type = "http"
    url = $McpUrl
    headers = [pscustomobject]@{ Authorization = "Bearer $Token" }
}
if ($vCfg.servers.PSObject.Properties["easybdd"]) {
    $vCfg.servers.easybdd = $easybddVsCodeEntry
} else {
    $vCfg.servers | Add-Member -NotePropertyName easybdd -NotePropertyValue $easybddVsCodeEntry
}

if ($JenkinsUrl -and $JenkinsAuth) {
    $jenkinsVsCodeEntry = [pscustomobject]@{
        type = "http"
        url = $JenkinsUrl
        headers = [pscustomobject]@{ Authorization = $JenkinsAuth }
    }
    if ($vCfg.servers.PSObject.Properties["jenkins"]) {
        $vCfg.servers.jenkins = $jenkinsVsCodeEntry
    } else {
        $vCfg.servers | Add-Member -NotePropertyName jenkins -NotePropertyValue $jenkinsVsCodeEntry
    }
}

if ($JiraUrl -and $JiraAuth) {
    $jiraVsCodeEntry = [pscustomobject]@{
        type = "http"
        url = $JiraUrl
        headers = [pscustomobject]@{ Authorization = $JiraAuth }
    }
    if ($vCfg.servers.PSObject.Properties["jira"]) {
        $vCfg.servers.jira = $jiraVsCodeEntry
    } else {
        $vCfg.servers | Add-Member -NotePropertyName jira -NotePropertyValue $jiraVsCodeEntry
    }
}

if ($ConfluenceUrl -and $ConfluenceAuth) {
    $confluenceVsCodeEntry = [pscustomobject]@{
        type = "http"
        url = $ConfluenceUrl
        headers = [pscustomobject]@{ Authorization = $ConfluenceAuth }
    }
    if ($vCfg.servers.PSObject.Properties["confluence"]) {
        $vCfg.servers.confluence = $confluenceVsCodeEntry
    } else {
        $vCfg.servers | Add-Member -NotePropertyName confluence -NotePropertyValue $confluenceVsCodeEntry
    }
}

$vCfg | ConvertTo-Json -Depth 20 | Set-Content -Path $VsCodeConfigPath -Encoding UTF8
Ok "GitHub Copilot (VS Code) configured: $VsCodeConfigPath"
$Configured += "GitHub Copilot"

# --- 4. Node.js (needed for the Claude Desktop bridge) ------------------------
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}

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
$DesktopDir = Join-Path $env:APPDATA "Claude"
New-Item -ItemType Directory -Force -Path $DesktopDir | Out-Null
$ConfigPaths = @(
    (Join-Path $DesktopDir "claude_desktop_config.json"),
    (Join-Path $env:LOCALAPPDATA "Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json")
)
$ConfigPaths = $ConfigPaths | Select-Object -Unique

# Token is passed via env and expanded by mcp-remote itself; keeping the header
# argument free of spaces avoids a Claude Desktop arg-parsing bug on Windows.
$serverEntry = [pscustomobject]@{
    command = "npx"
    args    = @("-y", "mcp-remote", $McpUrl, "--allow-http", "--transport", "http-only",
                "--header", 'Authorization:${EASYBDD_AUTH}')
    env     = [pscustomobject]@{ EASYBDD_AUTH = "Bearer $Token" }
}
foreach ($ConfigPath in $ConfigPaths) {
    $ConfigDir = Split-Path -Parent $ConfigPath
    if (-not (Test-Path $ConfigDir)) {
        New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    }

    $cfg = $null
    if (Test-Path $ConfigPath) {
        Copy-Item $ConfigPath "$ConfigPath.backup.$(Get-Date -Format yyyyMMddHHmmss)"
        Ok "Backed up existing config: $ConfigPath"
        try { $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json } catch { $cfg = $null }
    }
    $cfg = Ensure-JsonObject $cfg
    Ensure-NotePropertyObject -obj $cfg -propertyName "mcpServers"

    if ($cfg.mcpServers.PSObject.Properties["easybdd"]) {
        $cfg.mcpServers.easybdd = $serverEntry
    } else {
        $cfg.mcpServers | Add-Member -NotePropertyName easybdd -NotePropertyValue $serverEntry
    }

    if ($JenkinsUrl) {
        $jenkinsEntry = [pscustomobject]@{
            command = "npx"
            args    = @("-y", "mcp-remote", $JenkinsUrl, "--allow-http", "--transport", "http-only",
                        "--header", 'Authorization:${JENKINS_AUTH}')
            env     = [pscustomobject]@{ JENKINS_AUTH = $JenkinsAuth }
        }
        if ($cfg.mcpServers.PSObject.Properties["jenkins"]) {
            $cfg.mcpServers.jenkins = $jenkinsEntry
        } else {
            $cfg.mcpServers | Add-Member -NotePropertyName jenkins -NotePropertyValue $jenkinsEntry
        }
    }

    if ($JiraUrl) {
        $jiraEntry = [pscustomobject]@{
            command = "npx"
            args    = @("-y", "mcp-remote", $JiraUrl, "--allow-http", "--transport", "http-only",
                        "--header", 'Authorization:${JIRA_AUTH}')
            env     = [pscustomobject]@{ JIRA_AUTH = $JiraAuth }
        }
        if ($cfg.mcpServers.PSObject.Properties["jira"]) {
            $cfg.mcpServers.jira = $jiraEntry
        } else {
            $cfg.mcpServers | Add-Member -NotePropertyName jira -NotePropertyValue $jiraEntry
        }
    }

    if ($ConfluenceUrl) {
        $confluenceEntry = [pscustomobject]@{
            command = "npx"
            args    = @("-y", "mcp-remote", $ConfluenceUrl, "--allow-http", "--transport", "http-only",
                        "--header", 'Authorization:${CONFLUENCE_AUTH}')
            env     = [pscustomobject]@{ CONFLUENCE_AUTH = $ConfluenceAuth }
        }
        if ($cfg.mcpServers.PSObject.Properties["confluence"]) {
            $cfg.mcpServers.confluence = $confluenceEntry
        } else {
            $cfg.mcpServers | Add-Member -NotePropertyName confluence -NotePropertyValue $confluenceEntry
        }
    }

    $cfg | ConvertTo-Json -Depth 20 | Set-Content -Path $ConfigPath -Encoding UTF8
    Ok "Claude Desktop configured: $ConfigPath"
}
$Configured += "Claude Desktop"

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
Write-Host "  4. For GitHub Copilot, restart VS Code (or run 'Developer: Reload Window')"
Write-Host "     then ask Copilot Chat: 'Using the easybdd tools, list the available tests.'"
