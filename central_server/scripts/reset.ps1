# AMiracle one-click demo reset

$ErrorActionPreference = "Continue"
$exitCode = 0

$CentralRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $CentralRoot "..")).Path
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ResetScript = Join-Path $CentralRoot "scripts\reset_demo_environment.py"

function Write-ResetStep([string]$Message) {
    Write-Host "[AMiracle] $Message"
}

try {
    Set-Location -LiteralPath $CentralRoot

    if (!(Test-Path -LiteralPath $PythonExe)) {
        Write-ResetStep "ERROR: .venv\Scripts\python.exe not found"
        $exitCode = 1
        return
    }

    Write-Host ""
    Write-Host "========================================================================"
    Write-Host " Demo environment reset"
    Write-Host "========================================================================"
    Write-Host "  1. Stop services"
    Write-Host "  2. Type YES to confirm"
    Write-Host "  3. Backup SQLite"
    Write-Host "  4. Clear business data"
    Write-Host "  5. Keep Local Agent Chrome profiles"
    Write-Host ""

    Write-ResetStep "[1/5] Stopping central..."
    $StopCentral = Join-Path $CentralRoot "scripts\stop.ps1"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StopCentral
    if ($LASTEXITCODE -ne 0) {
        Write-ResetStep "WARN: stop incomplete; run 分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1 first if reset fails"
    }
    Write-Host ""

    Write-Host "------------------------------------------------------------------------"
    Write-Host " Will delete: users, accounts, tasks, intel, runs, rules, benchmarks"
    Write-Host " Will keep: Local Agent Chrome profiles under local_agent\profiles\"
    Write-Host " Keeps: default roles; does NOT delete source or .venv"
    Write-Host "------------------------------------------------------------------------"
    $answer = Read-Host "Type YES to confirm reset (anything else cancels)"
    if ($answer -ne "YES") {
        Write-ResetStep "Cancelled. No data changed."
        return
    }

    Write-ResetStep "[2/5] Backing up DB and clearing data..."
    Write-Host ""

    & $PythonExe $ResetScript @("--apply", "--yes", "--backup-db")
    $exitCode = $LASTEXITCODE

    Write-Host ""
    if ($exitCode -eq 0) {
        Write-ResetStep "[OK] Reset done. Run cd central_server; .\scripts\start.ps1, then cd local_agent; .\scripts\start.ps1 if needed."
    }
    elseif ($exitCode -eq 3) {
        Write-ResetStep "[FAIL] Logs locked. Run 分别运行 local_agent\scripts\stop.ps1 和 central_server\scripts\stop.ps1 then cd central_server; .\scripts\reset.ps1."
    }
    else {
        Write-ResetStep "[FAIL] Exit code: $exitCode"
    }
}
catch {
    Write-Host ""
    Write-ResetStep "ERROR: $($_.Exception.Message)"
    $exitCode = 1
}

exit $exitCode
