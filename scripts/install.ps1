# Printify installer for Windows 10/11.
# Installs Python (if needed), the app, its dependencies and SumatraPDF into C:\Printify,
# opens the firewall port on Private networks and starts Printify at every login.
# Safe to re-run: that is also how you update Printify.
#
# Run it via install.bat (double-click). Keep this file ASCII-only (Windows PowerShell 5.1).

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'   # Invoke-WebRequest is very slow with the progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir   = 'C:\Printify'
$AppName      = 'Printify'

$PythonVersion = '3.12.10'
$PythonUrl     = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$PythonSha256  = '67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb'

$SumatraVersion = '3.6.1'
$SumatraUrl     = "https://www.sumatrapdfreader.org/dl/rel/$SumatraVersion/SumatraPDF-$SumatraVersion-64.zip"
$SumatraSha256  = '98b33a518d42986856d225064b0cd2d3643ecf78cbf84ab873d26cc51877a544'

# --- Self-elevate ------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'Asking for administrator rights...'
    Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`""
    )
    exit
}

function Step($text) { Write-Host ''; Write-Host "==> $text" -ForegroundColor Cyan }

function Download($url, $dest, $sha256) {
    Write-Host "    Downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    $actual = (Get-FileHash $dest -Algorithm SHA256).Hash
    if ($actual -ne $sha256.ToUpper()) {
        Remove-Item $dest -Force
        throw "Checksum mismatch for $url (got $actual)."
    }
}

function Invoke-PythonCheck($exe, $code) {
    # Run "$exe -c $code" and return its trimmed output, or $null on any failure.
    # (Windows PowerShell 5.1 turns redirected stderr into terminating errors under 'Stop'.)
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $exe -c $code 2>$null
        if ($LASTEXITCODE -eq 0) { return "$out".Trim() }
    } catch { }
    return $null
}

function Find-Python {
    # Returns the path of a real Python >= 3.11, ignoring the Microsoft Store "python.exe" stub.
    $candidates = @()
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $exe = Invoke-PythonCheck 'py.exe' 'import sys; print(sys.executable)'
        if ($exe) { $candidates += $exe }
    }
    $candidates += Get-ChildItem -Path "$env:ProgramFiles\Python3*\python.exe", "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue |
        ForEach-Object { $_.FullName }
    foreach ($c in $candidates) {
        if (-not $c -or $c -like '*WindowsApps*' -or -not (Test-Path $c)) { continue }
        if ((Invoke-PythonCheck $c 'import sys; print(int(sys.version_info >= (3, 11)))') -eq '1') { return $c }
    }
    return $null
}

function Read-Port($configFile) {
    if (Test-Path $configFile) {
        $m = Select-String -Path $configFile -Pattern '^\s*port\s*=\s*(\d+)' | Select-Object -First 1
        if ($m) { return [int]$m.Matches[0].Groups[1].Value }
    }
    return 8631
}

function Stop-Printify {
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*-m printify*' } |
        ForEach-Object {
            Write-Host "    Stopping running Printify (PID $($_.ProcessId))"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Seconds 1
}

try {
    $SourceDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
    Write-Host "Printify installer (source: $SourceDir)" -ForegroundColor Green

    # --- 1. Python ---------------------------------------------------------------------
    Step 'Checking for Python 3.11+'
    $python = Find-Python
    if ($python) {
        Write-Host "    Found $python"
    } else {
        Write-Host "    Python not found. Installing Python $PythonVersion for all users..."
        $installer = Join-Path $env:TEMP "python-$PythonVersion-amd64.exe"
        try {
            Download $PythonUrl $installer $PythonSha256
            $p = Start-Process -FilePath $installer -Wait -PassThru -ArgumentList @(
                '/quiet', 'InstallAllUsers=1', 'PrependPath=1', 'Include_launcher=1',
                'Include_test=0', 'Include_doc=0'
            )
            if ($p.ExitCode -ne 0 -and $p.ExitCode -ne 3010) { throw "Python installer exit code $($p.ExitCode)" }
        } catch {
            Write-Warning "Direct Python install failed: $_"
            Write-Host '    Trying winget instead...'
            if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'winget is not available either.' }
            winget install -e --id Python.Python.3.12 --scope machine --silent --accept-package-agreements --accept-source-agreements
        } finally {
            Remove-Item $installer -Force -ErrorAction SilentlyContinue
        }
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
        $python = Find-Python
        if (-not $python) { throw 'Python installation failed. Install Python 3.12 from python.org manually, then re-run install.bat.' }
        Write-Host "    Installed $python"
    }

    # --- 2. Stop a running copy and copy the app ---------------------------------------
    Step "Copying Printify to $InstallDir"
    Stop-Printify
    New-Item -ItemType Directory -Force -Path $InstallDir, "$InstallDir\scripts", "$InstallDir\bin" | Out-Null
    if ($SourceDir -ne $InstallDir) {
        robocopy "$SourceDir\printify" "$InstallDir\printify" /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Copying files failed (robocopy exit $LASTEXITCODE)." }
        Copy-Item "$SourceDir\requirements.txt", "$SourceDir\config.example.toml", "$SourceDir\uninstall.bat" $InstallDir -Force
        Copy-Item "$SourceDir\scripts\uninstall.ps1" "$InstallDir\scripts" -Force
        if (Test-Path "$SourceDir\README.md") { Copy-Item "$SourceDir\README.md" $InstallDir -Force }
    }
    # Printify runs as the logged-in (non-admin) user and writes its log and temp files here.
    icacls $InstallDir /grant '*S-1-5-32-545:(OI)(CI)M' /Q | Out-Null

    # --- 3. Virtual environment + dependencies ------------------------------------------
    Step 'Installing Python packages'
    $venvPy = "$InstallDir\.venv\Scripts\python.exe"
    if (Test-Path $venvPy) {
        if ($null -eq (Invoke-PythonCheck $venvPy 'print(1)')) {
            Write-Host '    Existing virtual environment is broken. Recreating it.'
            Remove-Item "$InstallDir\.venv" -Recurse -Force
        }
    }
    if (-not (Test-Path $venvPy)) {
        & $python -m venv "$InstallDir\.venv"
        if ($LASTEXITCODE -ne 0) { throw 'Creating the virtual environment failed.' }
    }
    & $venvPy -m pip install --disable-pip-version-check --upgrade -r "$InstallDir\requirements.txt"
    if ($LASTEXITCODE -ne 0) { throw 'Installing Python packages failed. Check the internet connection and re-run.' }

    # --- 4. SumatraPDF -------------------------------------------------------------------
    Step 'Checking SumatraPDF'
    $sumatra = "$InstallDir\bin\SumatraPDF.exe"
    if (Test-Path $sumatra) {
        Write-Host "    Already installed: $sumatra"
    } else {
        $zip = Join-Path $env:TEMP "SumatraPDF-$SumatraVersion-64.zip"
        $unzipDir = Join-Path $env:TEMP 'printify-sumatra'
        Download $SumatraUrl $zip $SumatraSha256
        Remove-Item $unzipDir -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -Path $zip -DestinationPath $unzipDir -Force
        $exe = Get-ChildItem $unzipDir -Filter 'SumatraPDF*.exe' | Select-Object -First 1
        if (-not $exe) { throw 'SumatraPDF.exe not found in the downloaded zip.' }
        Move-Item $exe.FullName $sumatra -Force
        Remove-Item $zip, $unzipDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "    Installed $sumatra"
    }

    # --- 5. Config -----------------------------------------------------------------------
    Step 'Checking config.toml'
    $configFile = "$InstallDir\config.toml"
    if (-not (Test-Path $configFile)) {
        Copy-Item "$InstallDir\config.example.toml" $configFile
        Write-Host "    Created $configFile"
    } else {
        Write-Host "    Keeping existing $configFile"
    }
    $port = Read-Port $configFile

    # --- 6. Firewall ---------------------------------------------------------------------
    Step "Allowing TCP port $port on Private networks"
    Get-NetFirewallRule -DisplayName $AppName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName $AppName -Description 'Printify LAN print server' -Direction Inbound `
        -Action Allow -Protocol TCP -LocalPort $port -Profile Private | Out-Null
    $public = Get-NetConnectionProfile | Where-Object { $_.NetworkCategory -eq 'Public' }
    if ($public) {
        Write-Warning ("Network '{0}' is set to Public, so other PCs cannot reach Printify. " -f ($public.Name -join ', ') +
            'Change it to Private in Settings > Network & internet > (your connection) > Network profile type.')
    }

    # --- 7. Start at login ---------------------------------------------------------------
    Step 'Setting up auto-start at login'
    $startup = [Environment]::GetFolderPath('CommonStartup')
    $lnkPath = Join-Path $startup "$AppName.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = "$InstallDir\.venv\Scripts\pythonw.exe"
    $lnk.Arguments = '-m printify'
    $lnk.WorkingDirectory = $InstallDir
    $lnk.Description = 'Printify LAN print server'
    $lnk.Save()
    Write-Host "    Created $lnkPath"

    # --- 8. Start now --------------------------------------------------------------------
    Step 'Starting Printify'
    # Launch through Explorer so it runs as the logged-in user, not as administrator.
    Start-Process explorer.exe -ArgumentList "`"$lnkPath`""
    $healthy = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$port/api/health" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) { $healthy = $true; break }
        } catch { }
    }

    $ips = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        ForEach-Object { $_.IPv4Address.IPAddress }
    Write-Host ''
    if ($healthy) {
        Write-Host 'Printify is running.' -ForegroundColor Green
        foreach ($ip in $ips) { Write-Host "Share this address with your team:  http://${ip}:$port" -ForegroundColor Green }
        Write-Host 'Tip: reserve this IP for the PC in your router so the address never changes.'
    } else {
        Write-Warning "Printify did not respond on port $port. See $InstallDir\printify.log"
    }
} catch {
    Write-Host ''
    Write-Host "INSTALL FAILED: $_" -ForegroundColor Red
} finally {
    Write-Host ''
    Read-Host 'Press Enter to close'
}
