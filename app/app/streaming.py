"""Streaming infrastructure.

* ``StreamManager`` — in-memory registry of running streams.
* ``StreamContext``  — passed into streaming handlers so they can emit
  events and check for cancellation.

Every stream runs inside an ``anyio`` task group with a strict timeout
and a bounded output buffer for back-pressure.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Awaitable, Callable

import anyio
from anyio.abc import CancelScope

log = logging.getLogger(__name__)

# Defaults
DEFAULT_STREAM_TIMEOUT = 120.0  # seconds
DEFAULT_BUFFER_SIZE = 64  # max queued events before back-pressure


@dataclass(slots=True)
class _StreamEntry:
    """Internal bookkeeping for one active stream."""

    stream_id: str
    cancel_scope: CancelScope | None = None
    done: bool = False


class StreamContext:
    """Handle given to a streaming handler.

    The handler uses ``await ctx.emit(event)`` to push events, and can
    check ``ctx.cancelled`` to bail out early.
    """

    def __init__(
        self,
        stream_id: str,
        send: anyio.abc.ObjectSendStream,
        cancel_scope: CancelScope,
    ) -> None:
        self.stream_id = stream_id
        self._send = send
        self._cancel_scope = cancel_scope

    @property
    def cancelled(self) -> bool:
        return self._cancel_scope.cancel_called

    async def emit(self, event: dict[str, Any]) -> None:
        """Push an event into the output buffer.

        Blocks if the buffer is full (back-pressure).
        """
        if self.cancelled:
            return
        await self._send.send(event)


# Type alias for streaming handler
StreamHandlerFn = Callable[[dict[str, Any], StreamContext], Awaitable[None]]


class StreamManager:
    """Owns all active streams.  Engine cancels via ``cancel_stream``."""

    def __init__(
        self,
        timeout: float = DEFAULT_STREAM_TIMEOUT,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> None:
        self._timeout = timeout
        self._buffer_size = buffer_size
        self._streams: dict[str, _StreamEntry] = {}

    # -- Public API ----------------------------------------------------

    def new_stream_id(self) -> str:
        return uuid.uuid4().hex

    async def run_stream(
        self,
        handler: StreamHandlerFn,
        params: dict[str, Any],
        stream_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run *handler* in a task group and yield events as they arrive.

        The returned async iterator is what the server turns into SSE.
        """
        stream_id = stream_id or self.new_stream_id()
        send, recv = anyio.create_memory_object_stream[dict[str, Any]](
            max_buffer_size=self._buffer_size,
        )
        entry = _StreamEntry(stream_id=stream_id)
        self._streams[stream_id] = entry

        async def _run() -> None:
            try:
                with anyio.move_on_after(self._timeout) as scope:
                    entry.cancel_scope = scope
                    ctx = StreamContext(stream_id, send, scope)
                    await handler(params, ctx)
            except Exception:
                log.exception("stream %s handler error", stream_id)
            finally:
                await send.aclose()
                entry.done = True

        async with anyio.create_task_group() as tg:
            tg.start_soon(_run)

            async with recv:
                async for event in recv:
                    yield event

        self._streams.pop(stream_id, None)
        log.debug("stream %s finished", stream_id)

    def cancel_stream(self, stream_id: str) -> bool:
        """Cancel a running stream.  Returns True if found."""
        entry = self._streams.get(stream_id)
        if entry is None or entry.done:
            return False
        if entry.cancel_scope is not None:
            entry.cancel_scope.cancel()
            log.info("cancelled stream %s", stream_id)
            return True
        return False

    @property
    def active_streams(self) -> list[str]:
        return [sid for sid, e in self._streams.items() if not e.done]
