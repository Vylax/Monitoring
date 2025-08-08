# Monitor Dashboard (Dockerized)

A lightweight Flask dashboard that monitors activity of Windows software installed under specific directories, streaming live metrics to a browser.

By default it runs in a Docker container and connects back to your Windows host via WinRM to enumerate processes. It tracks, over time, for each software found under the target directories:

- Process count
- Aggregate CPU percent (local mode only)
- Aggregate memory usage

## Target directories

- `C:\\Program Files (x86)\\Splashtop`
- `C:\\Program Files (x86)\\ATERA Networks`

You can override via `TARGET_DIRS` (semicolon-separated).

## Run (Docker + WinRM)

1. Ensure Docker Desktop is running.
2. Enable WinRM on Windows (only once):

   - Open PowerShell as Administrator and run:

     ```powershell
     winrm quickconfig -q
     winrm set winrm/config/service '@{AllowUnencrypted="true"}'
     winrm set winrm/config/service/auth '@{Basic="true"}'
     ```

   - Open Firewall for WinRM HTTP-In on your active profile.
   - Optional: For HTTPS, create a cert and set `WINRM_USE_SSL=true`, `WINRM_PORT=5986`.

3. Start container:

   ```bash
   docker compose up -d --build
   ```

4. Open `http://localhost:8000`. Click "Connect" to enter credentials at runtime (not stored).

## Run locally (no passwords, UAC prompt)

If you prefer not to enable WinRM or store any password, run in local mode under your account with an elevation prompt:

```powershell
# From repo root
cd monitor
# Launches UAC prompt, creates venv, installs deps, and starts server
./run_local_admin.ps1
```

- This uses `MONITOR_MODE=local` and reads processes directly with `psutil`.
- Open `http://localhost:8000` and you should see data within a few seconds.

## Configuration

- `TARGET_DIRS`: Semicolon-separated Windows paths to watch
- `SAMPLE_INTERVAL_SECONDS`: Sampling interval (default 5)

## Notes

- CPU percent aggregation is available in local mode. In WinRM mode the initial version charts process count and memory; CPU may appear as 0.
- If you need a smaller CPU scale, the UI uses a fixed 0–0.01 (1%) band for CPU.
