# Changelog

## 2026.7.0-beta (2026-07-27)

- Bumped `dukpy` from 0.3.1 to 0.5.1. 0.3.1 has no prebuilt wheel for Python 3.13/3.14, so HA installs on those versions fell back to a source build that failed and blocked setup with a config flow 500. 0.5.1 ships wheels for those Python versions on the same Duktape engine and `evaljs` API, so behavior is unchanged.

## 2026.5.0 (2026-05-01)

Initial release.

- WiFi (WebSocket) and Bluetooth LE connection support
- Auto-discovery of BLE devices
- Full model support for all PitBoss and Louisiana Grills pellet grills
- Climate entity for grill temperature control (set temperature, turn off)
- Sensor entities: grill temp, grill set temp, smoker temp, probes 1–4, probe targets, recipe step/time
- Binary sensor entities: module on, fan/igniter/auger state, all error conditions, no pellets
- Number entities: probe 1 and probe 2 target temperatures (model-dependent)
- Switch entity: primer motor (model-dependent)
- Light entity: grill light (model-dependent)
- Reliability improvements over upstream pytboss library:
  - WebSocket connect timeout (no more infinite hangs at startup)
  - RPC futures cancelled on disconnect (no more hanging commands)
  - Exceptions in message handlers caught and logged, not silently dropped
  - JS parse errors isolated per message, not crashing the session
  - Stale data detection — refreshes state if no push received in 5 minutes
  - Proper availability chain for all entities
