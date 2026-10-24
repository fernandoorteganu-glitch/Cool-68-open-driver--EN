<#
Builds the Windows release: portable exe + installer, optionally signed, with SHA256SUMS.

  pwsh scripts/build.ps1                      # unsigned
  pwsh scripts/build.ps1 -Sign                # sign with the self-signed cert (run new-selfsigned-cert.ps1 once)
  pwsh scripts/build.ps1 -Sign -PfxPath c.pfx -PfxPassword (Read-Host -AsSecureString)

Needs: python with requirements-dev.txt installed, and Inno Setup 6 for the installer
(winget install JRSoftware.InnoSetup). Output goes to release/.
#>
[CmdletBinding()]
param([switch]$Sign, [switch]$SkipInstaller, [string]$PfxPath, [securestring]$PfxPassword)
$ErrorActionPreference = "Stop"

# Native tools (PyInstaller, Inno Setup) log progress to stderr; Windows PowerShell 5.1 would treat that as an error.
function Invoke-Native([scriptblock]$Command, [string]$What) {
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Command 2>&1 | ForEach-Object { Write-Host "$_" } } finally { $ErrorActionPreference = $old }
    if ($LASTEXITCODE) { throw "$What failed (exit code $LASTEXITCODE)" }
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$version = (Select-String -Path app/__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
$v4 = (($version -split '\.')[0..2] + @('0')) -join ','
Write-Host "== COOL 68 Control Center $version ==" -ForegroundColor Cyan

Remove-Item build, dist, release -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory release, build | Out-Null

# Windows file properties (company, product, version) for the exe
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v4), prodvers=($v4), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'COOL 68 Control Center contributors'),
    StringStruct('FileDescription', 'COOL 68 Control Center'),
    StringStruct('FileVersion', '$version'),
    StringStruct('InternalName', 'COOL68'),
    StringStruct('LegalCopyright', 'MIT License'),
    StringStruct('OriginalFilename', 'COOL68.exe'),
    StringStruct('ProductName', 'COOL 68 Control Center'),
    StringStruct('ProductVersion', '$version')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"@ | Set-Content -Encoding ASCII build/version_info.txt

$common = @("--noconfirm", "--clean", "--noconsole", "--icon", "assets/COOL68.ico", "--version-file", "build/version_info.txt",
    "--add-data", "app/fonts;app/fonts")
foreach ($m in "QtWebEngineCore", "QtWebEngineWidgets", "QtPdf", "Qt3DCore", "QtQuick", "QtQml", "QtNetwork", "QtSql", "QtMultimedia") {
    $common += @("--exclude-module", "PySide6.$m")
}
Invoke-Native { python -m PyInstaller @common --onedir --name COOL68 gui.py } "PyInstaller (onedir)"
Invoke-Native { python -m PyInstaller @common --onefile --name COOL68-portable gui.py } "PyInstaller (onefile)"

$signArgs = @{}
if ($PfxPath) { $signArgs.PfxPath = $PfxPath; $signArgs.PfxPassword = $PfxPassword }
if ($Sign) { & "$PSScriptRoot/sign.ps1" -Files dist/COOL68/COOL68.exe, dist/COOL68-portable.exe @signArgs }

Copy-Item dist/COOL68-portable.exe "release/COOL68-$version-portable.exe"

if (-not $SkipInstaller) {
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
    if (-not $iscc) { throw "Inno Setup not found. Install it with: winget install JRSoftware.InnoSetup" }
    Invoke-Native { & $iscc "/DAppVersion=$version" installer/COOL68.iss } "Inno Setup"
    Move-Item "installer/Output/COOL68-Setup-$version.exe" release/
    if ($Sign) { & "$PSScriptRoot/sign.ps1" -Files "release/COOL68-Setup-$version.exe" @signArgs }
}

Get-ChildItem release -File | Where-Object Name -ne SHA256SUMS.txt | ForEach-Object {
    "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(), $_.Name
} | Set-Content -Encoding ASCII release/SHA256SUMS.txt
Write-Host "`nDone:" -ForegroundColor Green
Get-ChildItem release | Format-Table Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) }} -AutoSize
