$script:LocalAgentRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:RepoRoot = (Resolve-Path (Join-Path $script:LocalAgentRoot "..")).Path
$script:LocalAgentRuntimeDir = Join-Path $script:LocalAgentRoot "logs\runtime"

function Write-LocalAgentStep {
    param([string]$Message)
    Write-Host "[Local Agent] $Message"
}

function Ensure-LocalAgentRuntimeDir {
    if (!(Test-Path -LiteralPath $script:LocalAgentRuntimeDir)) {
        New-Item -ItemType Directory -Path $script:LocalAgentRuntimeDir -Force | Out-Null
    }
}

function Get-LocalAgentPidFilePath {
    param([string]$Name)
    Join-Path $script:LocalAgentRuntimeDir "$Name.pid"
}

function Read-LocalAgentPid {
    param([string]$Name)
    $path = Get-LocalAgentPidFilePath -Name $Name
    if (!(Test-Path -LiteralPath $path)) { return $null }
    $text = (Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue).Trim()
    if ($text -match '^\d+$') { return [int]$text }
    return $null
}

function Remove-LocalAgentPid {
    param([string]$Name)
    $path = Get-LocalAgentPidFilePath -Name $Name
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    try {
        $line = (Get-Process -Id $ProcessId -ErrorAction Stop).CommandLine
        if ($line) { return $line }
    }
    catch {
        # fall through to WMI
    }
    try {
        return (Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop).CommandLine
    }
    catch {
        return $null
    }
}

function Get-ConfigBridgeSettings {
    param([string]$ConfigPath)
    $preferredPort = 18765
    $bindHost = "127.0.0.1"
    $maxAttempts = 10
    if (!(Test-Path -LiteralPath $ConfigPath)) {
        return @{ Host = $bindHost; PreferredPort = $preferredPort; MaxAttempts = $maxAttempts }
    }
    $content = Get-Content -LiteralPath $ConfigPath -Raw -ErrorAction SilentlyContinue
    if ($content -match '(?ms)\[local_bridge\][^\[]*?^\s*port\s*=\s*(\d+)') {
        $preferredPort = [int]$Matches[1]
    }
    if ($content -match '(?ms)\[local_bridge\][^\[]*?^\s*host\s*=\s*"([^"]+)"') {
        $bindHost = $Matches[1]
    }
    return @{ Host = $bindHost; PreferredPort = $preferredPort; MaxAttempts = $maxAttempts }
}

function Get-BridgePortListenerPid {
    param([string]$BindHost = "127.0.0.1", [int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalAddress $BindHost -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($conn) { return [int]$conn.OwningProcess }
    }
    catch {
        # fall back to netstat
    }
    $escapedHost = [regex]::Escape($BindHost)
    foreach ($line in (netstat -ano | Select-String "$escapedHost`:$Port\s+")) {
        if ($line.Line -notmatch 'LISTENING') { continue }
        $parts = ($line.Line -replace '\s+', ' ').Trim().Split(' ')
        if ($parts.Length -ge 1 -and $parts[-1] -match '^\d+$') {
            return [int]$parts[-1]
        }
    }
    return $null
}

function Test-BridgePortHealthy {
    param([string]$BindHost = "127.0.0.1", [int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://${BindHost}:$Port/healthz" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Get-BridgeDiscoverAgentIds {
    param([string]$BindHost = "127.0.0.1", [int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://${BindHost}:$Port/bridge/agents/discover" -UseBasicParsing -TimeoutSec 2
        $payload = $response.Content | ConvertFrom-Json
        $ids = @()
        foreach ($item in @($payload.items)) {
            $agentId = [string]$item.agent_id
            if ($agentId.Trim().Length -gt 0) { $ids += $agentId.Trim() }
        }
        return $ids
    }
    catch {
        return @()
    }
}

function Clear-StaleBridgePortOccupants {
    param(
        [string]$BindHost = "127.0.0.1",
        [int]$PreferredPort = 18765,
        [int]$MaxAttempts = 10
    )
    Ensure-LocalAgentRuntimeDir
    $trackedPid = Read-LocalAgentPid -Name "local-agent"
    $released = 0

    for ($offset = 0; $offset -lt $MaxAttempts; $offset++) {
        $port = $PreferredPort + $offset
        $listenerPid = Get-BridgePortListenerPid -BindHost $BindHost -Port $port
        if (-not $listenerPid) { continue }

        $healthy = Test-BridgePortHealthy -BindHost $BindHost -Port $port
        $agentIds = if ($healthy) { Get-BridgeDiscoverAgentIds -BindHost $BindHost -Port $port } else { @() }
        $hasDiscoverableAgent = $agentIds.Count -gt 0

        # 健康的 discover 实例视为合法多 Agent 并存（各占不同 bridge 端口），不自动清理。
        if ($healthy -and $hasDiscoverableAgent) {
            continue
        }

        if (-not (Test-LocalAgentOwnedProcess -ProcessId $listenerPid)) {
            Write-LocalAgentStep "Bridge port $port is used by PID $listenerPid (not Local Agent); skip auto-release"
            continue
        }

        if (-not $healthy) {
            Write-LocalAgentStep "Releasing bridge port $port (PID $listenerPid): health check failed"
        }
        else {
            Write-LocalAgentStep "Releasing bridge port $port (PID $listenerPid): no discoverable agent"
        }

        if (Stop-LocalAgentProcess -ProcessId $listenerPid) {
            $released++
            if ($trackedPid -eq $listenerPid) {
                Remove-LocalAgentPid -Name "local-agent"
                $trackedPid = $null
            }
        }
    }

    if ($released -gt 0) {
        Write-LocalAgentStep "Released $released stale bridge port occupant(s)"
        Start-Sleep -Milliseconds 400
    }
    return @{ ReleasedCount = $released }
}

function Test-LocalAgentOwnedProcess {
    param([int]$ProcessId)
    if ($ProcessId -eq $PID) { return $false }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    $cmd = Get-ProcessCommandLine -ProcessId $ProcessId
    if ($cmd -and $cmd -match [regex]::Escape($script:LocalAgentRoot)) { return $true }
    if ($cmd -and $cmd -match 'run_local_agent\.py') { return $true }
    if ($cmd -and $cmd -match 'remote-debugging-port=.*profiles\\accounts') { return $true }
    return $false
}

function Stop-LocalAgentProcess {
    param([int]$ProcessId)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    if (-not (Test-LocalAgentOwnedProcess -ProcessId $ProcessId)) {
        Write-LocalAgentStep "Skip PID $ProcessId ($($proc.ProcessName)): not a Local Agent process"
        return $false
    }
    Write-LocalAgentStep "Stopping $($proc.ProcessName) PID=$ProcessId"
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    return -not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-LocalAgentStack {
    Ensure-LocalAgentRuntimeDir
    $count = 0
    foreach ($name in @("local-agent", "chrome-cdp")) {
        $processId = Read-LocalAgentPid -Name $name
        Remove-LocalAgentPid -Name $name
        if ($processId -and (Stop-LocalAgentProcess -ProcessId $processId)) { $count++ }
    }
    return @{ StoppedCount = $count }
}
