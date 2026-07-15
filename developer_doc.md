# Developer changelog

Detailed, technical changelog for developers. End-user-facing release notes live
in [`changelog.md`](changelog.md) as concise one-liners; this file keeps the full
rationale and implementation detail for each release.

## v1.5.0

### Changes
- **Transport moved onto the official `my-pv` library** (`requirements: ["my-pv==0.0.2"]`). A new `connection.py` subclasses the library's `MyPVHTTPConnection` / `MyPVHTTPSConnection` (`MypvHttpConnection` / `MypvHttpsConnection`) and adds the raw access the integration needs: `get_json()` returns `data.jsn` / `setup.jsn` **unmodified** (the library lowercases keys, which would break `volt_L2` etc.), and `get_text()` provides plain-text access for the `control.html` power steering the library does not expose. Requests are serialised per device via a per-connection `asyncio.Lock` (replacing the former single global lock). `MypvCommunicator` keeps the exact same public method surface (`data_update`, `setup_update`, `state_update`, `set_number`, `set_power`, `set_pid_power`, `set_control_mode`, `switch`, `activate_boost`, `get_state_dict`), so `mypv_device.py`, `const.py` and every entity platform are unchanged. **Device values stay raw** — the library's value/config layer (`MyPVDevice` + bundled `configs`) is deliberately bypassed, so entity scaling (°C/10, Hz/1000, A/10) and unique ids are identical.
- **Authentication.** The config flow probes the device through the library; if it redirects to HTTPS (`MyPVAuthenticationError`), a `password` step is shown and the password is stored in `entry.data[CONF_PASSWORD]`. Old HTTP-only firmware is detected as before and needs no password. A `reauth` / `reauth_confirm` flow updates the password if it later becomes invalid; at runtime an auth failure during the cyclic poll raises `ConfigEntryAuthFailed`, and an auth failure during a user command starts reauth directly (`MypvCommunicator._start_reauth`). Each device gets its own library connection (its own session/auth), and connections are closed on unload (`MypvCommunicator.async_close`).
- **Transport hardening.** `connection._request` reads the body inside an `async with` block so the response is always released — including on the 401 (auth) path, which previously leaked the connection until GC.
- **Tests reseamed onto the connection layer.** The suite no longer mocks aiohttp; `create_connection` is patched to a `FakeWorld` / `FakeConnection` (one `DeviceSpec` per IP), so unreachable / auth-protected / dropping devices are modelled directly. New `test_connection.py` exercises the real `MypvHttpConnection` against a mocked session (query encoding, JSON parsing, 401→auth + response release, connection-error mapping, per-device serialisation, `create_connection` factory), plus new password/reauth/command-auth coverage. `config_flow` now routes through `create_connection` (single seam) and the dead `check_ip` was removed. Run with the Python 3.14 dev-container.

### Open / to verify
- **HTTPS/auth path ships as experimental.** Basic interaction with an auth-firmware device (`e0002410`) has been confirmed on real hardware with no HA log errors; broader confirmation is still pending — in particular `control.html?power=…` power steering over the authenticated HTTPS session. The plain-HTTP path on old firmware is byte-for-byte unchanged.

## v1.4.6

### Bug fixes
- `control_state` sensor (`MpvDevStatSensor`) decoded the device state wrongly (#42): `control.html`'s `State` field is the myPV **operation-state** code (`0` Standby, `1` Heat, `2` Boost heat, `3` Heat finished, `4` No control — confirmed against live AC-ELWA-2 captures and the AC-THOR Controls doc), but `DEV_STATE_ENUM` was built from the different "status codes" table **and** read with a `+ 1` offset. Net effect: every state except `Heat` was scrambled (e.g. `State=3` "target reached" showed `boost_heat`). Fixed by re-keying `DEV_STATE_ENUM`/`DEV_STATE_ENUM_SOLTHOR` to the raw operation-state codes and indexing them directly (no offset); missing `State` now keeps the last value. Affects all devices, not just one model. The `>=200` power-stage error codes and the `20/21/22` (SolThor `21/22/23`) Legionella/disabled/blocked entries are kept best-effort and still need device verification.

## v1.4.5

### Bug fixes
- Numeric sensors without a unit (e.g. meter power sums) keep their measurement state class again, so long-term statistics are tracked instead of triggering "no longer has a state class" warnings. Non-numeric sensors (versions, IPs, status) correctly have none — delete their orphaned statistics via the repair dialog.

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
