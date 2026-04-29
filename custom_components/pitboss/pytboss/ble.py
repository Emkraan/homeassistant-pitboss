"""Bluetooth LE connection support for Mongoose OS devices."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable
from uuid import UUID

import bleak_retry_connector
from bleak import BleakClient, BleakGATTCharacteristic, BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache

from .exceptions import NotConnectedError
from .transport import Transport

_LOGGER = logging.getLogger(__name__)


def _uuid(s: str) -> str:
    return str(UUID(bytes=s.encode()))


SERVICE_DEBUG = _uuid("_mOS_DBG_SVC_ID_")
CHAR_DEBUG_LOG = _uuid("0mOS_DBG_log___0")

SERVICE_RPC = _uuid("_mOS_RPC_SVC_ID_")
CHAR_RPC_DATA = _uuid("_mOS_RPC_data___")
CHAR_RPC_TX_CTL = _uuid("_mOS_RPC_tx_ctl_")
CHAR_RPC_RX_CTL = _uuid("_mOS_RPC_rx_ctl_")

DisconnectCallback = Callable[[BleakClient], None]


class BleConnection(Transport):
    """Bluetooth LE protocol transport for Mongoose OS devices."""

    def __init__(
        self,
        ble_device: BLEDevice,
        disconnect_callback: DisconnectCallback | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        super().__init__(loop=loop)
        self._ble_device: BLEDevice = ble_device
        self._disconnect_callback = disconnect_callback
        self._is_connected = False
        self._reconnecting = False

    async def connect(self) -> None:
        """Starts the connection to the device."""
        if self._is_connected:
            _LOGGER.warning("Already connected. Ignoring call to connect().")
            return
        self._ble_client = await bleak_retry_connector.establish_connection(
            client_class=BleakClientWithServiceCache,
            device=self._ble_device,
            name=self._ble_device.name or "<unknown>",
            disconnected_callback=self._on_disconnected,
        )
        self._is_connected = True
        await self._ble_client.start_notify(CHAR_RPC_RX_CTL, self._on_rpc_data_received)
        await self._ble_client.start_notify(CHAR_DEBUG_LOG, self._on_debug_log_received)

    def _on_disconnected(self, client: BleakClient) -> None:
        _LOGGER.debug("Bluetooth disconnected.")
        self._is_connected = False
        self._cancel_all_pending_futures()
        if not self._reconnecting and self._disconnect_callback is not None:
            self._disconnect_callback(client)

    async def disconnect(self) -> None:
        _LOGGER.debug("Disconnecting from device.")
        self._cancel_all_pending_futures()
        if self._ble_client:
            try:
                await self._ble_client.disconnect()
            except Exception as ex:
                _LOGGER.debug("Failed to disconnect cleanly: %s", ex)
        self._is_connected = False

    async def reset_device(self, ble_device: BLEDevice) -> None:
        """Resets the BLE device used for transport."""
        self._reconnecting = True
        _LOGGER.debug("Resetting device to: %s", ble_device)
        try:
            await self.disconnect()
            self._ble_device = ble_device
            await self.connect()
        except Exception as ex:
            _LOGGER.warning("Failed to reset BLE device: %s", ex)
            raise
        finally:
            self._reconnecting = False

    def is_connected(self) -> bool:
        return self._is_connected

    async def _send_prepared_command(self, cmd: dict) -> None:
        if not self._is_connected or self._ble_client is None:
            raise NotConnectedError("BLE device is not connected")
        payload = json.dumps(cmd)
        async with self._lock:
            await self._ble_client.write_gatt_char(
                CHAR_RPC_TX_CTL, _encode_len(len(payload))
            )
            for i in range(0, len(payload), 20):
                chunk = bytearray(payload[i : i + 20].encode("utf-8"))
                await self._ble_client.write_gatt_char(CHAR_RPC_DATA, chunk)

    async def _on_rpc_data_received(
        self, unused_char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        if self._ble_client is None:
            return
        try:
            resp_len = _decode_len(data)
            resp = bytearray()
            async with self._lock:
                while len(resp) < resp_len:
                    resp += await self._ble_client.read_gatt_char(CHAR_RPC_DATA)
            payload = json.loads(resp.decode("utf-8"))
            await self._on_command_response(payload)
        except Exception as ex:
            _LOGGER.warning("Error processing BLE RPC response: %s", ex, exc_info=True)

    async def _on_debug_log_received(
        self, unused_char: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        _LOGGER.debug("Debug log received: %s", data)
        try:
            parts = data.decode("utf-8").split()
            if len(parts) != 3:
                return

            head, payload, tail = parts
            checksum = int(tail[1 : len(tail) - 1])
            if len(payload) != checksum:
                _LOGGER.debug(
                    "Ignoring message with bad checksum (%d != %d)",
                    len(payload),
                    checksum,
                )
                return

            if head == "<==PB:" and self._state_callback:
                status_payload = temperatures_payload = None
                match payload[:4]:
                    case "FE0B":
                        status_payload = payload
                    case "FE0C":
                        temperatures_payload = payload
                await self._state_callback(status_payload, temperatures_payload)
            elif head == "<==PBD:" and self._vdata_callback:
                await self._vdata_callback(payload)
        except Exception as ex:
            _LOGGER.warning("Error processing BLE debug log: %s", ex, exc_info=True)


def _encode_len(n: int) -> bytearray:
    ret = bytearray([0, 0, 0, 0])
    for i in range(4):
        ret[3 - i] = 255 & n
        n >>= 8
    return ret


def _decode_len(n: bytearray) -> int:
    return n[0] << 24 | n[1] << 16 | n[2] << 8 | n[3]
