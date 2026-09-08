# gway-device

Standard host and hardware telemetry for GWAY boxes.

The package owns facts about the local machine rather than any particular display or application. Commands are exposed through GWAY and are designed to be useful directly and through GWAY-backed Sigils.

Canonical command surface:

```console
gway device hostname
gway device uptime

gway device memory
gway device memory percent
gway device memory total
gway device memory free
gway device memory used

gway device disk
gway device disk free-percent
gway device disk percent
gway device disk total
gway device disk free
gway device disk used

gway device cpu
gway device cpu percent
gway device cpu count
gway device cpu load

gway device undervoltage
gway device undervoltage state
gway device undervoltage count

gway device errors
gway device warnings
gway device error-source
gway device failed-units
```

Defaults are chosen for status/monitoring use: `memory` defaults to used percent, `disk` defaults to free percent, `cpu` defaults to utilization percent, and `undervoltage` defaults to the current boolean state. Size-valued memory and disk metrics are returned in MiB.

The zero-argument `memory-percent`, `disk-free-percent`, `cpu-percent`, and `undervoltage-count` aliases remain temporarily available for today's GWAY-backed Sigil resolver. They can be removed after callable Sigil arguments allow forms such as `[device.memory:percent]` and `[device.undervoltage:count]`.

Linux implementations use `/proc`, `shutil.disk_usage`, `journalctl`, and `systemctl`. Raspberry Pi undervoltage detection uses `vcgencmd get_throttled` when available and returns `False` on unsupported hosts.
