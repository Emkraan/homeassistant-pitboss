# Changelog

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
