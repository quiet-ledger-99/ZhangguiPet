# Build the ZhangguiPet Windows test zip (onedir + zip, no UPX). Run on Windows from anywhere:
#   powershell -ExecutionPolicy Bypass -File <src>\packaging\build_win.ps1 -Python <path-to-venv>\Scripts\python.exe
# Needs a venv with PySide6-Essentials and pyinstaller (v0.3.4/v0.3.5 were tested with PySide6 6.12.0, PyInstaller 6.22.3, Python 3.12).
# Everything (build cache, temp files, output) stays inside the source folder, so nothing is written to C:.
param(
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$Version = '0.3.9',
    [switch]$RunTests
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$tmp = Join-Path $root 'build\tmp'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$env:TEMP = $tmp; $env:TMP = $tmp
$env:PYINSTALLER_CONFIG_DIR = Join-Path $root 'build\pyi-cache'

& $Python pet_lines.py
if ($LASTEXITCODE) { throw 'line self-check failed' }
if ($RunTests) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    & $Python tests\test_v035.py
    if ($LASTEXITCODE) { throw 'unit tests failed' }
    if (Test-Path -LiteralPath 'tests\test_v036.py') {
        & $Python tests\test_v036.py
        if ($LASTEXITCODE) { throw 'v0.3.6 unit tests failed' }
    }
    if (Test-Path -LiteralPath 'tests\test_v037.py') {
        & $Python tests\test_v037.py
        if ($LASTEXITCODE) { throw 'v0.3.7 unit tests failed' }
    }
    if (Test-Path -LiteralPath 'tests\test_v038.py') {
        & $Python tests\test_v038.py
        if ($LASTEXITCODE) { throw 'v0.3.8 unit tests failed' }
    }
    if (Test-Path -LiteralPath 'tests\test_v039.py') {
        & $Python tests\test_v039.py
        if ($LASTEXITCODE) { throw 'v0.3.9 unit tests failed' }
    }
    if (Test-Path -LiteralPath 'tests\test_samesize.py') {
        & $Python tests\test_samesize.py
        if ($LASTEXITCODE) { throw 'samesize unit tests failed' }
    }
    Remove-Item Env:QT_QPA_PLATFORM
}
& $Python -m PyInstaller --noconfirm --clean --workpath (Join-Path $root 'build\work') --distpath (Join-Path $root 'dist') packaging\zhanggui_pet.spec
if ($LASTEXITCODE) { throw 'PyInstaller failed' }

$d = Join-Path $root 'dist\ZhangguiPet'
Copy-Item -LiteralPath README.md, LICENSE.txt, THIRD_PARTY_NOTICES.txt, CHANGELOG.md -Destination $d -Force
# v0.3.9: also the Chinese notice file (shuoming.txt in Chinese); matched by wildcard so this script stays ASCII-only
Get-ChildItem -LiteralPath $root -Filter '*.txt' -File | Where-Object { $_.Name -notin @('LICENSE.txt', 'THIRD_PARTY_NOTICES.txt') } | Copy-Item -Destination $d -Force
Copy-Item -LiteralPath licenses -Destination $d -Recurse -Force
$zip = Join-Path $root ("ZhangguiPet-v{0}-test.zip" -f $Version)
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
Compress-Archive -Path $d -DestinationPath $zip
Get-FileHash -LiteralPath $zip -Algorithm SHA256 | Format-List
Write-Host ("done: {0}" -f $zip)
