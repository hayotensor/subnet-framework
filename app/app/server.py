"""Application compartment — Starlette ASGI server.

Single ``/rpc`` POST endpoint that handles both unary and streaming
JSON-RPC 2.0 requests.

Run directly::

    python -m app.server
"""

from __future__ import annotations

import json
import logging

from shared.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    PARSE_ERROR,
    JsonRpcRequest,
    JsonRpcResponse,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

from app.dispatcher import MethodNotFoundError
from app.handlers import (
    STREAMING_METHODS,
    get_stream_handler,
    registry,
    stream_manager,
)

log = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────


def _error_response(req_id: str | None, code: int, msg: str, status: int = 200) -> JSONResponse:
    """Build a JSON-RPC error response."""
    resp = JsonRpcResponse.fail(req_id, code, msg)
    return JSONResponse(resp.to_dict(), status_code=status)


async def _sse_generator(method: str, params: dict, stream_id: str):
    """Yield SSE-formatted lines from a streaming handler."""
    handler = get_stream_handler(method)
    if handler is None:
        yield f"data: {json.dumps({'error': 'no stream handler'})}\n\n"
        return

    # Emit the stream_id first so Engine can cancel later
    yield f"data: {json.dumps({'type': 'stream_start', 'stream_id': stream_id})}\n\n"

    async for event in stream_manager.run_stream(handler, params, stream_id=stream_id):
        yield f"data: {json.dumps(event)}\n\n"

    yield f"data: {json.dumps({'type': 'stream_end', 'stream_id': stream_id})}\n\n"


# ── RPC endpoint ─────────────────────────────────────────────────────


async def rpc_endpoint(request: Request) -> JSONResponse | StreamingResponse:
    """Handle a JSON-RPC 2.0 POST to ``/rpc``."""
    req_id: str | None = None

    try:
        body = await request.body()
        raw = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _error_response(None, PARSE_ERROR, "Parse error")

    try:
        rpc_req = JsonRpcRequest.from_dict(raw)
        req_id = rpc_req.id
    except ValueError as exc:
        return _error_response(None, INVALID_REQUEST, str(exc))

    log.info("rpc ← %s(id=%s)", rpc_req.method, req_id)

    # ── Streaming path ───────────────────────────────────────────
    if rpc_req.method in STREAMING_METHODS:
        stream_id = stream_manager.new_stream_id()
        return StreamingResponse(
            _sse_generator(rpc_req.method, rpc_req.params, stream_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Stream-Id": stream_id,
            },
        )

    # ── Unary path ───────────────────────────────────────────────
    try:
        result = await registry.dispatch(rpc_req.method, rpc_req.params)
        resp = JsonRpcResponse.success(req_id, result)
        return JSONResponse(resp.to_dict())
    except MethodNotFoundError as exc:
        return _error_response(req_id, exc.code, str(exc))
    except Exception as exc:
        log.exception("handler error for %s", rpc_req.method)
        return _error_response(req_id, INTERNAL_ERROR, f"Internal error: {exc}")


# ── App factory ──────────────────────────────────────────────────────


def create_app() -> Starlette:
    return Starlette(
        debug=False,
        routes=[Route("/rpc", rpc_endpoint, methods=["POST"])],
    )


app = create_app()


# ── Runnable entrypoint ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    uvicorn.run(
        "app.server:app",
        host="127.0.0.1",
        port=8100,
        log_level="info",
    )
