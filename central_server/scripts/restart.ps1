param([switch]$NoFrontend)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

& (Join-Path $PSScriptRoot "stop.ps1")
& (Join-Path $PSScriptRoot "start.ps1") -NoFrontend:$NoFrontend
