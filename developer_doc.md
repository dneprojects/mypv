# Developer changelog

Detailed, technical changelog for developers. End-user-facing release notes live
in [`changelog.md`](changelog.md) as concise one-liners; this file keeps the full
rationale and implementation detail for each release.

## v1.6.7

### Bug fixes
- **Energy sensors integrated a source entity that does not exist on a translated installation.** `MpvEnergySensor.__init__` built the `IntegrationSensor` source id as `f"sensor.{slugify(name_by_user + '_' + source.name)}"` — i.e. from the *English* description name (`Power ELWA-2`). The display name is resolved through `translation_key`, so on a German installation the power sensor is registered as `sensor.<device>_leistung_elwa_2` while the energy sensors kept integrating `sensor.<device>_power_elwa_2`. Nothing ever reported under that id, so `int_`/`intd_`/`intm_` sensors stayed at `0` and — because `IntegrationSensor` derives its unit from the source — carried no `unit_of_measurement` either. Reported for an AC ELWA 2 on a German install; every non-English user is affected, and so is anyone who renamed their power sensor (the same string-built id breaks on rename).
- **Fix: resolve the source through the entity registry by unique id.** The unique id (`f"{serial}_{source.name}"`) is derived from the raw English name and is both language- and rename-proof. `async_added_to_hass` looks the real entity id up and rebinds `_sensor_source_id` (state tracking) *and* `_source_entity` (initial value + restore) before delegating to `IntegrationSensor`; by then the power sensor is registered, as it is added ahead of the energy sensors on the same platform. The construction-time string id remains only as a placeholder, and a failed lookup now logs a warning instead of integrating silently into nothing. The `name_by_user` device-registry walk this needed is gone.
- Note this was collateral damage of the v1.4.2 translation fix (`del self._attr_name`, so the translated name is used): that is what made the entity id language-dependent, invalidating the assumption the source id was built on.

### Tests
- `test_energy_sensors_bind_to_the_translated_power_sensor` sets `hass.config.language = "de"`, resolves the power entity from the registry, asserts its id really is the German one, and then asserts the public `source` attribute of all three energy sensors points at it. Verified to *fail* against the old string-built id, so it is a genuine regression guard — in English the old code would have passed.

### Open
- **`button.stop_boost` does not stop a running boost** (reported alongside the above; present in 1.6.3 too, so not a regression). `activate_boost(device, 0)` writes `POST /setup.jsn {"bststrt": 0}`, and the device evidently ignores it: `bststrt` looks like a one-shot trigger rather than a flag, and `setup.jsn` carries no boost-stop key (only `bstmode` and `ww1boost`). The reporter stops a boost by switching `bstmode` off. Needs a `setup.jsn` dump taken while a boost runs and again after stopping it from the device's own web interface, to see which key actually changes — guessing a write to live heating hardware is not acceptable.

## v1.6.6

### Changes
Structural follow-up to v1.6.5, which only removed the *trigger*. `control_enabled` conflated two unrelated questions — "can the device do this?" (capability) and "is the read working right now?" (runtime health) — and answered both with one latch that could only ever go from `True` to `False`. Both halves are now separated.

- **Entity existence no longer depends on the control read.** The `control_enabled` gate is gone from `init_entities()` (boost buttons and the power `number` entities). It was always redundant for capability: those entities are already gated on `key in data_keys`, and `boostactive` is a `data.jsn` key, so a device without boost support simply does not offer it. The gate contributed nothing except the failure mode reported against 1.6.4 — a read failing at setup silently stripping working entities.
- **The control read backs off instead of giving up.** `control_enabled` is replaced by `control_failures` / `control_skip`. The first `_CONTROL_FAILURES_BEFORE_BACKOFF` (3) consecutive failures are retried at the full poll rate and logged as warnings; after that the read is retried only every `_CONTROL_RETRY_CYCLES` (30) polls — ~5 min at the 10 s `SCAN_INTERVAL` — and logged at debug, so a device that genuinely does not serve the endpoint is not hammered. A single success resets the counter.
- **This fixes a second, older bug unrelated to 1.6.4.** `control_enabled` never returned to `True`, and `MpyDevice.update()` gated the whole state read on it. One transient timeout — near-certain over days against a device that serves a single connection at a time, polled every 10 s — permanently froze the control state on its last value until the entry was reloaded. That has been latent since long before the 1.6.4 regression.

### Field data (reporter, three AC-THORs — confirms the mechanism, refutes the v1.6.5 remedy)
- `http://<ip>/control.html` → **connection refused** (the device serves no plain HTTP, so `sec_level` is 1 or 2 and the integration correctly routes `control.html` over HTTPS); `https://<ip>/control.html` → **404**.
- **v1.6.5 did not help; a downgrade to 1.6.3 restored the entities.** So the 404 carries no usable body — empty or a bare error page — and `if text.strip()` never fires. The v1.6.5 remedy was aimed at a *sloppy status with a good body*; the reality is a genuine 404. The mechanism (the `control_enabled` gate) was right, the assumed payload was not.
- Why 1.6.3 worked is now fully explained: it returned the empty body unconditionally, `get_state_dict("")` produced an empty dict *without raising*, `state_update()` returned `True`, the gate stayed open and the entities were built.
- The device evidently 404s the **parameter-less** read specifically (that is what was tested in a browser). Whether it accepts `control.html` *with* query args is unknown, so the power `number` entities may or may not steer on this firmware — unchanged from 1.6.3 either way.
- **The boost buttons are unaffected by all of this:** `activate_boost()` writes `POST /setup.jsn {"bststrt": …}` and never touches `control.html`. They were gated on an endpoint they do not use, which is the clearest argument that the gate was simply wrong.

### Tests
- `test_boost_buttons_exist_when_the_control_read_fails` is an end-to-end regression guard: it sets up an entry whose `control.html` always raises and asserts the boost buttons are in the entity registry. Verified to *fail* with the old gate reinstated, so it is not a vacuous test. Required a new per-path `DeviceSpec.text_errors` in the fake world (the existing `error` field fails every read, which would have failed setup outright rather than modelling this case).
- `test_state_update_failure_backs_off_then_recovers` replaces `test_state_update_failure_disables_control`, covering the counter, the backoff and the recovery.

## v1.6.5

### Bug fixes
- **Boost buttons and power controls vanished after 1.6.4 (regression).** v1.6.4 turned every non-200 read into a `MyPVConnectionError`. On the `control.html` status read that is fatal in a way that is invisible in the logs: `MpyDevice.initialize()` calls `state_update()` *before* `init_entities()`, `state_update()` catches `MyPVConnectionError` and latches `control_enabled = False` (`communicate.py`), and `init_entities()` gates the boost buttons and the power `number` entities on that flag (`mypv_device.py`). Everything fed from `setup.jsn` — including the `bstmode` "Enable Boost Mode" switch, which lives in `SETUP_TYPES` and is built in a separate, ungated loop — survives. Reported symptom (three AC-THORs, unchanged config, 1.6.3 fine / 1.6.4 broken): switch present, `button.start_boost` / `button.stop_boost` gone. That split falls exactly along the `control_enabled` gate, not along "boost-related", which is what identified the mechanism.
- **`_request` now accepts a response that is a `200` *or* carries a non-empty body.** Embedded myPV firmware answers some endpoints with a sloppy status while the payload is perfectly good — the suspected trigger is the *parameter-less* `control.html` read (`state_update` is the only caller without query args; commands always pass some). The status is a channel independent of the body, and up to 1.6.3 the transport ignored it entirely, which is why this never surfaced before. Precedence on a non-200 is now: cached body (keeps the v1.6.4 transient-`429` protection) → non-empty body (v1.6.3 behaviour) → `MyPVConnectionError`. Only `200` bodies are cached, so an error page can never poison the cache and later be served as device state.
- Note the parser is deliberately unbreakable here: `get_state_dict` only picks `key=value` out of lines not starting with `<`, so even a useless body yields an empty dict rather than an exception — under 1.6.3 that still left `control_enabled` `True` and the buttons in place. The boost command itself is a *different* request (`control.html` **with** query args), so it may well have been working all along even where the status read was not.

### Open
- The exact HTTP status the reporter's AC-THOR returns is still unknown (no log yet); `400`/`404` on the parameter-less read are the working hypotheses. Redirects are ruled out (aiohttp follows them), as is a malformed status line (that raises `ClientError`, which already failed identically in 1.6.3). If 1.6.5 does not fix it, the next datum needed is the raw `curl -sk -D - http://<IP>/control.html` output.
- The deeper design issue is untouched by choice: entity *existence* is still decided by a single read at setup time, so any future transport hiccup can strip the control entities again. Decoupling capability from runtime health (or retrying before latching `control_enabled`) remains the structural fix. **Done in v1.6.6.** Deliberately held back from 1.6.5 so that release stayed a single-variable experiment: with the decoupling shipped too, the buttons would reappear for the reporter either way and we would never learn what the device actually answers on `control.html`.

## v1.6.4

### Changes
Runtime robustness, informed by reading the `my-pv==0.0.2` reference library (which the integration no longer depends on but which models the device's session behaviour). The library authenticates once in `open()` and then reuses the aiohttp `ClientSession` — i.e. relies on the **session cookie** the device sets at login — for every subsequent read/write; it never re-authenticates per request, and on any unexpected HTTP status (including `429`) it returns `{}` rather than crashing.

- **Transient non-200 no longer crashes the poll.** `_request` now raises `MyPVAuthenticationError` on `401` and, for any other non-200 (e.g. a `429` rate limit), returns the **last cached body** for that read path (`self._cache`, keyed by path, populated on each 200 read with no query). Previously the non-JSON body was passed to `json.loads` → `JSONDecodeError` → `UpdateFailed` → all entities unavailable with no reauth prompt. With no cached value yet it is a transient `MyPVConnectionError`.
- **Removed per-request re-authentication.** The `_reauthenticate` / `_get_once` / `_post_once` retry-on-401 added in v1.6.3 is gone; the connection logs in once (`open()`) and reuses the session like the library. This cuts `auth.jsn` traffic (the device rate-limits / locks out on frequent logins) and simplifies the read/write paths back to a single request.

Note: the exact production trigger (a device `429` under sustained polling) was inferred from the library diff, not reproduced live; the fix is a robustness improvement regardless and mirrors the library's own handling.
Two-phase transport model, verified on real `e0002410`. The earlier attempts to derive the transport during detection kept tripping over the device's grace window (after a login, `setup.jsn` reads stay open for a while, so a password-less probe is unreliable) and over a `sec_level 0 + password` device that serves `data.jsn`/`control.html` over HTTP but protects `setup.jsn` over HTTPS. The clean split:

- **Phase 1 — detection (`config_flow._check_host`, simple).** A working HTTPS connection means **new firmware**, which always has a login password (it can only be changed, not removed): the integration's initial login opens the device's grace window so reads/writes work afterwards. So new firmware always routes to the **password step**; plain HTTP means **old firmware** (no password). `sec_level` is *not* read here — it needs the (grace-dependent, pre-login) `setup.jsn`, so it is deferred to runtime.
- **Phase 2 — runtime (respects `sec_level`).** After the login, `setup_update()` reads `setup.jsn` (over the connection's own protocol -> HTTPS on new firmware) and calls `connection.set_sec_level()`. The connection then routes **per endpoint** via `_scheme_for()`: `sec_level 0` serves `data.jsn`/`control.html` over plain HTTP, everything else (and `setup.jsn` + `auth.jsn`) over HTTPS; `sec_level 1`/`2` use HTTPS throughout. `setup.jsn` is the deliberate exception (`_HTTP_IN_SEC0` excludes it) because the firmware protects it over HTTPS even in HTTP mode.
- **`sec_level 1` vs `2`.** A `401` on a read or a `setup.jsn` write triggers a single `_reauthenticate()` (re-run `auth.jsn`) and retry before surfacing as an auth error — covers a shorter grace window in mode 2; a no-op under the endless grace of modes 0/1.
- **Self-heal (`_setup_host`) simplified to match.** An old plain-HTTP entry (no password) whose device is now new firmware can no longer read it; if the device speaks HTTPS and no password is stored, it routes to reauth. The former `sec_level`-probing / no-password-HTTPS-upgrade / `_persist_https()` paths are gone. `_open_and_init()` now also maps a `MyPVAuthenticationError` raised during `device.initialize()` (a read `401` that re-auth could not satisfy) to `ConfigEntryAuthFailed`.
- `CONF_SSL` is no longer written by the config flow (a stored password implies HTTPS; the runtime transport follows `sec_level`); it is still read for backwards compatibility with pre-1.6.3 entries.

## v1.6.2

### Changes
- **A reachable-but-unreadable device routes to the password step instead of failing at setup.** `mypv_dev.jsn` (the discovery/identity beacon) answers over plain HTTP in *every* state, including a device still locked in its initial state after a firmware update — but `setup.jsn`/`data.jsn` are gated behind a login there, so `sec_level` cannot be read over any password-less channel. `_check_host` previously fell through to `auth_required=False` in that case (no password prompt → the config entry was created HTTP-only → setup then raised `ConfigEntryNotReady` "No myPV device responded"). It now returns `auth_required=True` whenever the device is reachable but `setup` came back `None` from both the HTTP and the password-less HTTPS probe, so the user gets the password step. The `password` step description also tells the user to set the initial password on the device's own web interface (initial password = device key) first. `sec_level 0` with open HTTP reads is unaffected: `setup.jsn` reads there, `sec_level` is `0`, and no auth flow is triggered.

## v1.6.1

### Changes
- **Self-healing transport on a post-setup encryption-mode change.** An already-configured entry stores its transport (`CONF_SSL` / `CONF_PASSWORD`); if the device's `sec_level` is later changed, the stored transport can no longer read (`mypv_dev.jsn` still answers over plain HTTP in every mode, so `open()` succeeds, but the first real read of `setup.jsn` is redirected → `MyPVConnectionError` → an endless `ConfigEntryNotReady` retry). `MypvCommunicator.initialize()` now heals this: `_setup_host()` opens + initialises via `_open_and_init()`, and on failure re-reads `sec_level` over password-less HTTPS (`_probe_sec_level()`, open in every mode) — `2` without a stored password raises `ConfigEntryAuthFailed` (reauth for the password); `1`/`2` while on plain HTTP upgrades to HTTPS and persists `CONF_SSL` (`_persist_https()`). It also covers the inverse: reads that *succeed* over HTTP while the device reports `sec_level ≥ 1` are upgraded to HTTPS too (otherwise `control.html` would be redirected). Connections expose `is_https` for the HTTP-vs-HTTPS decision. A wrong stored password still raises `ConfigEntryAuthFailed` from `open()` directly.

## v1.6.0

### Changes
- **Removed the `my-pv` library dependency — the transport is now built in.** `connection.py` is self-contained (own aiohttp `ClientSession` lifecycle, own `MyPVConnectionError` / `MyPVAuthenticationError`; `manifest.json` `requirements: []`). The library was `0.0.2` and did not match the real firmware (wrong auth encoding, POST-vs-GET writes, no HTTPS-without-password); we had already overridden almost everything, and its HTTP `_auth` (`GET http://…/auth.jsn` with `ssl=True`) actively **broke detection** on new firmware — `/auth.jsn` is HTTPS-redirected there, so the self-signed cert raised `MyPVAuthenticationError` in *every* mode. Base `_Connection` gives `open()` (session + `mypv_dev.jsn`), `is_open()`, `close()`, `get_json()`/`get_text()` (raw, key-preserving), `send()`, `command()`; `MypvHttpConnection` (`http`) and `MypvHttpsConnection` (`https`, `ssl=False`, optional password) specialise it.
- **All three firmware encryption modes supported and auto-detected.** `sec_level` governs only the `control.html` channel; data/setup stay open and the HTTPS server runs in every mode. Contract (verified on real `e0002410`): reads and `control.html` power steering are open (no password) everywhere; config writes are `POST /setup.jsn` (with `pw` only in mode 2); the browser-encoded password (`_encode_form`) gates only `/auth.jsn`. `create_connection(host, password, use_https)` picks HTTPS when a password is set or `use_https`, else HTTP; `communicate` reads `CONF_SSL` and passes `use_https`.
  - **Detection** (`_check_host`): the encryption mode is read straight from `setup.jsn`'s `sec_level` (`0` HTTP / `1` HTTPS / `2` HTTPS + password). `mypv_dev.jsn` is served over plain HTTP in *every* mode (it is the discovery/identity endpoint), so it only proves reachability and gives the name — it does **not** distinguish the mode (an earlier redirect-probe wrongly assumed `mypv_dev.jsn` is redirected in mode 2; only `data.jsn`/`setup.jsn`/`control.html` are). `setup.jsn` is readable over plain HTTP in modes 0/1 (and old firmware) and over HTTPS *without a password* in every mode, so detection tries HTTP then HTTPS and classifies by `sec_level`: `2` → password step (`CONF_PASSWORD`, which already implies HTTPS); `1` → `CONF_SSL: True` (HTTPS, no password); `0` or absent (old firmware) → plain HTTP.
- **Two write channels.** `send()` = config writes (`POST /setup.jsn`, `pw` appended only when set); `command()` = power steering (`GET /control.html?…`, never carries `pw` — the channel is open, so the password stays out of URLs).
- **New "Encryption" enum sensor** (`MpvEncSensor`, diagnostic) reflecting `setup.sec_level` → HTTP / HTTPS / HTTPS+PW.
- Reauth unchanged in spirit: a wrong stored password → `open()` raises `MyPVAuthenticationError` → `ConfigEntryAuthFailed` on setup/poll, or `_start_reauth()` on a user command.

### Verified on hardware (`e0002410`)
- The device contract (all three modes: reads, config writes, boost, `control.html` power steering, login encoding) was confirmed live. The rebuilt self-contained transport + `sec_level` auto-detection were re-verified live against the real device in **all three modes**: mode 0 (HTTP), mode 1 (HTTPS, no password — reads/`control.html`/config write over HTTPS), and mode 2 (HTTPS + password — detection routes to the password step, login/reads/`control.html`/config write over the authenticated HTTPS session). The mode-2 detection fix (read `sec_level` rather than assume `mypv_dev.jsn` is redirected) was validated on hardware.

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
