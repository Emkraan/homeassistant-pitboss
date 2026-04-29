"""Constants for the PitBoss integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "pitboss"

CONF_GRILL_ID = "grill_id"
CONF_GRILL_MODEL = "grill_model"
CONF_PASSWORD = "password"
CONF_PROTOCOL = "protocol"
CONF_ADDRESS = "address"

PROTOCOL_WSS = "wss"
PROTOCOL_BLE = "ble"

PING_INTERVAL = timedelta(seconds=30)
PING_TIMEOUT = 10.0

MIN_PROBE_TEMP = 50
MAX_PROBE_TEMP = 250

PLATFORMS = [
    "binary_sensor",
    "climate",
    "light",
    "number",
    "sensor",
    "switch",
]
