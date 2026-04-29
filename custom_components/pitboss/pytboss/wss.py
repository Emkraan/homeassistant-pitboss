"""WebSocket connection support for PitBoss grills."""

from __future__ import annotations

import asyncio
import logging
from asyncio import AbstractEventLoop, Event, Lock, Task
from typing import Any
from uuid import uuid4

from aiohttp import ClientSession, ClientWebSocketResponse, WSServerHandshakeError

from .exceptions import GrillUnavailable, NotConnectedError
from .transport import Transport

_BASE_URL = "wss://socket.dansonscorp.com"
_LOGGER = logging.getLogger(__name__)
_MAX_BACKOFF_TIME = 30.0
_CONNECT_TIMEOUT = 20.0


class WebSocketConnection(Transport):
    """WebSocket transport for PitBoss grills."""

    def __init__(
        self,
        grill_id: str,
        session: ClientSession | None = None,
        loop: AbstractEventLoop | None = None,
        app_id: str | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        super().__init__(loop=loop)
        self._session = session or ClientSession()
        self._session_owned = session is None
        self._sock_lock = Lock()
        self._sock: ClientWebSocketResponse | None = None
        self._url = f"{base_url}/to/{grill_id}"
        self._app_id = app_id or str(uuid4()).split("-")[-1]
        self._subscribe_task: Task | None = None
        self._subscribed = Event()
        self._keep_running = False

    async def connect(self) -> None:
        """Starts the connection to the device.

        Raises GrillUnavailable if the grill cannot be reached within the timeout.
        """
        if self._subscribe_task is not None and not self._subscribe_task.done():
            _LOGGER.warning("connect() called while already connected; ignoring.")
            return

        self._subscribed.clear()
        self._keep_running = True
        self._subscribe_task = self._loop.create_task(self._subscribe())

        try:
            async with asyncio.timeout(_CONNECT_TIMEOUT):
                await self._subscribed.wait()
        except asyncio.TimeoutError:
            self._keep_running = False
            if self._subscribe_task and not self._subscribe_task.done():
                self._subscribe_task.cancel()
            raise GrillUnavailable("Timed out waiting for WebSocket connection")

    async def disconnect(self) -> None:
        """Stops the connection to the device."""
        self._keep_running = False
        self._cancel_all_pending_futures()

        async with self._sock_lock:
            if self._sock and not self._sock.closed:
                await self._sock.close()

        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
            except asyncio.CancelledError:
                pass
        self._subscribe_task = None

        if self._session_owned and not self._session.closed:
            await self._session.close()

    async def _ws_connect(self) -> ClientWebSocketResponse:
        _LOGGER.debug("Connecting to %s", self._url)
        try:
            return await self._session.ws_connect(self._url)
        except WSServerHandshakeError as ex:
            raise GrillUnavailable(str(ex)) from ex

    async def _subscribe(self) -> None:
        """Reconnecting WebSocket receive loop."""
        attempt = 1
        backoff = 1.0

        while self._keep_running:
            sock: ClientWebSocketResponse | None = None
            try:
                sock = await self._ws_connect()
            except GrillUnavailable as ex:
                _LOGGER.warning(
                    "WebSocket connect failed (attempt %d): %s. Retrying in %.1fs.",
                    attempt,
                    ex,
                    backoff,
                )
                await asyncio.sleep(backoff)
                attempt += 1
                backoff = min(_MAX_BACKOFF_TIME, backoff * 2)
                continue

            attempt = 1
            backoff = 1.0

            async with self._sock_lock:
                self._sock = sock

            _LOGGER.debug("WebSocket connected")
            self._subscribed.set()

            try:
                async with sock:
                    async for msg in sock:
                        if not self._keep_running:
                            break
                        try:
                            payload = msg.json()
                        except Exception:
                            _LOGGER.warning(
                                "Received non-JSON WebSocket message; skipping."
                            )
                            continue
                        _LOGGER.debug("WSS payload: %s", payload)
                        try:
                            await self._handle_message(payload)
                        except Exception as ex:
                            _LOGGER.warning(
                                "Error handling WebSocket message: %s",
                                ex,
                                exc_info=True,
                            )
            except Exception as ex:
                if self._keep_running:
                    _LOGGER.warning("WebSocket session ended unexpectedly: %s", ex)
            finally:
                async with self._sock_lock:
                    self._sock = None
                _LOGGER.debug("WebSocket disconnected; will reconnect.")

        _LOGGER.debug("WebSocket subscribe loop exiting.")

    async def _handle_message(self, payload: dict[str, Any]) -> None:
        if "app_id" in payload and payload["app_id"] != self._app_id:
            return

        if "status" in payload:
            if self._state_callback:
                statuses = payload["status"]
                status_payload = statuses[0] if len(statuses) > 0 else None
                temp_payload = statuses[1] if len(statuses) > 1 else None
                await self._state_callback(status_payload, temp_payload)
            return

        if "id" in payload and payload.get("id", -1) != -1:
            await self._on_command_response(payload)
            return

        if payload.get("result"):
            if self._vdata_callback:
                await self._vdata_callback(payload["result"])

    def is_connected(self) -> bool:
        """Whether the device is currently connected."""
        return self._sock is not None and not self._sock.closed

    async def _send_prepared_command(self, cmd: dict) -> None:
        async with self._sock_lock:
            if self._sock is None or self._sock.closed:
                raise NotConnectedError("WebSocket is not connected")
            cmd["app_id"] = self._app_id
            _LOGGER.debug("Sending command: %s", cmd)
            await self._sock.send_json(cmd)
