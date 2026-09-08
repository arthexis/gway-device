# gway-device

Standard host and hardware telemetry for GWAY boxes.

The package owns facts about the local machine rather than any particular display or application. Commands are exposed through GWAY and are designed to be useful directly and through GWAY-backed Sigils.

Initial command surface:

```console
gway device hostname
gway device uptime
gway device memory-percent
gway device disk-free-percent
gway device cpu-percent
gway device errors
gway device warnings
gway device error-source
gway device failed-units
gway device undervoltage
```

Linux implementations use `/proc`, `shutil.disk_usage`, `journalctl`, and `systemctl`. Raspberry Pi undervoltage detection uses `vcgencmd get_throttled` when available and returns `0` on unsupported hosts.
