"""Engine client — thin JSON-RPC 2.0 consumer.

* ``call(method, params)``   → unary result
* ``stream(method, params)`` → async iterator of SSE events
* ``cancel_stream(id)``      → tell Application to cancel a stream

Uses ``httpx.AsyncClient`` with connection pooling.
**Never** imports from ``app/``.

Run directly for a quick demo::

    python -m engine.client
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx
from shared.jsonrpc import JsonRpcError, JsonRpcRequest

from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception_type

log = logging.getLogger(__name__)


class RpcError(Exception):
    """Raised when the Application returns a JSON-RPC error."""

    def __init__(self, error: JsonRpcError) -> None:
        self.error = error
        super().__init__(f"[{error.code}] {error.message}")


class EngineClient:
    """Thin async client that talks JSON-RPC 2.0 over HTTP.

    Parameters
    ----------
    base_url : str
        Application server origin, e.g. ``http://127.0.0.1:8100``.
    timeout : float
        Default request timeout in seconds.
    max_retries : int
        Max connection-level retries.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8100",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
        )

    # -- Lifecycle -----------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "EngineClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # -- Internal retry helper -----------------------------------------

    def _get_retrier(self) -> AsyncRetrying:
        return AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=0.5, max=10),
            retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
            reraise=True,
        )

    # -- Unary RPC -----------------------------------------------------

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a unary JSON-RPC request and return the result.

        Raises ``RpcError`` if the Application returns a JSON-RPC error.
        """
        req = JsonRpcRequest(method=method, params=params or {})
        payload = req.to_dict()

        log.debug("rpc → %s(id=%s)", method, req.id)

        async for attempt in self._get_retrier():
            with attempt:
                resp = await self._client.post("/rpc", json=payload)
                resp.raise_for_status()

        data = resp.json()
        if "error" in data and data["error"] is not None:
            err = JsonRpcError(**data["error"])
            raise RpcError(err)

        return data.get("result")

    # -- Streaming RPC -------------------------------------------------

    async def stream(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a streaming JSON-RPC request and yield SSE events.

        Each yielded dict is a parsed SSE ``data:`` line.
        """
        req = JsonRpcRequest(method=method, params=params or {})
        payload = req.to_dict()

        log.debug("rpc stream → %s(id=%s)", method, req.id)

        # We retry the initial connection establishment
        async for attempt in self._get_retrier():
            with attempt:
                resp_cm = self._client.stream("POST", "/rpc", json=payload)
                resp = await resp_cm.__aenter__()
                resp.raise_for_status()

        try:
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                raw = line[len("data:") :].strip()
                try:
                    event = json.loads(raw)
                    yield event
                except json.JSONDecodeError:
                    log.warning("bad SSE line: %r", line)
        finally:
            await resp_cm.__aexit__(None, None, None)

    # -- Cancel a stream -----------------------------------------------

    async def cancel_stream(self, stream_id: str) -> dict[str, Any]:
        """Request cancellation of an active stream."""
        return await self.call("engine.stream.cancel", {"stream_id": stream_id})


# ── Demo entrypoint ──────────────────────────────────────────────────


async def _demo() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async with EngineClient() as client:
        # Unary calls
        print("── echo ──")
        result = await client.call("echo", {"msg": "hello from engine"})
        print(f"  result: {result}")

        print("── add ──")
        result = await client.call("add", {"a": 17, "b": 25})
        print(f"  result: {result}")

        # Streaming call
        print("── generate (stream) ──")
        async for event in client.stream("generate", {"prompt": "test", "tokens": 5, "delay": 0.2}):
            print(f"  event: {event}")

        print("── done ──")


if __name__ == "__main__":
    import anyio

    anyio.run(_demo)
