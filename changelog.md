# Latest changes

User-facing release notes. For the detailed technical changelog see
[`developer_doc.md`](developer_doc.md).

## v1.5.1
- **Experimental (HTTPS+password firmware):** fixed login failing with a correct password when it contains special characters (e.g. `!`), and fixed device control (setting values, switches, power, boost) not taking effect. Passwords are now sent like the device's own web interface, and control commands are written the way the newer firmware expects.

## v1.5.0
- Device communication now runs through the official my-pv library (entities and power control unchanged).
- **Experimental:** password authentication for newer HTTPS firmware (e.g. `e0002410`) — setup asks for it only when the device requires it, with re-authentication support. This path is new; if you run auth firmware, please report any issues.

## v1.4.6
- Fixed the control state sensor showing wrong states (e.g. `boost_heat` at target temperature, with boost off).

## v1.4.5
- Fixed long-term statistics for numeric sensors (measurement state class restored).

## v1.4.4
- Fixed "Connect call failed" when a command overlapped the cyclic poll.

## v1.4.3
- Fixed entities flipping to "unknown" and broken setup under concurrent requests.

## v1.4.2
- Energy sensor names are now translated.

## v1.4.1
- Added German translations for entity names and states.

## v1.4.0
- Entities report their value immediately on startup.
- Setup retries automatically when the device is unreachable.
- Config-entry-only integration (removed the dead YAML import path).

## v1.3.3
- Entity names and states are now translatable; several sensors moved to diagnostic (disabled by default).
- Polling interval fixed at 10 s (options flow removed).
- Fixed a state class error on non-numeric sensors and the reset-energy / disable-HTTP actions.

## v1.3.2
- New: report-only firmware update entities for the control and power unit.
