#!/usr/bin/env pwsh
# Fixes VS Code build with Visual Studio 2026 (internal version 18, toolset v145).
# Run this instead of `npm install` when you need a clean build.
#
# Persistent patches already in the repo:
#   - .npmrc: msvs_version="2026"
#   - build/npm/preinstall.ts: '18' in supportedVersions
#
# This script patches TWO copies of node-gyp after npm install --ignore-scripts:
#   1. The system npm's node-gyp (used when npm rebuilds native modules)
#   2. build/npm/gyp/node-gyp (used by preinstall.ts's header install step)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = $PSScriptRoot
$patchedCount = 0

# --- Patch find-visualstudio.js for VS 2026 ---
function Patch-FindVisualStudio {
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) {
        Write-Host "    SKIP (not found): $FilePath" -ForegroundColor Yellow
        return
    }

    Write-Host "    Patching: $FilePath" -ForegroundColor Cyan
    $content = Get-Content -Path $FilePath -Raw

    if ($content.Contains('2026')) {
        Write-Host "    Already patched, skipping." -ForegroundColor Yellow
        $script:patchedCount++
        return
    }

    # 1) Add 2026 to the three supportedYears arrays
    $content = $content.Replace(
        'return this.findVSFromSpecifiedLocation([2019, 2022])',
        'return this.findVSFromSpecifiedLocation([2019, 2022, 2026])')
    $content = $content.Replace(
        'return this.findNewVSUsingSetupModule([2019, 2022])',
        'return this.findNewVSUsingSetupModule([2019, 2022, 2026])')
    $content = $content.Replace(
        'return this.findNewVS([2019, 2022])',
        'return this.findNewVS([2019, 2022, 2026])')

    # 2) Map versionMajor 18 -> versionYear 2026
    $content = $content.Replace(
        "ret.versionYear = 2022`r`n      return ret`r`n    }`r`n    this.log.silly",
        "ret.versionYear = 2022`r`n      return ret`r`n    }`r`n    if (ret.versionMajor === 18) {`r`n      ret.versionYear = 2026`r`n      return ret`r`n    }`r`n    this.log.silly")

    # 3) Map versionYear 2026 -> toolset v145
    $content = $content.Replace(
        "} else if (versionYear === 2022) {`r`n      return 'v143'`r`n    }",
        "} else if (versionYear === 2022) {`r`n      return 'v143'`r`n    } else if (versionYear === 2026) {`r`n      return 'v145'`r`n    }")

    Set-Content -Path $FilePath -Value $content -NoNewline
    Write-Host "    OK" -ForegroundColor Green
    $script:patchedCount++
}

# --- Find system node-gyp via npm.cmd location ---
function Find-SystemNodeGyp {
    $npmCmd = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
    if (-not $npmCmd) { return $null }

    # npm.cmd lives in the node install dir (or fnm multishell proxy).
    # node-gyp is at <dir>/node_modules/npm/node_modules/node-gyp
    $npmDir = Split-Path $npmCmd -Parent
    $findVS = Join-Path $npmDir 'node_modules\npm\node_modules\node-gyp\lib\find-visualstudio.js'

    if (Test-Path $findVS) { return $findVS }
    return $null
}

# --- Main ---
Write-Host "==> Cleaning node_modules and package-lock.json..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -Path (Join-Path $repoRoot 'node_modules') -ErrorAction SilentlyContinue
Remove-Item -Force -Path (Join-Path $repoRoot 'package-lock.json') -ErrorAction SilentlyContinue

Write-Host "`n==> Step 1: npm install --ignore-scripts" -ForegroundColor Cyan
Push-Location $repoRoot
npm install --ignore-scripts
$exit1 = $LASTEXITCODE
Pop-Location
if ($exit1 -ne 0) {
    Write-Host "ERROR: npm install --ignore-scripts failed" -ForegroundColor Red
    exit 1
}

Write-Host "`n==> Step 2: Patching node-gyp for VS 2026" -ForegroundColor Cyan

# Patch 1: system node-gyp (used by npm rebuild)
$sysNodeGyp = Find-SystemNodeGyp
if ($sysNodeGyp) {
    Patch-FindVisualStudio -FilePath $sysNodeGyp
} else {
    Write-Host "    System node-gyp not found, skipping." -ForegroundColor Yellow
}

# Patch 2: local node-gyp in build/npm/gyp (used by preinstall.ts header install)
# Run `npm ci` here first to ensure it's installed, then patch
$gypDir = Join-Path $repoRoot 'build\npm\gyp'
$localNodeGyp = Join-Path $gypDir 'node_modules\node-gyp\lib\find-visualstudio.js'

if (-not (Test-Path $localNodeGyp)) {
    Write-Host "    Installing local node-gyp in build/npm/gyp..." -ForegroundColor Cyan
    Push-Location $gypDir
    npm ci --silent 2>&1 | Out-Null
    Pop-Location
}
Patch-FindVisualStudio -FilePath $localNodeGyp

Write-Host "`n    Patched $patchedCount node-gyp installation(s)." -ForegroundColor Green

Write-Host "`n==> Step 3: npm rebuild (compile native modules for Electron)" -ForegroundColor Cyan
Push-Location $repoRoot
$env:npm_config_disturl = "https://electronjs.org/headers"
$env:npm_config_target = "39.8.2"
$env:npm_config_runtime = "electron"
$env:npm_config_build_from_source = "true"
$env:npm_config_msvs_version = "2026"
npm rebuild
$exit2 = $LASTEXITCODE
Remove-Item Env:\npm_config_disturl -ErrorAction SilentlyContinue
Remove-Item Env:\npm_config_target -ErrorAction SilentlyContinue
Remove-Item Env:\npm_config_runtime -ErrorAction SilentlyContinue
Remove-Item Env:\npm_config_build_from_source -ErrorAction SilentlyContinue
Remove-Item Env:\npm_config_msvs_version -ErrorAction SilentlyContinue
Pop-Location

if ($exit2 -ne 0) {
    Write-Host "`n==> WARNING: npm rebuild had errors, trying npm install anyway..." -ForegroundColor Yellow
}

Write-Host "`n==> Step 4: npm install (run scripts)" -ForegroundColor Cyan
Push-Location $repoRoot
npm install
$exit2 = $LASTEXITCODE
Pop-Location

if ($exit2 -eq 0) {
    Write-Host "`n==> Done! Build dependencies installed successfully." -ForegroundColor Green
} else {
    Write-Host "`n==> npm install failed. Check output above." -ForegroundColor Red
    exit 1
}
