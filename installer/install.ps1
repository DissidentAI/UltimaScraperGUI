# One-click installation from the source folder (no Python, no PATH, no admin needed).
. (Join-Path $PSScriptRoot "common.ps1")

try {
    Install-Environment | Out-Null

    Write-Step "Création des raccourcis"
    $pythonw = Join-Path $Venv "Scripts\pythonw.exe"
    $script = Join-Path $Root "ultima_scraper_gui.py"
    $icon = Join-Path $Root "ultima_scraper\docs\assets\img\icon.ico"
    $shell = New-Object -ComObject WScript.Shell
    $targets = @(
        (Join-Path $Root "UltimaScraper.lnk"),
        (Join-Path ([Environment]::GetFolderPath("Desktop")) "UltimaScraper.lnk"),
        (Join-Path ([Environment]::GetFolderPath("Programs")) "UltimaScraper.lnk")
    )
    foreach ($target in $targets) {
        $shortcut = $shell.CreateShortcut($target)
        $shortcut.TargetPath = $pythonw
        $shortcut.Arguments = "`"$script`""
        $shortcut.WorkingDirectory = $Root
        $shortcut.IconLocation = $icon
        $shortcut.Save()
    }

    Write-Step "Installation terminée ! Lancement d'UltimaScraper…"
    Write-Host "Raccourci créé sur le Bureau et dans le menu Démarrer." -ForegroundColor Green
    Start-Process -FilePath $pythonw -ArgumentList "`"$script`"" -WorkingDirectory $Root
}
catch {
    Write-Host ""
    Write-Host "ERREUR : $_" -ForegroundColor Red
    Read-Host "Appuyez sur Entrée pour fermer"
    exit 1
}
