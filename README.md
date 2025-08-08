# Monitor Dashboard

A lightweight Flask dashboard to monitor the activity of software installed under specific Windows directories. It streams live metrics to your browser and now supports persistence, stacked charts, and time-window presets.

What you get
- Three stacked charts: CPU, Memory, and Processes (per software group)
- Time window selector: 5m, 30m, 1h, 4h, 12h, 1d, 3d, 1w, 1mo, 6mo, 1y
- CPU y-axis auto-scales to the max in the current window
- 1s sampling interval by default
- Persistence across restarts (JSON on disk)
- Runtime WinRM credentials (no secrets stored in compose)
- Optional local mode (no WinRM, UAC elevation, no passwords)

Target directories (defaults)
- `C:\\Program Files (x86)\\Splashtop`
- `C:\\Program Files (x86)\\ATERA Networks`
- `C:\\Program Files\\Splashtop`
- `C:\\Program Files\\ATERA Networks`

Override with `TARGET_DIRS` (semicolon-separated).

## Run with Docker (WinRM)

1. Ensure Docker Desktop is running.
2. Start the service:
   ```bash
   docker compose up -d --build
   ```
3. Open `http://localhost:8000`.
4. Click "Connect" and enter your WinRM credentials at runtime (not stored). If needed:
   - Host: `host.docker.internal` or your LAN IP
   - Port: `5985` (HTTP) or `5986` (HTTPS + enable SSL)

WinRM enablement (once, elevated PowerShell):
```powershell
winrm quickconfig -q
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
winrm set winrm/config/service/auth '@{Basic="true"}'
# Also allow Windows Firewall "Windows Remote Management (HTTP-In)" on your active profile
```

Diagnostics: `http://localhost:8000/api/status` shows mode, last error, and last fetch counts.

### Persistence
- Data is stored at `/app_data/metrics.json` inside the container and persisted via a named volume `monitor_data`.
- To reset history: `docker compose down -v` (removes the volume) or delete `monitor_data` volume.

### Configuration (Docker)
- `SAMPLE_INTERVAL_SECONDS` (default `1`)
- `TARGET_DIRS` (semicolon-separated)
- `PERSIST_PATH` (default `/app_data/metrics.json`)
- WinRM: `WINRM_HOST`, `WINRM_PORT`, `WINRM_USE_SSL`

## Run locally (no WinRM, no passwords)
Best if you don’t want to enable WinRM. Runs under your account with UAC elevation, using `psutil` locally.

```powershell
# From repo root
cd monitor
# Double-click or run:
./run_local_admin.cmd
```
- Prompts for UAC elevation
- Creates a venv on first run, installs deps
- Starts at `http://localhost:8000`
- Defaults to `SAMPLE_INTERVAL_SECONDS=1`

## UI tips
- Use the View selector to switch between windows (5m … 1y)
- CPU shows as a fraction (0.001 = 0.1%). Axis auto-scales to the max value in view.
- Legend entries reflect each software group detected. Splashtop and Atera are auto-detected by path and common process names.

## Notes
- CPU aggregation is accurate in local mode. Over WinRM, CPU may appear as 0 in this version (process count and memory are still tracked).
- If a vendor isn’t detected by path, the app falls back to name-based grouping (expanded for Splashtop/Atera).

## Troubleshooting
- No lines on the chart (Docker/WinRM):
  - Click Connect and enter credentials; then check `http://localhost:8000/api/status`
  - Open the WinRM firewall rule and verify host/port
- Vertical layout issues: charts are fixed-height; hard refresh (Ctrl+F5) to reload CSS/JS
- Reset data: delete the volume or `metrics.json` (see Persistence)
