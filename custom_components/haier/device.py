"""TCP transport for a Haier AC unit."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .const import DEFAULT_PORT
from .protocol import CMD_STATUS, HaierProtocol

_LOGGER = logging.getLogger(__name__)

CONNECT_TIMEOUT: float = 10.0
RESPONSE_TIMEOUT: float = 5.0
RECONNECT_BASE_DELAY: float = 2.0
RECONNECT_MAX_DELAY: float = 60.0
RECONNECT_MAX_ATTEMPTS: int = 10
COMMAND_GAP: float = 0.15  # 150 ms — matches TS library default
LISTEN_IDLE_SLEEP: float = 1.0


class DeviceNotAvailable(Exception):
    """Raised when the AC cannot be reached for a command."""


class HaierDevice:
    """Owns the TCP connection, reconnection, command gap and state cache."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connect_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._pending: list[asyncio.Future[bytes]] = []
        self._last_command_ts: float = 0.0
        self._reconnect_attempts: int = 0
        self._running: bool = False
        self._listen_task: asyncio.Task[None] | None = None
        self._loop = asyncio.get_event_loop()
        self.protocol = HaierProtocol()
        self.state: dict[str, Any] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []

    # ----- listeners -----
    def add_listener(self, cb: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[dict[str, Any]], None]) -> None:
        if cb in self._listeners:
            self._listeners.remove(cb)

    def _notify(self, state: dict[str, Any]) -> None:
        for cb in self._listeners:
            try:
                cb(state)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener callback failed")

    # ----- lifecycle -----
    async def start(self) -> None:
        self._running = True
        if not await self.async_connect():
            _LOGGER.warning(
                "Initial connect to %s:%s failed; will retry on next command",
                self._host, self._port,
            )
        self._listen_task = asyncio.create_task(self._listen_for_responses())

    async def stop(self) -> None:
        self._running = False
        if self._listen_task is not None:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        await self.async_disconnect()

    async def async_disconnect(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._reader = None
        self._writer = None

    # ----- connect with backoff (single-flight) -----
    async def async_connect(self) -> bool:
        async with self._connect_lock:
            if self._writer is not None and not self._writer.is_closing():
                return True

            delay = RECONNECT_BASE_DELAY
            for attempt in range(1, RECONNECT_MAX_ATTEMPTS + 1):
                try:
                    self._reader, self._writer = await asyncio.wait_for(
                        asyncio.open_connection(self._host, self._port),
                        timeout=CONNECT_TIMEOUT,
                    )
                    self._reconnect_attempts = 0
                    _LOGGER.info(
                        "Connected to Haier device %s:%s", self._host, self._port
                    )
                    return True
                except (OSError, asyncio.TimeoutError) as exc:
                    _LOGGER.warning(
                        "Connection attempt %d/%d to %s failed: %s",
                        attempt, RECONNECT_MAX_ATTEMPTS, self._host, exc,
                    )
                    if attempt < RECONNECT_MAX_ATTEMPTS:
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, RECONNECT_MAX_DELAY)

            _LOGGER.error(
                "Giving up on %s after %d connection attempts",
                self._host, RECONNECT_MAX_ATTEMPTS,
            )
            return False

    async def _handle_connection_lost(self) -> None:
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except (ConnectionError, OSError):
                pass
        self._reader = None
        self._writer = None

    # ----- listen/parse -----
    async def _listen_for_responses(self) -> None:
        """Read from the socket forever; never die on a single bad frame."""
        while self._running:
            reader = self._reader
            if reader is None:
                await asyncio.sleep(LISTEN_IDLE_SLEEP)
                continue

            try:
                data = await reader.read(1024)
            except asyncio.CancelledError:
                raise
            except (ConnectionError, OSError) as exc:
                _LOGGER.warning("Read error from %s: %s", self._host, exc)
                data = b""

            if not data:
                if not self._running:
                    break
                await self._handle_connection_lost()
                if not await self.async_connect():
                    _LOGGER.error(
                        "Cannot reconnect to %s; next command will retry", self._host
                    )
                continue

            try:
                frames = self.protocol.parse_response(data)
            except Exception:  # noqa: BLE001
                _LOGGER.exception(
                    "Unhandled error while parsing response from %s", self._host
                )
                continue

            for frame in frames:
                try:
                    self._dispatch_frame(frame)
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "Error handling frame from %s: %s",
                        self._host, frame.get("raw", b"").hex(),
                    )

    def _dispatch_frame(self, frame: dict[str, Any]) -> None:
        payload = frame.get("payload", b"")
        if payload and payload[0] == CMD_STATUS:
            self._update_state(payload)
        if self._pending:
            future = self._pending.pop(0)
            if not future.done():
                future.set_result(frame["raw"])

    def _update_state(self, payload: bytes) -> None:
        """Decode status payload into the cached state and notify listeners."""
        if len(payload) < 4:
            return
        self.state = {
            "raw": payload.hex(),
            "power": bool(payload[1] & 0x01),
            "mode": payload[2],
            "temperature": 16.0 + (payload[3] >> 1),
        }
        self._notify(self.state)

    # ----- command path -----
    async def _send_request(
        self, packet: bytes, expect_response: bool = True
    ) -> bytes | None:
        """Send one packet. Caller MUST hold self._command_lock."""
        if self._writer is None or self._writer.is_closing():
            if not await self.async_connect():
                raise DeviceNotAvailable(f"Cannot connect to {self._host}")

        try:
            assert self._writer is not None
            self._writer.write(packet)
            await self._writer.drain()
        except (ConnectionError, OSError) as exc:
            _LOGGER.warning("Write to %s failed: %s", self._host, exc)
            await self._handle_connection_lost()
            raise DeviceNotAvailable(str(exc)) from exc

        if not expect_response:
            return None

        future: asyncio.Future[bytes] = self._loop.create_future()
        self._pending.append(future)
        try:
            async with asyncio.timeout(RESPONSE_TIMEOUT):
                return await future
        except asyncio.TimeoutError:
            if future in self._pending:
                self._pending.remove(future)
            _LOGGER.warning(
                "No response from %s within %.1fs; keeping socket (not reconnecting)",
                self._host, RESPONSE_TIMEOUT,
            )
            return None

    async def async_send_command(self, packet: bytes) -> bytes | None:
        """Public entry point: serialise commands and enforce COMMAND_GAP."""
        async with self._command_lock:
            now = self._loop.time()
            wait = self._last_command_ts + COMMAND_GAP - now
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                return await self._send_request(packet)
            finally:
                self._last_command_ts = self._loop.time()