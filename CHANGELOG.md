# Changelog

## 2026.9.1-beta (2026-09-26)

### Fixed
- Commands (set temperature, probe targets, shutdown) intermittently failed with `Unauthorized` even with the correct grill password. The grill checks the password against a key derived from its uptime in 10 second buckets and rejects keys that run behind. The uptime was cached for 5 seconds without being advanced, so over the WiFi relay the key regularly fell into the previous bucket. Uptime is now extrapolated from a single reading with a small lead, and a rejected command is retried once with a freshly read uptime.

## 2026.9.0-beta (2026-09-26)

### Fixed
- Setting the grill temperature failed silently. The grill was rejecting commands as `Unauthorized` (wrong stored password) and the error only reached the log. Failures now show in the UI with a clear message.
- Every entity was named after the device (e.g. all sensors showed as "HotRod Temperature") because the integration shipped no translations. All entities now have proper names.
- The coordinator connected twice on startup and leaked a WebSocket connection on every ping failure.

### Added
- Setup validates the password against the grill and refuses a wrong one.
- Reauthentication when the grill rejects the stored password, and a Reconfigure option to change it.
- Status sensor (Off, Igniting, Preheating, At temperature, Cooling down, Error) and an aggregate Problem sensor listing active faults.
- Climate reports heating/idle action, turn-off support, and rounds targets to 5 degrees within the model range.
- Diagnostics download (password redacted), firmware version and grill ID on the device page.
- Optimistic updates so new set points appear immediately.

### Changed
- Fault and component sensors moved to the diagnostic category; probes beyond the model's count, smoke cabinet, and recipe sensors are disabled by default.
- Probe target duplicate sensors removed (the probe target numbers remain).
- Minimum Home Assistant version is now 2025.1.0.

## 2026.8.10 (2026-08-10)

Promote from beta to stable. Includes the grill_id fix from 2026.8.0-beta plus CI and tooling compliance updates.

### Fixed
- WiFi (WebSocket) config flow crashed immediately after setup with `KeyError: 'grill_id'` - the grill ID is now saved to the config entry's data dictionary so the coordinator has access to it on first load.

### Changed
- Migrated from Dependabot to Renovate for dependency updates.
- CI now uses the shared `ha-shared-workflows` reusable workflow.
- Exempted `renovate[bot]` from the readme-freshness gate.

## 2026.8.0-beta (2026-08-05)

- Fixed: WiFi (WebSocket) config flow crashed immediately after setup with `KeyError: 'grill_id'` because the grill ID was used to set the config entry's unique ID but never saved to the entry's data dictionary. The coordinator now has access to it on first load.

## 2026.7.0-beta (2026-07-27)

- Bumped `dukpy` from 0.3.1 to 0.5.1. 0.3.1 has no prebuilt wheel for Python 3.13/3.14, so HA installs on those versions fell back to a source build that failed and blocked setup with a config flow 500. 0.5.1 ships wheels for those Python versions on the same Duktape engine and `evaljs` API, so behavior is unchanged.

## 2026.5.0 (2026-05-01)

Initial release.

- WiFi (WebSocket) and Bluetooth LE connection support
- Auto-discovery of BLE devices
- Full model support for all PitBoss and Louisiana Grills pellet grills
- Climate entity for grill temperature control (set temperature, turn off)
- Sensor entities: grill temp, grill set temp, smoker temp, probes 1-4, probe targets, recipe step/time
- Binary sensor entities: module on, fan/igniter/auger state, all error conditions, no pellets
- Number entities: probe 1 and probe 2 target temperatures (model-dependent)
- Switch entity: primer motor (model-dependent)
- Light entity: grill light (model-dependent)
- Reliability improvements over upstream pytboss library:
  - WebSocket connect timeout (no more infinite hangs at startup)
  - RPC futures cancelled on disconnect (no more hanging commands)
  - Exceptions in message handlers caught and logged, not silently dropped
  - JS parse errors isolated per message, not crashing the session
  - Stale data detection - refreshes state if no push received in 5 minutes
  - Proper availability chain for all entities
