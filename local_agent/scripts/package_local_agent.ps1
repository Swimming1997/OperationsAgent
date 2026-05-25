$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$LocalAgentRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RepoRoot = (Resolve-Path (Join-Path $LocalAgentRoot "..")).Path
$PackageRoot = Join-Path $RepoRoot "packages"
New-Item -ItemType Directory -Force -Path $PackageRoot | Out-Null

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$zipPath = Join-Path $PackageRoot "AMiracle-local-agent-$stamp.zip"
$temp = Join-Path $env:TEMP "AMiracle-local-agent-$stamp"
if (Test-Path -LiteralPath $temp) { Remove-Item -Recurse -Force -LiteralPath $temp }
New-Item -ItemType Directory -Force -Path $temp | Out-Null

robocopy $LocalAgentRoot $temp /E /XD data logs profiles node_modules __pycache__ .pytest_cache .ruff_cache "references\MediaCrawler\.git" "references\MediaCrawler\node_modules" /XF *.pyc *.pyo *.tsbuildinfo *.zip .env | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy failed with $LASTEXITCODE" }

Compress-Archive -Path (Join-Path $temp "*") -DestinationPath $zipPath -Force
Remove-Item -Recurse -Force -LiteralPath $temp
Write-Host "Package created: $zipPath"
