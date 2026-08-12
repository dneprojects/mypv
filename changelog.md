# Latest changes

User-facing release notes. For the detailed technical changelog see
[`developer_doc.md`](developer_doc.md).

## v1.7.5
- New "Target Grid Power" control on devices that report it. This is the value the device's own controller regulates the grid power to, so it decides how much of the surplus is left unused -- negative means feed-in, positive means drawn from the grid. It could previously only be set at the device itself.

## v1.7.4
- Fixed the "PID Power" control being unusable on devices whose control state had not been read yet: setting it failed with `KeyError: 'Control State'` and the automation stopped there.
- Setting "PID Power" now sends exactly one value per call. It used to keep writing once a second until the device confirmed HTTP control, which made a single call run without end -- an automation writing at a fixed interval was either skipped every run or piled up writers. Repeating the write could never switch the control type anyway; only the "Enable HTTP" switch does that.
- Both power controls now say so when the device is not in HTTP control mode. Such a device answers the write normally and discards the value, which looked like the control simply had no effect. The warning is logged once per mode change, not once per write.
- A power value that could not be delivered is no longer shown as if it had been. The control keeps the value the device actually received, and a written value now appears immediately instead of at the next poll.

## v1.7.3
- Fixed the entities staying unavailable on devices that refuse plain HTTP: the integration followed the encryption mode the device reported and sent two of its requests unencrypted, which such a device rejects every time. It now notices the refusal, switches those requests to HTTPS and keeps them there, instead of failing until the entry is reloaded.
- Connection errors now name the address and the encryption mode they were sent with, so a report shows straight away when the two do not match.

## v1.7.2
- Entities no longer flip to "unavailable" when the device misses a single reply. The heater serves one connection at a time, so an occasional timeout is normal; brief dropouts are now ridden out and only a lasting one is reported, which removes the gaps that appeared in long-term graphs.
- Communication errors now say what actually failed. Most of them carry no message of their own, so the log line ended at the colon and named nothing -- it now reports the error type and the underlying cause.
- The device is polled less: its settings are re-read every two minutes instead of every ten seconds, which cuts a third of the requests. Changes made in Home Assistant are still confirmed immediately, and settings changed at the device itself appear within two minutes.

## v1.7.1
- Fixed the firmware installation not being offered on AC•THOR devices: they report their download progress differently from the AC ELWA 2, and the check only recognised the ELWA's way. Thanks to @marmer1 for the report and the fix.

## v1.7.0
- The control unit firmware can now be installed from Home Assistant: the update entity downloads the firmware and starts the installation, with the download progress shown while it runs. Needs a recent enough control unit firmware (an AC ELWA 2 from e0002500, an AC•THOR from a0020000); older devices keep reporting the update but still have to be updated from the device's own web interface, as do the power unit and co-controller firmwares.
- New entity for the co-controller firmware, which the devices report alongside the control and power unit firmware.
- A firmware download started at the device itself is now visible in Home Assistant; the progress was previously computed but never shown.

## v1.6.9
- Fixed "Entity no longer has a state class" for the AC-THOR 9s output status sensor: devices that report their relay state as text lost the long-term statistics for it.
- Fixed the Surplus sensor losing its statistics depending on whether the device happened to report a value while Home Assistant was starting.
- Fixed the "Control Value Timeout" control missing on devices that do not report this setting — it failed to be created instead of simply staying empty.

## v1.6.8
- Fixed the integration failing to set up on Home Assistant 2026.8 ("Error setting up entry myPV"): the energy sensors were built with an argument Home Assistant no longer accepts. Older Home Assistant versions keep working unchanged.

## v1.6.7
- Fixed the daily and monthly energy consumption sensors staying at 0 kWh with no unit on non-English installations: they now follow the power sensor by its internal id instead of its display name, so a translated or renamed power sensor is still found.

## v1.6.6
- The boost buttons and power controls are now always created when the device supports them — they can no longer disappear because the status read happened to fail while the integration was starting.
- A failing status read no longer switches the control state off permanently: it is retried (at a reduced rate) and recovers by itself as soon as the device answers again. Previously a single timeout froze the control state sensor until Home Assistant was restarted.

## v1.6.5
- Fixed the boost buttons ("Start Boost" / "Stop Boost") and the power controls disappearing after the update to 1.6.4: a device answering the status read with an unusual HTTP status is accepted again as long as it sends a usable body.

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
