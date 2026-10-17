# Printify

Print PDFs on the office printer from any computer on the LAN (Ubuntu, macOS, anything with a browser). A Windows PC that already prints fine hosts a small web page. You upload a PDF there and Windows prints it.

## For teammates: how to print

1. Open **http://&lt;windows-pc-ip&gt;:8631** in your browser (ask whoever set it up for the address, and bookmark it).
2. Choose or drop a PDF.
3. Set the options: copies, pages (e.g. `1-3, 5`), double-sided, color, paper size, scaling.
4. Click **Print**. The queue at the bottom shows the job while Windows prints it.

Only PDF files are supported for now. To print anything else, export it to PDF first (File → Export/Print → Save as PDF).

## For the person setting up the Windows PC

Requirements: Windows 10/11, an internet connection during install, and administrator rights.
Python does **not** need to be installed, because the installer handles it.

1. Make sure the printer prints from this PC normally and is set as the **default printer**
   (Settings → Bluetooth & devices → Printers & scanners → turn off "Let Windows manage my default printer", then set your printer as default).
2. Make sure the network is **Private**: Settings → Network & internet → (your connection) → Network profile type → Private.
3. Copy the `printify` folder to this PC's local disk (extract it first if it's a zip). Don't run it from a network drive.
4. Double-click **`install.bat`** and approve the administrator prompt. If Windows SmartScreen warns about it, click *More info → Run anyway*.
   The installer will:
   - install Python 3.12 if it's missing
   - copy Printify to `C:\Printify` and install its packages
   - download SumatraPDF, which does the actual printing
   - allow port 8631 through the firewall (Private networks only)
   - add Printify to the Startup folder, so it **starts automatically at every login** with no window
   - start Printify and show the address to share
5. Share the address it prints (e.g. `http://192.168.1.50:8631`) with the team.
6. Recommended: reserve the PC's IP in your router (DHCP reservation) so the address never changes.
   Then restart the PC once and check that the page still opens after you log in.

The PC must be on and logged in for printing to work.

### Updating
Copy the new `printify` folder over and run `install.bat` again. Your `C:\Printify\config.toml` is kept.

### Uninstalling
Run `C:\Printify\uninstall.bat`. It removes the auto-start entry, the firewall rule and `C:\Printify`. Python stays installed.

### Configuration
`C:\Printify\config.toml` settings:

| Setting | Default | Meaning |
|---|---|---|
| `port` | `8631` | Web page port. Re-run `install.bat` after changing it, so the firewall rule is updated |
| `printer` | `""` | Exact Windows printer name. Empty means the default printer |
| `max_upload_mb` | `50` | Largest PDF accepted |
| `sumatra_path` | `""` | Custom SumatraPDF.exe path. Empty means `C:\Printify\bin\SumatraPDF.exe` |

Restart Printify after changes: log out and back in, or re-run `install.bat`.

### Troubleshooting
- **The page doesn't open from other computers**: check that the network is Private and that the PC's IP hasn't changed. Check that `http://localhost:8631` works on the Windows PC itself.
- **The job is accepted but nothing prints**: print a PDF from Windows directly to check the printer, and look at `C:\Printify\printify.log`.
- **The printer status shows offline or error**: fix the printer in Windows first (Printers & scanners → open queue).
- **A double-sided or color option is missing**: the printer driver reported that the printer doesn't support it.

## Development (macOS/Linux)

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m printify      # http://localhost:8631, dry run
```

On non-Windows systems a dry-run backend is used. It logs the SumatraPDF command it would run (to `printify.log` and the console) instead of printing.
