import json
from pathlib import Path

from gway_device import commands, monitor


def test_hostname_is_short(monkeypatch):
    monkeypatch.setattr(commands.socket, "gethostname", lambda: "gway-001.example")
    assert commands.hostname() == "gway-001"


def test_uptime_formats_minutes(monkeypatch, tmp_path: Path):
    fake = tmp_path / "uptime"
    fake.write_text("3660.00 0.00\n", encoding="utf-8")
    original = commands.Path
    monkeypatch.setattr(
        commands,
        "Path",
        lambda value: fake if value == "/proc/uptime" else original(value),
    )
    assert commands.uptime() == "1h1m"


def test_memory_metrics(monkeypatch):
    monkeypatch.setattr(commands, "_memory_values", lambda: (4096, 1024))
    assert commands.memory() == 75
    assert commands.memory("percent") == 75
    assert commands.memory("total") == 4
    assert commands.memory("free") == 1
    assert commands.memory("used") == 3
    assert commands.memory_percent() == 75


def test_disk_metrics(monkeypatch):
    mib = 1024**2
    monkeypatch.setattr(commands, "_disk_values", lambda _path="/": (100 * mib, 75 * mib, 25 * mib))
    assert commands.disk() == 25
    assert commands.disk("free-percent") == 25
    assert commands.disk("percent") == 75
    assert commands.disk("total") == 100
    assert commands.disk("free") == 25
    assert commands.disk("used") == 75
    assert commands.disk_free_percent() == 25


def test_cpu_metrics(monkeypatch):
    monkeypatch.setattr(commands, "_cpu_percent", lambda: 42)
    monkeypatch.setattr(commands.os, "cpu_count", lambda: 4)
    monkeypatch.setattr(commands.os, "getloadavg", lambda: (1.25, 0.5, 0.25))
    assert commands.cpu() == 42
    assert commands.cpu("percent") == 42
    assert commands.cpu("count") == 4
    assert commands.cpu("load") == 1.25
    assert commands.cpu_percent() == 42


def test_error_source_uses_most_common(monkeypatch):
    monkeypatch.setattr(
        commands,
        "_journal",
        lambda _priority: [
            "Sep 08 host alpha[1]: failed",
            "Sep 08 host beta[2]: failed",
            "Sep 08 host alpha[3]: failed",
        ],
    )
    assert commands.error_source() == "alpha"


def test_undervoltage_defaults_to_current_state(monkeypatch):
    monkeypatch.setattr(commands, "_run", lambda *_args, **_kwargs: "throttled=0x1")
    assert commands.undervoltage() is True
    assert commands.undervoltage("state") is True


def test_undervoltage_count_reads_monitor_state(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "undervoltage.json"
    state_file.write_text('{"count": 3}\n', encoding="utf-8")
    monkeypatch.setattr(commands, "UNDERVOLTAGE_STATE_FILE", state_file)
    assert commands.undervoltage("count") == 3
    assert commands.undervoltage_count() == 3


def test_monitor_counts_only_false_to_true_transitions(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "undervoltage.json"
    boot_file = tmp_path / "boot_id"
    boot_file.write_text("boot-a\n", encoding="utf-8")
    monkeypatch.setattr(monitor, "STATE_DIR", tmp_path)
    monkeypatch.setattr(monitor, "STATE_FILE", state_file)
    monkeypatch.setattr(monitor, "BOOT_ID_FILE", boot_file)

    samples = iter([False, True, True, False, True])
    monkeypatch.setattr(monitor, "_undervoltage_current", lambda: next(samples))

    for _ in range(5):
        monitor.sample_once()

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["count"] == 2
    assert state["active"] is True


def test_monitor_resets_count_for_new_boot(monkeypatch, tmp_path: Path):
    state_file = tmp_path / "undervoltage.json"
    boot_file = tmp_path / "boot_id"
    boot_file.write_text("boot-b\n", encoding="utf-8")
    state_file.write_text(
        '{"boot_id": "boot-a", "count": 7, "active": true}\n', encoding="utf-8"
    )
    monkeypatch.setattr(monitor, "STATE_DIR", tmp_path)
    monkeypatch.setattr(monitor, "STATE_FILE", state_file)
    monkeypatch.setattr(monitor, "BOOT_ID_FILE", boot_file)
    monkeypatch.setattr(monitor, "_undervoltage_current", lambda: False)

    state = monitor.sample_once()

    assert state == {"boot_id": "boot-b", "count": 0, "active": False}
