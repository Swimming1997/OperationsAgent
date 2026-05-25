param([string]$Config = "")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

& (Join-Path $PSScriptRoot "stop.ps1")
if ($Config) {
    & (Join-Path $PSScriptRoot "start.ps1") -Config $Config
}
else {
    & (Join-Path $PSScriptRoot "start.ps1")
}
