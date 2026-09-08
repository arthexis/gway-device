"""GWAY command surface for local device telemetry."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from collections import Counter
from pathlib import Path

UNDERVOLTAGE_STATE_FILE = Path("/run/gway-device/undervoltage.json")
MODEL_FILE = Path("/proc/device-tree/model")
CONFIG_FILE = Path("/boot/firmware/config.txt")
LEGACY_CONFIG_FILE = Path("/boot/config.txt")


def _run(args: list[str], *, timeout: float = 2.0) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def hostname() -> str:
    return socket.gethostname().split(".")[0]


def model() -> str:
    try:
        value = MODEL_FILE.read_bytes().decode("utf-8", errors="replace").rstrip("\x00\n")
    except OSError:
        value = ""
    return value or "unknown"


def uptime() -> str:
    try:
        seconds = int(float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0]))
    except (OSError, ValueError, IndexError):
        return "?"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d{hours}h{minutes}m"
    if hours:
        return f"{hours}h{minutes}m"
    return f"{minutes}m"


def _memory_values() -> tuple[int, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, raw = line.partition(":")
            if key not in {"MemTotal", "MemAvailable"}:
                continue
            match = re.search(r"\d+", raw)
            if match:
                values[key] = int(match.group(0))
    except OSError:
        return 0, 0
    return values.get("MemTotal", 0), values.get("MemAvailable", 0)


def memory(metric: str = "percent") -> int:
    total_kib, free_kib = _memory_values()
    used_kib = max(0, total_kib - free_kib)
    normalized = metric.strip().lower().replace("_", "-")
    if normalized == "percent":
        return round((used_kib / total_kib) * 100) if total_kib else 0
    if normalized == "total":
        return round(total_kib / 1024)
    if normalized == "free":
        return round(free_kib / 1024)
    if normalized == "used":
        return round(used_kib / 1024)
    raise ValueError(f"unknown memory metric: {metric}")


def _disk_values(path: str = "/") -> tuple[int, int, int]:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return 0, 0, 0
    return usage.total, usage.used, usage.free


def disk(metric: str = "free-percent", path: str = "/") -> int:
    total, used, free = _disk_values(path)
    normalized = metric.strip().lower().replace("_", "-")
    if normalized == "free-percent":
        return round((free / total) * 100) if total else 0
    if normalized in {"percent", "used-percent"}:
        return round((used / total) * 100) if total else 0
    if normalized == "total":
        return round(total / (1024**2))
    if normalized == "free":
        return round(free / (1024**2))
    if normalized == "used":
        return round(used / (1024**2))
    raise ValueError(f"unknown disk metric: {metric}")


def _cpu_times() -> tuple[int, int] | None:
    try:
        line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        return None
    fields = line.split()
    if not fields or fields[0] != "cpu":
        return None
    try:
        values = [int(value) for value in fields[1:]]
    except ValueError:
        return None
    idle = sum(values[3:5]) if len(values) >= 5 else values[3]
    return idle, sum(values)


def _cpu_percent() -> int:
    first = _cpu_times()
    if first is None:
        return 0
    time.sleep(0.1)
    second = _cpu_times()
    if second is None:
        return 0
    idle_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    if total_delta <= 0:
        return 0
    return max(0, min(100, round((1 - idle_delta / total_delta) * 100)))


def cpu(metric: str = "percent") -> int | float:
    normalized = metric.strip().lower().replace("_", "-")
    if normalized == "percent":
        return _cpu_percent()
    if normalized == "count":
        return os.cpu_count() or 0
    if normalized in {"load", "load1"}:
        return round(os.getloadavg()[0], 2)
    raise ValueError(f"unknown cpu metric: {metric}")


def _boot_config_text() -> str:
    for path in (CONFIG_FILE, LEGACY_CONFIG_FILE):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return ""


def _config_enabled(key: str) -> bool | None:
    text = _boot_config_text()
    if not text:
        return None
    result: bool | None = None
    pattern = re.compile(rf"^\s*dtparam\s*=\s*{re.escape(key)}\s*=\s*(on|off|1|0|true|false)\s*(?:#.*)?$", re.IGNORECASE)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = pattern.match(line)
        if match:
            result = match.group(1).lower() in {"on", "1", "true"}
    return result


def interface(name: str = "summary") -> bool | str:
    """Return GPIO interface enablement or a compact enabled-interface summary."""
    normalized = name.strip().lower().replace("_", "-")
    checks = {
        "i2c": ("i2c_arm", Path("/dev/i2c-1")),
        "spi": ("spi", Path("/dev/spidev0.0")),
        "uart": (None, Path("/dev/serial0")),
        "1wire": (None, Path("/sys/bus/w1/devices")),
        "1-wire": (None, Path("/sys/bus/w1/devices")),
    }
    if normalized == "summary":
        enabled = []
        for item in ("i2c", "spi", "uart", "1wire"):
            if interface(item) is True:
                enabled.append(item)
        return ",".join(enabled) if enabled else "-"
    if normalized not in checks:
        raise ValueError(f"unknown device interface: {name}")
    config_key, runtime_path = checks[normalized]
    configured = _config_enabled(config_key) if config_key else None
    if configured is not None:
        return configured
    return runtime_path.exists()


def interfaces() -> str:
    """Zero-argument summary alias for current Sigil resolution."""
    return str(interface("summary"))


# Temporary zero-argument aliases for today's GWAY-backed Sigil resolver.
def memory_percent() -> int:
    return memory("percent")


def disk_free_percent() -> int:
    return disk("free-percent")


def cpu_percent() -> int:
    return int(cpu("percent"))


def _journal(priority: str) -> list[str]:
    output = _run(
        ["journalctl", "--since", "-15min", "-p", priority, "--no-pager", "-q", "-n", "300"],
        timeout=3.0,
    )
    return [line for line in output.splitlines() if line.strip()]


def errors() -> int:
    return len(_journal("err"))


def warnings() -> int:
    return len(_journal("warning..warning"))


def _source(line: str) -> str:
    match = re.search(r"\s([\w@_.-]+)(?:\[\d+\])?:\s", line)
    return match.group(1) if match else "-"


def error_source() -> str:
    sources = [_source(line) for line in _journal("err")]
    sources = [source for source in sources if source != "-"]
    if not sources:
        return "-"
    return Counter(sources).most_common(1)[0][0]


def failed_units() -> int:
    output = _run(["systemctl", "--failed", "--no-legend", "--no-pager"], timeout=2.0)
    return sum(1 for line in output.splitlines() if line.strip())


def _undervoltage_current() -> bool:
    output = _run(["vcgencmd", "get_throttled"], timeout=1.0)
    match = re.search(r"0x([0-9a-fA-F]+)", output)
    if not match:
        return False
    value = int(match.group(1), 16)
    return bool(value & (1 << 0))


def _undervoltage_count() -> int:
    try:
        state = json.loads(UNDERVOLTAGE_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    try:
        return max(0, int(state.get("count", 0)))
    except (TypeError, ValueError):
        return 0


def undervoltage(metric: str = "state") -> bool | int:
    normalized = metric.strip().lower().replace("_", "-")
    if normalized in {"state", "current"}:
        return _undervoltage_current()
    if normalized == "count":
        return _undervoltage_count()
    raise ValueError(f"unknown undervoltage metric: {metric}")


def undervoltage_count() -> int:
    return _undervoltage_count()
