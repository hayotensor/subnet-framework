"""Example RPC handlers — unary and streaming.

All handlers are registered on the module-level ``registry`` and
``stream_manager`` instances which the server imports.
"""

from __future__ import annotations

import logging

import anyio

from app.dispatcher import Registry
from app.streaming import StreamContext, StreamManager

log = logging.getLogger(__name__)

registry = Registry()
stream_manager = StreamManager()

# ── Unary handlers ───────────────────────────────────────────────────


@registry.handler("echo")
async def echo(params: dict) -> dict:
    """Return params unchanged."""
    return params


@registry.handler("add")
async def add(params: dict) -> dict:
    """Add two numbers."""
    a = params.get("a", 0)
    b = params.get("b", 0)
    return {"result": a + b}


# ── Streaming handlers ──────────────────────────────────────────────

STREAMING_METHODS = {"generate"}


@registry.handler("generate")
async def generate(params: dict) -> str:
    """Placeholder — actual streaming is handled by the server route.

    This handler is registered so that ``registry.is_registered``
    returns True for dispatch validation.  The real work happens
    in ``_generate_stream`` below.
    """
    return "use streaming endpoint"


async def generate_stream(params: dict, ctx: StreamContext) -> None:
    """Streaming handler: emit token events with simulated delay."""
    prompt = params.get("prompt", "")
    tokens = params.get("tokens", 5)
    delay = params.get("delay", 0.3)

    for i in range(tokens):
        if ctx.cancelled:
            break
        await ctx.emit(
            {
                "type": "token",
                "index": i,
                "token": f"tok_{i}",
                "prompt": prompt,
            }
        )
        await anyio.sleep(delay)

    if not ctx.cancelled:
        await ctx.emit({"type": "done", "total": tokens})


# ── Stream cancellation (control method) ─────────────────────────────


@registry.handler("engine.stream.cancel")
async def cancel_stream(params: dict) -> dict:
    """Cancel a running stream by ID."""
    stream_id = params.get("stream_id")
    if not stream_id:
        return {"cancelled": False, "error": "missing stream_id"}
    ok = stream_manager.cancel_stream(stream_id)
    return {"cancelled": ok, "stream_id": stream_id}


# ── Lookup helper for streaming methods ──────────────────────────────

STREAM_HANDLERS = {
    "generate": generate_stream,
}


def get_stream_handler(method: str):
    """Return the streaming handler function for *method*, or None."""
    return STREAM_HANDLERS.get(method)
