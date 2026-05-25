param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$projectName = Split-Path -Leaf $ProjectRoot
$projectRootFull = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\', '/')
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$packageDir = Join-Path $ProjectRoot 'packages'
$stagingRoot = Join-Path $env:TEMP "$projectName-package-$timestamp"
$stagingProject = Join-Path $stagingRoot $projectName
$zipPath = Join-Path $packageDir "$projectName-code-$timestamp.zip"

$excludedDirs = @(
    '.git',
    '.venv',
    '.pytest_cache',
    '.ruff_cache',
    '__pycache__',
    'node_modules',
    'dist',
    'data',
    'logs',
    'packages',
    'profiles'
)

$excludedFiles = @(
    '.env'
)

New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stagingProject | Out-Null

function Test-IsExcludedPath {
    param([System.IO.FileSystemInfo]$Item)

    $fullName = [System.IO.Path]::GetFullPath($Item.FullName)
    $relative = $fullName.Substring($projectRootFull.Length).TrimStart('\', '/')
    $parts = $relative -split '[\\/]'

    foreach ($part in $parts) {
        if ($excludedDirs -contains $part) {
            return $true
        }
    }

    if (-not $Item.PSIsContainer) {
        if ($excludedFiles -contains $Item.Name) {
            return $true
        }
        if ($Item.Extension -eq '.pyc') {
            return $true
        }
        if ($Item.Name -like '*.zip') {
            return $true
        }
        if ($Item.Name -like '*.tsbuildinfo') {
            return $true
        }
    }

    return $false
}

$items = Get-ChildItem -LiteralPath $ProjectRoot -Force -Recurse | Where-Object {
    -not (Test-IsExcludedPath $_)
}

foreach ($item in $items) {
    $fullName = [System.IO.Path]::GetFullPath($item.FullName)
    $relative = $fullName.Substring($projectRootFull.Length).TrimStart('\', '/')
    $target = Join-Path $stagingProject $relative

    if ($item.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
    } else {
        $targetDir = Split-Path -Parent $target
        New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
        Copy-Item -LiteralPath $item.FullName -Destination $target -Force
    }
}

Compress-Archive -LiteralPath $stagingProject -DestinationPath $zipPath -Force
Remove-Item -LiteralPath $stagingRoot -Recurse -Force

Write-Host ''
Write-Host "Package created: $zipPath"
Write-Host ''
Write-Host 'Excluded: .venv, data, logs, profiles, packages, cache dirs, .env, *.zip'
Write-Host 'You can send this zip file to the GPT expert.'
Write-Host ''

if ($Host.Name -eq 'ConsoleHost' -and -not $NoPause) {
    Write-Host 'Press any key to exit...'
    $null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
}
