"""Base class for transport protocols."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from asyncio import AbstractEventLoop, Future, Lock, get_running_loop
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Any, Protocol, Self, Type

from .exceptions import RPCError

_LOGGER = logging.getLogger(__name__)

_DEFAULT_COMMAND_TIMEOUT = 15.0


class RawStateCallback(Protocol):
    async def __call__(
        self, status_payload: str | None, temperatures_payload: str | None = None
    ) -> None: ...


RawVDataCallback = Callable[[str], Awaitable[None]]
SendCommandFn = Callable[
    [str, dict[Any, Any]],
    Awaitable[dict[Any, Any] | None],
]


class Transport(ABC):
    """Base class for transport protocols."""

    def __init__(self, loop: AbstractEventLoop | None = None) -> None:
        self._lock = Lock()
        self._futures_lock = Lock()
        self._last_command_id = 0
        self._rpc_futures: dict[int, Future[Any]] = {}
        self._state_callback: RawStateCallback | None = None
        self._vdata_callback: RawVDataCallback | None = None
        self._loop = loop or get_running_loop()

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.disconnect()

    def set_state_callback(self, state_callback: RawStateCallback) -> None:
        self._state_callback = state_callback

    def set_vdata_callback(self, vdata_callback: RawVDataCallback) -> None:
        self._vdata_callback = vdata_callback

    @abstractmethod
    async def connect(self) -> None:
        """Starts the connection to the device."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Stop the connection to the device."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Whether there is an active connection to the device."""

    @abstractmethod
    async def _send_prepared_command(self, cmd: dict) -> None: ...

    async def send_command(
        self,
        method: str,
        params: dict,
        *,
        timeout: float | None = _DEFAULT_COMMAND_TIMEOUT,
    ) -> dict:
        """Sends a command to the device and waits for a response.

        All pending futures are cancelled and cleaned up on timeout so callers
        never hang indefinitely.
        """
        cmd = await self._prepare_command(method, params)
        future: Future[Any] = self._loop.create_future()
        async with self._futures_lock:
            self._rpc_futures[cmd["id"]] = future
        try:
            async with asyncio.timeout(timeout):
                await self._send_prepared_command(cmd)
                return await future
        except (asyncio.TimeoutError, Exception):
            # Clean up the future so it doesn't linger in the dict.
            async with self._futures_lock:
                self._rpc_futures.pop(cmd["id"], None)
            if not future.done():
                future.cancel()
            raise

    async def send_command_without_answer(
        self,
        method: str,
        params: dict,
        *,
        timeout: float | None = _DEFAULT_COMMAND_TIMEOUT,
    ) -> None:
        """Sends a command to the device without waiting for a response."""
        async with asyncio.timeout(timeout):
            await self._send_prepared_command(
                await self._prepare_command(method, params)
            )

    async def _next_command_id(self) -> int:
        async with self._futures_lock:
            self._last_command_id = (self._last_command_id + 1) & 2047
            return self._last_command_id

    async def _prepare_command(self, method: str, params: dict) -> dict:
        return {"id": await self._next_command_id(), "method": method, "params": params}

    async def _on_command_response(self, payload: dict) -> bool:
        cmd_id = payload.get("id")
        if cmd_id is None:
            return False
        async with self._futures_lock:
            future = self._rpc_futures.pop(cmd_id, None)
        if not future:
            return False
        if not future.cancelled() and not future.done():
            if "error" in payload:
                future.set_exception(
                    RPCError(payload["error"].get("message", "Unknown error"))
                )
            else:
                future.set_result(payload.get("result", {}))
        return True

    def _cancel_all_pending_futures(self) -> None:
        """Cancel all pending RPC futures — call this on disconnect."""
        for future in self._rpc_futures.values():
            if not future.done():
                future.cancel()
        self._rpc_futures.clear()
