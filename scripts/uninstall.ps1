# Printify uninstaller. Run via uninstall.bat (double-click).
# Removes auto-start, the firewall rule and C:\Printify. Python stays installed.
# Keep this file ASCII-only (Windows PowerShell 5.1).

$ErrorActionPreference = 'Stop'
$InstallDir = 'C:\Printify'
$AppName    = 'Printify'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Asking for administrator rights...'
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    )
    exit
}

try {
    Set-Location $env:TEMP   # don't hold C:\Printify open while deleting it

    Write-Host '==> Stopping Printify'
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*-m printify*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1

    Write-Host '==> Removing auto-start shortcut'
    Remove-Item (Join-Path ([Environment]::GetFolderPath('CommonStartup')) "$AppName.lnk") -Force -ErrorAction SilentlyContinue

    Write-Host '==> Removing firewall rule'
    Get-NetFirewallRule -DisplayName $AppName -ErrorAction SilentlyContinue | Remove-NetFirewallRule

    $answer = Read-Host "Delete $InstallDir including config.toml and logs? [Y/n]"
    if ($answer -notmatch '^[Nn]') {
        Remove-Item $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "    Deleted $InstallDir"
    } else {
        Write-Host "    Kept $InstallDir"
    }

    Write-Host ''
    Write-Host 'Printify has been uninstalled. Python is still installed (remove it from Settings > Apps if you want).' -ForegroundColor Green
} catch {
    Write-Host "UNINSTALL FAILED: $_" -ForegroundColor Red
} finally {
    Write-Host ''
    Read-Host 'Press Enter to close'
}
