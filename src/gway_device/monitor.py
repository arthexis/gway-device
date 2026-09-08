"""Background monitoring for device events that require continuous observation."""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path

from gway_device.commands import _undervoltage_current

STATE_DIR = Path("/run/gway-device")
STATE_FILE = STATE_DIR / "undervoltage.json"
BOOT_ID_FILE = Path("/proc/sys/kernel/random/boot_id")
POLL_INTERVAL = 1.0

_RUNNING = True


def _boot_id() -> str:
    try:
        return BOOT_ID_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def _load_state() -> dict[str, object]:
    boot_id = _boot_id()
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    if state.get("boot_id") != boot_id:
        return {"boot_id": boot_id, "count": 0, "active": False}
    return {
        "boot_id": boot_id,
        "count": int(state.get("count", 0)),
        "active": bool(state.get("active", False)),
    }


def _write_state(state: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_name(f".{STATE_FILE.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o644)
    os.replace(temp, STATE_FILE)


def sample_once() -> dict[str, object]:
    state = _load_state()
    active = _undervoltage_current()
    was_active = bool(state.get("active", False))
    if active and not was_active:
        state["count"] = int(state.get("count", 0)) + 1
    state["active"] = active
    _write_state(state)
    return state


def _stop(_signum: int, _frame: object) -> None:
    global _RUNNING
    _RUNNING = False


def main() -> int:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _RUNNING:
        sample_once()
        time.sleep(POLL_INTERVAL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
