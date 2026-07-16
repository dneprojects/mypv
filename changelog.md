# Latest changes

User-facing release notes. For the detailed technical changelog see
[`developer_doc.md`](developer_doc.md).

## v1.6.4
- Entities no longer drop to "unavailable" on a transient device rate-limit (HTTP 429) response: the last values are kept, matching the reference library.
- The device is logged in to once and the session reused, instead of re-authenticating per request — fewer logins, no lockout risk.

## v1.6.3
- Newer firmware (which always has a login password) now reliably asks for the password at setup, fixing "No myPV device responded" in HTTP mode and after firmware or password changes.
- Device communication now follows the device's encryption setting (HTTP for `sec_level` 0, HTTPS otherwise), with automatic re-login if the session expires.

## v1.6.2
- A reachable device whose configuration cannot be read (e.g. locked after a firmware update) now prompts for the password instead of failing silently with "No myPV device responded".

## v1.6.1
- Self-healing when the device's encryption mode changes after setup: re-detects the mode and asks for the password or switches to HTTPS instead of failing with "Error connecting".

## v1.6.0
- Auto-detects all firmware encryption modes (HTTP / HTTPS / HTTPS+password) at setup (`e0002410`).
- Fixes login with special characters (e.g. `!`) in the password.
- Fixes device control (values, switches, power, boost) not taking effect on newer firmware.
- New "Encryption" sensor showing the active mode.
- Removed the external `my-pv` library dependency; transport is now built in.

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
