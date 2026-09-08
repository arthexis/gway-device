from pathlib import Path

from gway_device import commands


def test_hostname_is_short(monkeypatch):
    monkeypatch.setattr(commands.socket, "gethostname", lambda: "gway-001.example")
    assert commands.hostname() == "gway-001"


def test_uptime_formats_minutes(monkeypatch, tmp_path: Path):
    fake = tmp_path / "uptime"
    fake.write_text("3660.00 0.00\n", encoding="utf-8")
    original = commands.Path
    monkeypatch.setattr(commands, "Path", lambda value: fake if value == "/proc/uptime" else original(value))
    assert commands.uptime() == "1h1m"


def test_disk_free_percent(monkeypatch):
    class Usage:
        total = 100
        free = 25

    monkeypatch.setattr(commands.shutil, "disk_usage", lambda _path: Usage())
    assert commands.disk_free_percent() == 25


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


def test_undervoltage_decodes_current_or_historical_bit(monkeypatch):
    monkeypatch.setattr(commands, "_run", lambda *_args, **_kwargs: "throttled=0x10000")
    assert commands.undervoltage() == 1
