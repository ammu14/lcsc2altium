# Build installer. Run from repo root:  powershell -File installer\build_installer.ps1
# Requires .tools\innosetup-installer.exe (Inno Setup installer) on first run.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$iscc = Join-Path $root '.tools\innosetup\ISCC.exe'
if (-not (Test-Path $iscc)) {
    $pkg = Join-Path $root '.tools\innosetup-installer.exe'
    if (-not (Test-Path $pkg)) {
        Write-Host "Fetching Inno Setup ..."
        python (Join-Path $PSScriptRoot 'fetch_inno.py')
        if (-not (Test-Path $pkg)) { throw "Inno Setup download failed" }
    }
    Write-Host "Installing Inno Setup into .tools\innosetup ..."
    & $pkg /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /DIR="$root\.tools\innosetup" | Out-Null
    if (-not (Test-Path $iscc)) { throw "Inno Setup install failed" }
}

# 版本号从 Python 包读取，保证安装包与程序一致
$ver = (python -c "import sys; sys.path.insert(0,'.'); from lcsc_exporter import __version__; print(__version__)").Trim()
if (-not $ver) { throw "Cannot read __version__" }
Write-Host "Version: $ver"

Write-Host "Compiling installer ..."
& $iscc "/DAppVersion=$ver" "installer\lcsc2altium.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
Write-Host "Done. See dist\ folder."
