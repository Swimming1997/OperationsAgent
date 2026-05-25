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
        return (Get-Process -Id $ProcessId -ErrorAction Stop).CommandLine
    }
    catch {
        return $null
    }
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
