<div align="center">
  <img src="https://raw.githubusercontent.com/Emkraan/homeassistant-pitboss/main/.github/homeassistant-pitboss.png" alt="PitBoss" width="120" />
  <h1>PitBoss for Home Assistant</h1>
  <p>Home Assistant integration for PitBoss pellet grills: Bluetooth LE (fully local) and WiFi (via the Dansons WebSocket relay).</p>

  [![HACS](https://img.shields.io/badge/HACS-Custom-orange?style=for-the-badge)](https://hacs.xyz)
  [![Release](https://img.shields.io/github/v/release/Emkraan/homeassistant-pitboss?style=for-the-badge)](https://github.com/Emkraan/homeassistant-pitboss/releases)
  [![HA Version](https://img.shields.io/badge/HA-2025.1.0%2B-blue?style=for-the-badge)](https://www.home-assistant.io)
  [![License](https://img.shields.io/github/license/Emkraan/homeassistant-pitboss?style=for-the-badge)](LICENSE)
</div>

<div align="center">

> Headless integration: Authentication / Roles / Audit sections are N/A.

</div>

<div align="center">

⚠️ 🚨 **This is an unofficial integration and is not affiliated with or endorsed by Dansons Inc. or PitBoss.** 🚨 ⚠️

</div>

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Automations](#automations)
- [Troubleshooting](#troubleshooting)
- [How It Works](#how-it-works)
- [License](#license)

---

## Features

- **Local Bluetooth LE** control: BLE talks straight to the grill with no cloud and no account required
- **WiFi (WebSocket)** connection for full range: preferred when available, relayed through the Dansons cloud socket (see [How It Works](#how-it-works))
- **Auto-discovery** of BLE devices on the HA Bluetooth integration
- **Full model support** for all PitBoss and Louisiana Grills pellet grill models
- **Climate entity**: monitor and set grill temperature, shut down remotely
- **Status at a glance**: a single Status sensor (Off, Igniting, Preheating, At temperature, Cooling down, Error) and one Problem sensor that lists active faults
- **Password checked at setup**, with reauthentication and a Reconfigure option if it changes
- **Probe sensors**: up to 4 meat probes with target temperature control
- **Error monitoring**: probe errors, fan/igniter/auger faults, pellet level, ErL
- **Recipe tracking**: current step and time remaining
- **Primer motor and grill light** control (model-dependent)
- **Reliable reconnection**: exponential backoff with proper timeout handling

---

## Requirements

| Requirement | Detail |
|---|---|
| Home Assistant | 2025.1.0 or newer |
| HACS | 1.34.0 or newer |
| Connection | WiFi grill ID **or** Bluetooth LE adapter on your HA host |
| WiFi path | Reaches the grill through the Dansons WebSocket relay (`socket.dansonscorp.com`); HA needs outbound internet |
| Grill | Any PitBoss or Louisiana Grills WiFi-enabled pellet grill |

---

## Installation

### HACS (Recommended)

Click the badge below to open HACS and add this repository in one step:

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Emkraan&repository=homeassistant-pitboss&category=integration)

Or manually:

1. Open **HACS -> Integrations**.
2. Click the menu (⋮) -> **Custom repositories**.
3. Add `https://github.com/Emkraan/homeassistant-pitboss`, category: **Integration**.
4. Search for **PitBoss** and click **Download**.
5. Restart Home Assistant.
6. Go to **Settings -> Devices & Services -> Add Integration** and search for **PitBoss**.

### Manual

1. Copy the `custom_components/pitboss` folder into your HA `custom_components` directory
2. Restart Home Assistant
3. Add the integration via **Settings -> Devices & Services**

---

## Configuration

During setup you will be asked to choose a connection type:

### WiFi (WebSocket)

- **Grill ID**: `PBL-` followed by 12 hex characters (e.g. `PBL-F4CFA2B1E8C4`). Find it in the PitBoss app under grill settings, or as the device hostname in your router's DHCP client list.
- **Grill Model**: select your exact model from the dropdown. This determines which entities are created and what temperature ranges are enforced.
- **Password**: the grill password from the PitBoss app (grill settings). Setup checks it against the grill and refuses a wrong one. Without the correct password, temperatures still read but every change (set temperature, probe targets, shutdown) is rejected by the grill.

### Changing the password later

If the grill rejects the stored password, Home Assistant raises a **Reauthenticate** notification. You can also change it any time from **Settings -> Devices & Services -> PitBoss -> Reconfigure**.

### Bluetooth LE

- HA will show a list of discovered PitBoss BLE devices nearby.
- Select your grill, choose the model, and enter the grill password (leave blank only if the grill has none). It is checked against the grill the same way as WiFi.

---

## Entities

Names below are shown after the device name (for example `PitBoss PB1100PSC2 Grill temperature`). Entity IDs are generated from the same text when the integration is first added, e.g. `sensor.pitboss_pb1100psc2_grill_temperature`. Renaming the device later does not change existing IDs.

### Sensors

| Entity | Description | Default |
|---|---|---|
| Status | Off, Igniting, Preheating, At temperature, Cooling down, Error | Enabled |
| Grill temperature | Current grill temperature | Enabled |
| Grill set temperature | Current set point | Enabled |
| Probe 1 to 4 | Meat probe readings (probes beyond the model's count are disabled) | Per model |
| Smoke cabinet temperature | Only on models that report it | Disabled |
| Recipe step / Recipe time remaining | App recipe progress | Disabled |

### Binary Sensors

| Entity | Description | Category |
|---|---|---|
| Problem | On when any fault is active; `active` attribute lists which | Primary |
| Pellets low | Hopper empty | Primary |
| Power | Control module powered on | Primary |
| Fan / Igniter / Auger | Component running | Diagnostic |
| Probe 1 to 3 error, Over-temperature, Fan, Igniter, Auger, Startup failure (ErL) | Individual faults | Diagnostic |

### Climate

| Entity | Description |
|---|---|
| Grill | Current and target temperature, heating/idle action, set temperature (rounded to 5 degrees and clamped to the model range), turn off. The grill must already be running to accept a new temperature; remote power-on is not supported by the grill. |

### Number

| Entity | Description |
|---|---|
| Probe 1 target / Probe 2 target | Probe alarm temperature (model-dependent) |

### Switch and Light

| Entity | Description |
|---|---|
| Pellet primer | Run the primer motor (model-dependent) |
| Light | Grill light (model-dependent) |

If the grill rejects a command, Home Assistant shows the reason in the UI (wrong password, grill not connected, grill off).

---

## Automations

### Alert when probe reaches target temperature

```yaml
alias: "Grill - Probe 1 at target"
trigger:
  - platform: numeric_state
    entity_id: sensor.pitboss_pb1100psc2_probe_1
    above: number.pitboss_pb1100psc2_probe_1_target
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "Probe 1 has reached target temperature!"
```

### Notify on pellet empty

```yaml
alias: "Grill - No Pellets Warning"
trigger:
  - platform: state
    entity_id: binary_sensor.pitboss_pb1100psc2_pellets_low
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "PitBoss pellet hopper is empty, refill needed!"
```

### Shut down grill after cook timer

```yaml
alias: "Grill - Auto shutdown after 6 hours"
trigger:
  - platform: state
    entity_id: climate.pitboss_pb1100psc2
    to: heat
    for:
      hours: 6
action:
  - service: climate.set_hvac_mode
    target:
      entity_id: climate.pitboss_pb1100psc2
    data:
      hvac_mode: "off"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Setting the temperature fails with "The grill rejected the password" | Stored grill password is wrong | Settings -> Devices & Services -> PitBoss -> Reconfigure, enter the password from the PitBoss app |
| Commands fail only some of the time with "Unauthorized" | Versions before 2026.9.1 let the password key fall behind the grill's clock | Update to 2026.9.1 or newer |
| "PitBoss grills cannot be started remotely" or "The grill is off" | Set temperature sent while the grill is off | Start the grill at the controller first |
| Integration stuck on "Configuring" | Grill off or not reachable at HA startup | Power on the grill and restart the integration |
| Entities unavailable after grill restart | BLE/WiFi reconnect in progress | Wait ~30 seconds; coordinator will reconnect automatically |
| WiFi connection drops frequently | Grill firmware enters slow-push mode | Ensure HA has outbound access to the Dansons relay; integration wakes fast mode on startup |
| Wrong temperature unit | `isFahrenheit` flag from grill | Match the unit setting on the grill's physical display |
| BLE device not discovered | Grill out of range or HA Bluetooth not configured | Ensure HA has a Bluetooth adapter; move grill closer |
| Commands timeout | Grill busy or BLE congestion | Will retry on next interaction; check logs for errors |

**Diagnostics:** Download diagnostics from the device page; the password is redacted and `auth_ok` shows whether the grill accepts it.

**Enable debug logging:**

```yaml
# configuration.yaml
logger:
  default: warning
  logs:
    custom_components.pitboss: debug
```

---

## How It Works

The integration talks to the grill's control board over one of two transports. BLE is fully local. The WiFi path relays through a Dansons-hosted cloud socket, the same relay the official PitBoss app uses; it is not a direct LAN connection.

**WiFi (WebSocket):** The grill firmware runs [Mongoose OS](https://mongoose-os.com) on an ESP32. It connects out to the Dansons WebSocket relay at `wss://socket.dansonscorp.com/to/<grill_id>` and pushes state updates every 5 seconds when active. This integration connects to the same relay endpoint (`socket.dansonscorp.com`, defined in `pytboss/wss.py`) and receives the same push frames, so the WiFi path depends on Dansons cloud availability and HA outbound internet. All grill control goes through `PB.SendMCUCommand` RPCs, which forward raw hex commands to the MCU control board via UART.

**Authentication:** Reading state never needs the grill password. Commands do: each one carries the password encoded with a key derived from the grill's uptime in 10 second buckets, and the firmware accepts only the current or next bucket. The integration reads the uptime once, extrapolates it with a small lead so it never runs behind, and retries a rejected command once with a fresh reading.

**Bluetooth LE:** The grill also exposes the Mongoose OS BLE RPC GATT service. Commands use the same JSON RPC structure sent over GATT write characteristics. State updates are broadcast via the debug log GATT notification channel as hex-encoded frames. This path involves no cloud.

**State parsing:** The grill sends two frame types: `FE0B` (status: booleans, errors, recipe) and `FE0C` (temperatures: grill, smoker, probes). Parsing and command building are driven by per-model JavaScript functions stored in the vendored `pytboss/grills.json` database. These functions are evaluated at runtime with the `dukpy` JavaScript engine (`from dukpy import evaljs` in `pytboss/grills.py`; `dukpy==0.5.1` in `manifest.json`). The model database is vendored locally, so parsing does not require a live cloud API call, but the `dukpy` dependency and the JS evaluation path are still in use.

---

## License

MIT © [Emkraan](https://github.com/Emkraan)
