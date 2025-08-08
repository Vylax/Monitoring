import json
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import psutil

try:
    import winrm  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    winrm = None


@dataclass
class SoftwareMetricsPoint:
    timestamp: float
    process_count: int
    total_cpu_percent: float
    total_memory_bytes: int


@dataclass
class SoftwareSeries:
    software_key: str
    display_name: str
    points: Deque[SoftwareMetricsPoint] = field(default_factory=lambda: deque(maxlen=7200))  # ~2 hours @ 1s


class InMemoryTimeSeriesStore:
    def __init__(self, max_points: int = 7200, persistence_path: Optional[str] = None, persist_interval_seconds: float = 10.0) -> None:
        self._lock = threading.Lock()
        self._series: Dict[str, SoftwareSeries] = {}
        self._max_points = max_points
        self._persistence_path = persistence_path
        self._persist_interval = persist_interval_seconds
        self._last_persist_ts = 0.0

    def ensure_series(self, software_key: str, display_name: str) -> SoftwareSeries:
        with self._lock:
            if software_key not in self._series:
                self._series[software_key] = SoftwareSeries(
                    software_key=software_key,
                    display_name=display_name,
                    points=deque(maxlen=self._max_points),
                )
            else:
                # Update display name if changed
                self._series[software_key].display_name = display_name
            return self._series[software_key]

    def add_point(self, software_key: str, display_name: str, point: SoftwareMetricsPoint) -> None:
        series = self.ensure_series(software_key, display_name)
        with self._lock:
            series.points.append(point)

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            snapshot: Dict[str, Dict[str, object]] = {}
            for key, series in self._series.items():
                snapshot[key] = {
                    "key": key,
                    "display_name": series.display_name,
                    "points": [
                        {
                            "t": p.timestamp,
                            "process_count": p.process_count,
                            "cpu": p.total_cpu_percent,
                            "mem": p.total_memory_bytes,
                        }
                        for p in series.points
                    ],
                }
        return snapshot

    def load_from_disk(self) -> None:
        if not self._persistence_path or not os.path.exists(self._persistence_path):
            return
        try:
            with open(self._persistence_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._series.clear()
                for key, s in data.items():
                    series = SoftwareSeries(
                        software_key=key,
                        display_name=s.get("display_name", key),
                        points=deque(maxlen=self._max_points),
                    )
                    for p in s.get("points", [])[-self._max_points:]:
                        try:
                            series.points.append(
                                SoftwareMetricsPoint(
                                    timestamp=float(p.get("t", 0.0)),
                                    process_count=int(p.get("process_count", 0)),
                                    total_cpu_percent=float(p.get("cpu", 0.0)),
                                    total_memory_bytes=int(p.get("mem", 0)),
                                )
                            )
                        except Exception:
                            continue
                    self._series[key] = series
        except Exception:
            # Ignore corrupt or unreadable persistence
            pass

    def save_to_disk(self, force: bool = False) -> None:
        if not self._persistence_path:
            return
        now = time.time()
        if not force and (now - self._last_persist_ts) < self._persist_interval:
            return
        data = self.snapshot()
        tmp_path = f"{self._persistence_path}.tmp"
        try:
            os.makedirs(os.path.dirname(self._persistence_path) or ".", exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp_path, self._persistence_path)
            self._last_persist_ts = now
        except Exception:
            # Best-effort persistence
            pass


class WinRMClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 5985,
        use_ssl: bool = False,
    ) -> None:
        if winrm is None:
            raise RuntimeError("pywinrm is not available. Install it or use MONITOR_MODE=local")
        endpoint = f"http{'s' if use_ssl else ''}://{host}:{port}/wsman"
        self._session = winrm.Session(endpoint, auth=(username, password), transport="ntlm" if "\\" in username else "basic")

    def run_powershell(self, script: str) -> str:
        r = self._session.run_ps(script)
        if r.status_code != 0:
            raise RuntimeError(f"WinRM error {r.status_code}: {r.std_err.decode('utf-8', 'ignore')}")
        return r.std_out.decode("utf-8", "ignore")

    def list_processes(self) -> List[Dict[str, object]]:
        ps_script_csv = (
            "$ErrorActionPreference='Stop'; "
            "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,KernelModeTime,UserModeTime,WorkingSetSize | "
            "ConvertTo-Csv -NoTypeInformation"
        )
        out_csv = self.run_powershell(ps_script_csv)
        import csv
        from io import StringIO

        reader = csv.DictReader(StringIO(out_csv))
        rows: List[Dict[str, object]] = []
        for row in reader:
            try:
                rows.append(
                    {
                        "pid": int(row.get("ProcessId") or 0),
                        "name": (row.get("Name") or "").strip(),
                        "exe": (row.get("ExecutablePath") or "").strip(),
                        "cpu_time": int(row.get("KernelModeTime") or 0) + int(row.get("UserModeTime") or 0),
                        "rss": int(row.get("WorkingSetSize") or 0),
                    }
                )
            except Exception:
                continue
        return rows

    def list_services(self) -> List[Dict[str, object]]:
        ps_script_csv = (
            "$ErrorActionPreference='Stop'; "
            "Get-CimInstance Win32_Service | Select-Object Name,State,Status,PathName | ConvertTo-Csv -NoTypeInformation"
        )
        out_csv = self.run_powershell(ps_script_csv)
        import csv
        from io import StringIO

        reader = csv.DictReader(StringIO(out_csv))
        rows: List[Dict[str, object]] = []
        for row in reader:
            rows.append(
                {
                    "name": (row.get("Name") or "").strip(),
                    "state": (row.get("State") or "").strip(),
                    "status": (row.get("Status") or "").strip(),
                    "path": (row.get("PathName") or "").strip(),
                }
            )
        return rows


def normalize_windows_path(p: str) -> str:
    p = p.replace("/", "\\")
    return p.lower()


NAME_GROUPS: Dict[str, List[str]] = {
    # Add more Splashtop identifiers commonly seen in process names
    "Splashtop": ["splashtop", "streamer", "srservice", "splashtopremote", "srs"],
    "Atera": ["atera", "ateragent", "agentpackage", "agentpackageheartbeat"],
}


def match_name_group(name: Optional[str]) -> Optional[Tuple[str, str]]:
    if not name:
        return None
    n = name.lower()
    for display, keywords in NAME_GROUPS.items():
        for kw in keywords:
            if kw in n:
                key = f"name|{display}"
                return key, display
    return None


def path_under_targets(exe_path: Optional[str], targets: List[str]) -> Optional[Tuple[str, str]]:
    if not exe_path:
        return None
    exe_norm = normalize_windows_path(exe_path)
    for t in targets:
        t_norm = normalize_windows_path(t)
        if exe_norm.startswith(t_norm):
            rel = exe_norm[len(t_norm):].lstrip("\\/")
            display = (rel.split("\\")[0] or os.path.basename(exe_norm))
            key = f"{t_norm}|{display}"
            return key, display
    return None


class Sampler:
    def __init__(self, store: InMemoryTimeSeriesStore, interval_seconds: float, mode: str, targets: List[str]) -> None:
        self._store = store
        self._interval = max(1.0, float(interval_seconds))
        self._mode = mode
        self._targets = targets
        self._thread = threading.Thread(target=self._run, daemon=True, name="monitor-sampler")
        self._stop = threading.Event()
        self._config_lock = threading.Lock()
        self._winrm: Optional[WinRMClient] = None
        self._last_error: Optional[str] = None
        self._last_fetch_count: int = 0
        self._last_sample_ts: float = 0.0
        if self._mode == "winrm":
            host = os.getenv("WINRM_HOST", "host.docker.internal")
            username = os.getenv("WINRM_USERNAME", "")
            password = os.getenv("WINRM_PASSWORD", "")
            port = int(os.getenv("WINRM_PORT", "5985"))
            use_ssl = os.getenv("WINRM_USE_SSL", "false").lower() in {"1", "true", "yes"}
            if username and password:
                try:
                    self._winrm = WinRMClient(host, username, password, port=port, use_ssl=use_ssl)
                except Exception as e:
                    self._last_error = str(e)

    def set_winrm_credentials(self, host: Optional[str], username: str, password: str, port: Optional[int] = None, use_ssl: Optional[bool] = None) -> None:
        if winrm is None:
            raise RuntimeError("pywinrm is not available")
        resolved_host = host or os.getenv("WINRM_HOST", "host.docker.internal")
        resolved_port = int(port if port is not None else os.getenv("WINRM_PORT", "5985"))
        resolved_ssl = bool(use_ssl if use_ssl is not None else (os.getenv("WINRM_USE_SSL", "false").lower() in {"1", "true", "yes"}))
        client = WinRMClient(resolved_host, username, password, port=resolved_port, use_ssl=resolved_ssl)
        with self._config_lock:
            self._mode = "winrm"
            self._winrm = client
            self._last_error = None

    def status(self) -> Dict[str, object]:
        with self._config_lock:
            return {
                "mode": self._mode,
                "winrm_configured": self._winrm is not None,
                "last_error": self._last_error,
                "targets": self._targets,
                "last_fetch_count": self._last_fetch_count,
                "last_sample_ts": self._last_sample_ts,
            }

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _collect_local(self) -> Dict[str, Tuple[str, int, float, int]]:
        aggregates: Dict[str, Tuple[str, int, float, int]] = {}
        for proc in psutil.process_iter(["pid", "name", "exe", "username"]):
            try:
                info = proc.info
                match = path_under_targets(info.get("exe"), self._targets)
                if not match:
                    match = match_name_group(info.get("name"))
                if not match:
                    continue
                key, display = match
                cpu = 0.0
                try:
                    cpu = proc.cpu_percent(interval=None)
                except Exception:
                    cpu = 0.0
                rss = 0
                try:
                    rss = proc.memory_info().rss
                except Exception:
                    rss = 0
                if key not in aggregates:
                    aggregates[key] = (display, 0, 0.0, 0)
                display_name, cnt, cpu_sum, mem_sum = aggregates[key]
                aggregates[key] = (display_name, cnt + 1, cpu_sum + cpu, mem_sum + rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return aggregates

    def _collect_remote(self) -> Dict[str, Tuple[str, int, float, int]]:
        with self._config_lock:
            client = self._winrm
        if not client:
            self._last_error = "WinRM not configured"
            return {}
        aggregates: Dict[str, Tuple[str, int, float, int]] = {}
        try:
            procs = client.list_processes()
            self._last_fetch_count = len(procs)
            self._last_error = None
        except Exception as e:
            self._last_error = str(e)
            procs = []
        for p in procs:
            name = str(p.get("name") or "")
            exe = str(p.get("exe") or "")
            match = path_under_targets(exe, self._targets)
            if not match:
                match = match_name_group(name)
            if not match:
                continue
            key, display = match
            rss = int(p.get("rss") or 0)
            if key not in aggregates:
                aggregates[key] = (display, 0, 0.0, 0)
            display_name, cnt, cpu_sum, mem_sum = aggregates[key]
            aggregates[key] = (display_name, cnt + 1, cpu_sum, mem_sum + rss)
        return aggregates

    def _run(self) -> None:
        for proc in psutil.process_iter():
            try:
                proc.cpu_percent(interval=None)
            except Exception:
                continue
        while not self._stop.is_set():
            ts = time.time()
            try:
                if self._mode == "winrm":
                    aggregates = self._collect_remote()
                else:
                    aggregates = self._collect_local()
                for key, (display, count, cpu, mem) in aggregates.items():
                    self._store.add_point(
                        key,
                        display,
                        SoftwareMetricsPoint(
                            timestamp=ts,
                            process_count=count,
                            total_cpu_percent=cpu,
                            total_memory_bytes=mem,
                        ),
                    )
                # Throttled persistence
                self._store.save_to_disk(force=False)
            except Exception as e:
                self._last_error = str(e)
            finally:
                self._last_sample_ts = ts
                time.sleep(self._interval)


def load_targets_from_env() -> List[str]:
    default_dirs = [
        r"C:\\Program Files (x86)\\Splashtop",
        r"C:\\Program Files (x86)\\ATERA Networks",
        r"C:\\Program Files\\Splashtop",
        r"C:\\Program Files\\ATERA Networks",
    ]
    raw = os.getenv("TARGET_DIRS")
    if not raw:
        return default_dirs
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    return parts or default_dirs
