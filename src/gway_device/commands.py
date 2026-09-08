"""GWAY command surface for local device telemetry."""

from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import time
from collections import Counter
from pathlib import Path


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


def memory_percent() -> int:
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
        return 0
    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return 0
    return round((1 - available / total) * 100)


def disk_free_percent() -> int:
    try:
        usage = shutil.disk_usage("/")
    except OSError:
        return 0
    if not usage.total:
        return 0
    return round((usage.free / usage.total) * 100)


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


def cpu_percent() -> int:
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


def _journal(priority: str) -> list[str]:
    output = _run(
        ["journalctl", "--since", "-15min", "-p", priority, "--no-pager", "-q", "-n", "300"],
        timeout=3.0,
    )
    return [line for line in output.splitlines() if line.strip()]


def errors() -> int:
    return len(_journal("err"))


def warnings() -> int:
    return len(_journal("warning"))


def _source(line: str) -> str:
    parts = line.split()
    if len(parts) >= 5:
        return parts[4].split("[", 1)[0].rstrip(":") or "-"
    match = re.search(r"\s([\w@_.-]+)(?:\[\d+\])?:", line)
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


def undervoltage() -> int:
    output = _run(["vcgencmd", "get_throttled"], timeout=1.0)
    match = re.search(r"0x([0-9a-fA-F]+)", output)
    if not match:
        return 0
    value = int(match.group(1), 16)
    # Bits 0 and 16 mean under-voltage now / has occurred since boot.
    return int(bool(value & ((1 << 0) | (1 << 16))))
