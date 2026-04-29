<div align="center">
  <img src="https://raw.githubusercontent.com/Emkraan/homeassistant-pitboss/main/.github/homeassistant-pitboss.png" alt="PitBoss" width="120" />
  <h1>PitBoss for Home Assistant</h1>
  <p>Local-only Home Assistant integration for PitBoss pellet grills — WiFi and Bluetooth LE.</p>

  [![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
  [![Release](https://img.shields.io/github/v/release/Emkraan/homeassistant-pitboss)](https://github.com/Emkraan/homeassistant-pitboss/releases)
  [![HA Version](https://img.shields.io/badge/HA-2024.1.0%2B-blue)](https://www.home-assistant.io)
  [![License](https://img.shields.io/github/license/Emkraan/homeassistant-pitboss)](LICENSE)
</div>

> **Unofficial integration.** Not affiliated with or endorsed by Dansons Inc. or PitBoss.

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

- **100% local** — no cloud, no account required
- **WiFi (WebSocket)** connection for full range — preferred when available
- **Bluetooth LE** connection for proximity use — primary fallback
- **Auto-discovery** of BLE devices on the HA Bluetooth integration
- **Full model support** for all PitBoss and Louisiana Grills pellet grill models
- **Climate entity** — monitor and set grill temperature, shut down remotely
- **Probe sensors** — up to 4 meat probes with target temperature control
- **Error monitoring** — probe errors, fan/igniter/auger faults, pellet level, ErL
- **Recipe tracking** — current step and time remaining
- **Primer motor and grill light** control (model-dependent)
- **Reliable reconnection** — exponential backoff with proper timeout handling

---

## Requirements

| Requirement | Detail |
|---|---|
| Home Assistant | 2024.1.0 or newer |
| HACS | 1.34.0 or newer |
| Connection | WiFi grill ID **or** Bluetooth LE adapter on your HA host |
| Grill | Any PitBoss or Louisiana Grills WiFi-enabled pellet grill |

---

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add `https://github.com/Emkraan/homeassistant-pitboss` as an **Integration**
4. Search for **PitBoss** and install
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration** and search for **PitBoss**

### Manual

1. Copy the `custom_components/pitboss` folder into your HA `custom_components` directory
2. Restart Home Assistant
3. Add the integration via **Settings → Devices & Services**

---

## Configuration

During setup you will be asked to choose a connection type:

### WiFi (WebSocket)

- **Grill ID** — the device name as registered in the PitBoss app (e.g. `PBL-MyGrill`). Find it in the app under device settings or your router's DHCP client list.
- **Grill Model** — select your exact model from the dropdown. This determines which entities are created and what temperature ranges are enforced.
- **Password** (optional) — if you have set a grill password in the app, enter it here. Leave blank otherwise.

### Bluetooth LE

- HA will show a list of discovered PitBoss BLE devices nearby.
- Select your grill, choose the model, and optionally enter a password.

---

## Entities

### Sensors

| Entity | Description | Unit |
|---|---|---|
| Grill Temperature | Current grill grate temperature | °F / °C |
| Grill Set Temperature | Current grill target setpoint | °F / °C |
| Smoker Temperature | Firebox/smoker actual temperature | °F / °C |
| Probe 1–4 Temperature | Current meat probe readings | °F / °C |
| Probe 1–2 Target | Probe target temperatures | °F / °C |
| Recipe Step | Current recipe step number | — |
| Recipe Time Remaining | Seconds remaining in current recipe step | s |

### Binary Sensors

| Entity | Description |
|---|---|
| Module On | Control module powered on |
| Fan Running | Combustion fan state |
| Igniter On | Hot rod / igniter state |
| Auger Running | Auger motor state |
| Probe 1–3 Error | Meat probe fault |
| High Temp Error | Over-temperature fault |
| Fan Error | Fan fault |
| Igniter Error | Igniter fault |
| Auger Error | Auger motor fault |
| No Pellets | Pellet hopper empty |
| Startup Error (ErL) | Startup cycle failure |

### Climate

| Entity | Description |
|---|---|
| Grill | Set target temperature or turn grill off. Remote power-on is not supported — use physical controls. |

### Number

| Entity | Description | Models |
|---|---|---|
| Probe 1 Target Temperature | Set probe 1 alert temperature | All with probe 1 |
| Probe 2 Target Temperature | Set probe 2 alert temperature | PBA, PBB, and similar |

### Switch

| Entity | Description | Models |
|---|---|---|
| Primer Motor | Activate/deactivate primer | Models with primer |

### Light

| Entity | Description | Models |
|---|---|---|
| Grill Light | Toggle grill light | Models with light |

---

## Automations

### Alert when probe reaches target temperature

```yaml
alias: "Grill - Probe 1 at target"
trigger:
  - platform: numeric_state
    entity_id: sensor.pitboss_probe1_temp
    above: sensor.pitboss_probe1_target
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
    entity_id: binary_sensor.pitboss_no_pellets
    to: "on"
action:
  - service: notify.mobile_app_your_phone
    data:
      message: "PitBoss pellet hopper is empty — refill needed!"
```

### Shut down grill after cook timer

```yaml
alias: "Grill - Auto shutdown after 6 hours"
trigger:
  - platform: state
    entity_id: climate.pitboss_grill
    to: heat
    for:
      hours: 6
action:
  - service: climate.set_hvac_mode
    target:
      entity_id: climate.pitboss_grill
    data:
      hvac_mode: "off"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Integration stuck on "Configuring" | Grill off or not reachable at HA startup | Power on the grill and restart the integration |
| Entities unavailable after grill restart | BLE/WiFi reconnect in progress | Wait ~30 seconds; coordinator will reconnect automatically |
| WiFi connection drops frequently | Grill firmware enters slow-push mode | Ensure HA can reach the WebSocket server; integration wakes fast mode on startup |
| Wrong temperature unit | `isFahrenheit` flag from grill | Match the unit setting on the grill's physical display |
| BLE device not discovered | Grill out of range or HA Bluetooth not configured | Ensure HA has a Bluetooth adapter; move grill closer |
| Commands timeout | Grill busy or BLE congestion | Will retry on next interaction; check logs for errors |

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

This integration communicates directly with the grill over your local network or Bluetooth — no cloud required.

**WiFi (WebSocket):** The grill firmware runs [Mongoose OS](https://mongoose-os.com) on an ESP32. It connects to a Dansons WebSocket relay at `wss://socket.dansonscorp.com/to/<grill_id>` and pushes state updates every 5 seconds when active. This integration connects to the same relay endpoint and receives the same push frames. All grill control goes through `PB.SendMCUCommand` RPCs, which forward raw hex commands to the MCU control board via UART.

**Bluetooth LE:** The grill also exposes the Mongoose OS BLE RPC GATT service. Commands use the same JSON RPC structure sent over GATT write characteristics. State updates are broadcast via the debug log GATT notification channel as hex-encoded frames.

**State parsing:** The grill sends two frame types — `FE0B` (status: booleans, errors, recipe) and `FE0C` (temperatures: grill, smoker, probes). Both are decoded directly in Python — no JavaScript engine required (the original library used `dukpy` to evaluate JS from the cloud API; all parsing is ported to native Python here with the `grills.json` model database vendored locally).

---

## License

MIT © [Emkraan](https://github.com/Emkraan)
