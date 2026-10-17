# Printify — LAN Print Tool

A small web app hosted on a Windows PC. Anyone on the LAN (Ubuntu, macOS, anything with a browser) opens a page, uploads a file, picks options, and it prints on the office printer through Windows, where printing already works reliably.

## Decisions

| Topic | Decision |
|---|---|
| File types | **Phase 1: PDF only.** Other formats come later (see Phase 2) |
| Print options | Copies, page range, duplex, color/B&W, paper size, fit/actual size |
| Printers | One printer, the Windows default (can be overridden in config). Duplex/color support is auto-detected; if detection fails, all options are shown |
| Access | Open to the LAN, no login. Every job is logged |
| Host | Windows 11 PC, usually logged in, **not a dev PC** (no Python preinstalled) |
| Install | Copy the folder over, double-click `install.bat`. It installs Python, dependencies and SumatraPDF, then sets up the firewall and **auto-start at login** |
| Location / port | `C:\Printify`, port **8631** |
| Stack | Python 3.12 + FastAPI + uvicorn + pypdf + pywin32, run from source in a venv. Printing via the SumatraPDF command line |

### Why this stack
- **SumatraPDF** is a free, tiny PDF viewer with a reliable command-line print mode that already supports every option we need:
  `SumatraPDF.exe -print-to "<printer>" -print-settings "1-3,5,2x,duplexlong,monochrome,paper=A4,fit" -silent file.pdf`
- **pywin32** (`win32print`) gives the default printer, its capabilities (duplex/color/paper sizes) and the Windows print queue.
- **FastAPI** gives a small API and serves a single static HTML page. There's no frontend build step.
- **Run from source instead of an `.exe`:** PyInstaller can't build a Windows `.exe` from a Mac, so the install script installs Python on the host. Updating is just "copy the new folder and re-run `install.bat`".

## Architecture

```
[Browser on Mac/Ubuntu] --HTTP (LAN)--> [Printify on Windows PC :8631]
                                            | save upload to temp dir
                                            | validate PDF (pypdf)
                                            | SumatraPDF -print-to ...
                                            v
                                   [Windows spooler] --> [LAN printer]
```

## Features (Phase 1)

1. **Web page**: pick or drag-and-drop a PDF, then set the options (only those the printer supports). Shows a result message, the printer status and an auto-refreshing queue.
2. **API**
   - `GET  /` serves the page
   - `GET  /api/health` returns ok
   - `GET  /api/printer` returns the name, status and capabilities
   - `POST /api/print` takes a multipart file + options
   - `GET  /api/jobs` returns the Windows spooler queue for the printer
3. **Safety**
   - Real-PDF check (`%PDF` header + pypdf parse) and a 50 MB limit
   - Page range validated against the page count; copies clamped to 1–99
   - SumatraPDF arguments passed as a list (no shell)
   - Random temp names, deleted after spooling and cleaned at startup
   - A lock serializes print jobs
   - Rotating log: `C:\Printify\printify.log`
4. **Dev on Mac/Linux**: a dry-run backend logs the SumatraPDF command instead of printing.

## Project layout

```
printify/
  plan.md  README.md  requirements.txt  config.example.toml
  install.bat  uninstall.bat
  printify/
    __main__.py  main.py  config.py  pdfcheck.py  sumatra.py  printer.py
    static/ index.html app.js style.css
  scripts/ install.ps1 uninstall.ps1
  tests/
```

## Install script (`install.bat` → `scripts\install.ps1`)

The script is idempotent, so re-running it updates the app.

1. **Elevation**: self-elevates via UAC. `install.bat` bypasses PowerShell's execution policy.
2. **Python**: if Python ≥ 3.11 is already installed, skip this step. Otherwise:
   - Download the pinned official installer from python.org.
   - Install silently for all users (`/quiet InstallAllUsers=1 PrependPath=1`).
   - Fall back to `winget` if the download fails.
3. **Stop**: stop any running Printify.
4. **Copy**: copy the app files to `C:\Printify`.
5. **venv**: create `C:\Printify\.venv` and `pip install -r requirements.txt`.
6. **SumatraPDF**: download the portable build to `C:\Printify\bin\SumatraPDF.exe`, unless it's already there.
7. **Config**: create `config.toml` from the example only if it's missing.
8. **Firewall**: inbound rule for TCP 8631, Private profile only. Warn if the network is Public.
9. **Auto-start**: `Printify.lnk` in the all-users Startup folder runs `.venv\Scripts\pythonw.exe -m printify` with no console window.
10. **Start now**: start the app as the logged-in user, check `/api/health`, and print the LAN URL to share.

`uninstall.bat` removes the shortcut, the firewall rule and `C:\Printify`. Python stays installed.

## Host setup (README)

1. Make sure the printer prints from Windows and is set as the **default printer**.
2. Give the PC a fixed IP (DHCP reservation on the router).
3. Make sure the network profile is **Private**.
4. Copy the folder to the PC and double-click `install.bat`. Approve the UAC prompt.
5. Share `http://<ip>:8631` with the team. Reboot once to confirm auto-start.

## Phase 2 (later)
- Images (Pillow → PDF), plain text, Office docs (headless LibreOffice → PDF)
- First-page preview
- Optional shared PIN
- mDNS name (`printify.local`)
- Offline installer bundle (Python installer + wheels + SumatraPDF in one zip)

## Risks / open points
- **Capability detection** varies by driver. If it fails, all options are shown and the driver ignores what it can't do.
- **Job status**: Windows shows a job only while it is spooling or printing.
- **Host uptime**: the host must be on and logged in. If that becomes a problem, switch to a Windows service (NSSM) with no code change.
