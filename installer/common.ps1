# Shared helpers for install.ps1 / build.ps1.
# Everything (uv, Python, packages) is downloaded into the project folder:
# nothing is installed system-wide and PATH is never modified.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # makes Invoke-WebRequest much faster
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$Root = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $Root ".tools"
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:UV_CACHE_DIR = Join-Path $Tools "cache"
$env:UV_NO_MODIFY_PATH = "1"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Get-Uv {
    $existing = Get-ChildItem -Path (Join-Path $Tools "uv") -Filter "uv.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing) { return $existing.FullName }

    Write-Step "Téléchargement de uv (gestionnaire Python autonome)"
    $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "aarch64" } else { "x86_64" }
    $url = "https://github.com/astral-sh/uv/releases/latest/download/uv-$arch-pc-windows-msvc.zip"
    New-Item -ItemType Directory -Force -Path (Join-Path $Tools "uv") | Out-Null
    $zip = Join-Path $Tools "uv.zip"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath (Join-Path $Tools "uv") -Force
    Remove-Item $zip
    $uv = Get-ChildItem -Path (Join-Path $Tools "uv") -Filter "uv.exe" -Recurse | Select-Object -First 1
    if (-not $uv) { throw "uv.exe introuvable après le téléchargement." }
    return $uv.FullName
}

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    # Native tools write progress on stderr: don't let PowerShell treat it as an error,
    # and keep their output out of the pipeline (functions here return values).
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Exe @Arguments | Out-Host } finally { $ErrorActionPreference = $previous }
    if ($LASTEXITCODE -ne 0) { throw "La commande a échoué : $Exe $($Arguments -join ' ')" }
}

function Install-Environment {
    $uv = Get-Uv
    Write-Step "Préparation de Python 3.11 et de l'environnement (.venv)"
    if (-not (Test-Path $VenvPython)) {
        Invoke-Checked $uv @("venv", "--python", "3.11", "--python-preference", "only-managed", $Venv)
    }
    Write-Step "Installation des dépendances"
    Invoke-Checked $uv @("pip", "install", "--python", $VenvPython, "--no-deps", "-r", (Join-Path $Root "requirements.txt"))
    return $uv
}
