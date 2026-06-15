# Latest changes

## v1.3.3

### Improvements
- Entity names and enum states are now translatable (translation keys); all icons moved to `icons.json`.
- Network (IP/subnet/gateway/DNS), screen mode, fan speed, firmware versions, firmware update states, power unit temperature and L1 voltage are now diagnostic sensors, disabled by default.
- Device `data` and `setup` are fetched concurrently and use Home Assistant's shared HTTP session.
- Coordinator now reports `UpdateFailed`, so unavailability and `ConfigEntryNotReady` work correctly.
- Polling interval is no longer user-configurable (fixed 10 s, per Home Assistant guidelines); the options flow was removed.
- Large internal cleanup: shared entity base class, fully typed code, ruff/mypy clean.

### Bug fixes
- Non-numeric sensors (e.g. control source) no longer raise a state class error.
- Reset-energy-sensor service and the "Enable HTTP" switch-off now work.

## v1.3.2

### New feature
- Report-only firmware `update` entities for the control unit and the power unit.
