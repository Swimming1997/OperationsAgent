$script:CentralRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$script:RepoRoot = (Resolve-Path (Join-Path $script:CentralRoot "..")).Path
$script:CentralRuntimeDir = Join-Path $script:CentralRoot "logs\runtime"
$script:CentralFastApiPort = 8000
$script:CentralVitePort = 5173
$script:CentralRootRegex = [regex]::Escape($script:CentralRoot)

function Write-CentralStep {
    param([string]$Message)
    Write-Host "[Central] $Message"
}

function Ensure-CentralRuntimeDir {
    if (!(Test-Path -LiteralPath $script:CentralRuntimeDir)) {
        New-Item -ItemType Directory -Path $script:CentralRuntimeDir -Force | Out-Null
    }
}

function Get-CentralPidFilePath {
    param([string]$Name)
    Join-Path $script:CentralRuntimeDir "$Name.pid"
}

function Save-CentralRuntimePid {
    param([string]$Name, [int]$ProcessId)
    if ($ProcessId -le 0) { return }
    Ensure-CentralRuntimeDir
    Set-Content -LiteralPath (Get-CentralPidFilePath -Name $Name) -Value $ProcessId -Encoding ascii -NoNewline
}

function Read-CentralRuntimePid {
    param([string]$Name)
    $path = Get-CentralPidFilePath -Name $Name
    if (!(Test-Path -LiteralPath $path)) { return $null }
    $text = (Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue).Trim()
    if ($text -match '^\d+$') { return [int]$text }
    return $null
}

function Remove-CentralRuntimePid {
    param([string]$Name)
    $path = Get-CentralPidFilePath -Name $Name
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    }
}

function Get-PidsByPort {
    param([int]$Port)
    $ids = @()
    try {
        $ids += @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique)
    }
    catch {}
    $rows = @(netstat -ano -p tcp | Select-String -Pattern "LISTENING")
    foreach ($row in $rows) {
        $parts = @($row.Line -split "\s+" | Where-Object { $_ })
        if ($parts.Length -ge 5 -and $parts[1] -match ":$Port$" -and $parts[3] -eq "LISTENING") {
            $ids += [int]$parts[-1]
        }
    }
    return @($ids | Where-Object { $_ -and $_ -ne $PID } | Select-Object -Unique)
}

function Get-ProcessCommandLine {
    param([int]$ProcessId)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction Stop
        return $proc.CommandLine
    }
    catch {
        return $null
    }
}

function Test-CentralOwnedProcess {
    param([int]$ProcessId)
    if ($ProcessId -eq $PID) { return $false }
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    $cmd = Get-ProcessCommandLine -ProcessId $ProcessId
    if ($cmd -and $cmd -match $script:CentralRootRegex) { return $true }
    $path = $proc.Path
    if ($path -and $path -match [regex]::Escape("$($script:RepoRoot)\.venv\")) { return $true }
    $fastApi = @(Get-PidsByPort -Port $script:CentralFastApiPort) -contains $ProcessId
    $vite = @(Get-PidsByPort -Port $script:CentralVitePort) -contains $ProcessId
    if ($fastApi -and $proc.ProcessName -match '^(python|pythonw)$') { return $true }
    if ($vite -and $proc.ProcessName -match '^(node|npm)$') { return $true }
    return $false
}

function Write-CentralPortDiagnostics {
    param([int[]]$Ports)
    foreach ($port in $Ports) {
        foreach ($processId in @(Get-PidsByPort -Port $port)) {
            $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
            $name = if ($proc) { $proc.ProcessName } else { "unknown" }
            Write-CentralStep "Port $port is still in use by PID=$processId ($name). This script will not stop processes without a central PID file."
        }
    }
}

function Stop-CentralProcessTree {
    param([int]$ProcessId)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if (-not $proc) { return $false }
    if (-not (Test-CentralOwnedProcess -ProcessId $ProcessId)) {
        Write-CentralStep "Skip PID $ProcessId ($($proc.ProcessName)): not a central process"
        return $false
    }
    Write-CentralStep "Stopping $($proc.ProcessName) PID=$ProcessId"
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    return -not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-CentralPidFile {
    param([string]$Name)
    $processId = Read-CentralRuntimePid -Name $Name
    Remove-CentralRuntimePid -Name $Name
    if ($processId) { return Stop-CentralProcessTree -ProcessId $processId }
    return $false
}

function Stop-CentralStack {
    Ensure-CentralRuntimeDir
    Stop-CentralPidFile -Name "vite" | Out-Null
    Stop-CentralPidFile -Name "fastapi" | Out-Null
    Start-Sleep -Milliseconds 800
    Write-CentralPortDiagnostics -Ports @($script:CentralFastApiPort, $script:CentralVitePort)
    return @{
        FastApiFree = (@(Get-PidsByPort -Port $script:CentralFastApiPort).Count -eq 0)
        ViteFree = (@(Get-PidsByPort -Port $script:CentralVitePort).Count -eq 0)
    }
}
