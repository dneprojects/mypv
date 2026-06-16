# Latest changes

## v1.4.4

### Bug fixes
- All device requests are serialized; a command (e.g. set power) overlapping the cyclic poll no longer fails with "Connect call failed" (the device serves one connection at a time).

## v1.4.3

### Bug fixes
- Device data and setup are fetched sequentially again; concurrent requests overwhelmed the single-connection myPV web server, flipping entities to "unknown" and breaking setup (regression since v1.3.3).

## v1.4.2

### Bug fixes
- Energy sensor names are now translated (they were stuck in English regardless of the configured language).

## v1.4.1

### Improvements
- German translations for all entity names and states.

## v1.4.0

### Improvements
- Entities report their value immediately on startup instead of waiting for the first poll.
- Setup retries automatically when the device is unreachable; cleaner unload.
- Declared as a config-entry-only integration (removed the dead YAML import path); passes hassfest without warnings.

### Quality
- Added a test suite (~98% coverage) and a pre-commit suite (ruff + hassfest).

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
