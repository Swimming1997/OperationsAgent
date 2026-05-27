param(
    [string]$Config = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptPath = Join-Path $repoRoot "local_agent\scripts\start.ps1"

if (!(Test-Path -LiteralPath $scriptPath)) {
    throw "未找到脚本: $scriptPath"
}

$invokeArgs = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    $scriptPath
)

if ($Config) {
    $invokeArgs += @("-Config", $Config)
}

& powershell @invokeArgs
exit $LASTEXITCODE
