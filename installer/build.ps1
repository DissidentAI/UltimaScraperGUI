# Builds UltimaScraper.exe (and UltimaScraper-Setup.exe when Inno Setup is available)
# from the source folder. Usage: double-click build_exe.bat
. (Join-Path $PSScriptRoot "common.ps1")

try {
    $uv = Install-Environment
    Invoke-Checked $uv @("pip", "install", "--python", $VenvPython, "-r", (Join-Path $Root "requirements-build.txt"))

    Push-Location $Root
    try {
        Write-Step "Construction du dossier dist\UltimaScraper (PyInstaller)"
        Invoke-Checked $VenvPython @("-m", "PyInstaller", "--noconfirm", "--clean", "pyinstaller.spec")

        Write-Step "Construction de l'exécutable portable dist\UltimaScraper-portable.exe"
        $env:ULTIMA_ONEFILE = "1"
        Invoke-Checked $VenvPython @("-m", "PyInstaller", "--noconfirm", "--distpath", "dist\onefile", "--workpath", "build\onefile", "pyinstaller.spec")
        Remove-Item Env:\ULTIMA_ONEFILE
        Copy-Item "dist\onefile\UltimaScraper.exe" "dist\UltimaScraper-portable.exe" -Force

        $iscc = Get-Command iscc -ErrorAction SilentlyContinue
        $candidates = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        $isccPath = if ($iscc) { $iscc.Source } else { $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1 }
        if ($isccPath) {
            Write-Step "Construction de l'installeur dist\UltimaScraper-Setup.exe (Inno Setup)"
            Invoke-Checked $isccPath @("installer\UltimaScraper.iss")
        }
        else {
            Write-Host "Inno Setup 6 non trouvé : installeur ignoré (https://jrsoftware.org/isdl.php)." -ForegroundColor Yellow
        }
    }
    finally {
        Pop-Location
    }
    Write-Step "Terminé. Les fichiers sont dans le dossier dist\"
    Start-Process (Join-Path $Root "dist")
}
catch {
    Write-Host ""
    Write-Host "ERREUR : $_" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée pour fermer"
    exit 1
}
