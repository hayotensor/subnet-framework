"""Tests for the Application compartment /rpc endpoint.

Uses ``httpx.ASGITransport`` to test Starlette in-process without
starting a real server.
"""

import httpx
import pytest
from app.server import app


@pytest.fixture
def client():
    """In-process async test client."""
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://test")


# ── Unary tests ──────────────────────────────────────────────────────


@pytest.mark.anyio
async def test_echo(client):
    resp = await client.post(
        "/rpc", json={"jsonrpc": "2.0", "method": "echo", "params": {"msg": "hi"}, "id": "1"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["result"] == {"msg": "hi"}
    assert data["id"] == "1"


@pytest.mark.anyio
async def test_add(client):
    resp = await client.post(
        "/rpc", json={"jsonrpc": "2.0", "method": "add", "params": {"a": 3, "b": 4}, "id": "2"}
    )
    data = resp.json()
    assert data["result"] == {"result": 7}


@pytest.mark.anyio
async def test_method_not_found(client):
    resp = await client.post(
        "/rpc", json={"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": "3"}
    )
    data = resp.json()
    assert data["error"]["code"] == -32601  # METHOD_NOT_FOUND


@pytest.mark.anyio
async def test_parse_error(client):
    resp = await client.post(
        "/rpc",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    data = resp.json()
    assert data["error"]["code"] == -32700  # PARSE_ERROR


@pytest.mark.anyio
async def test_invalid_request(client):
    resp = await client.post("/rpc", json={"jsonrpc": "1.0", "method": "echo"})
    data = resp.json()
    assert data["error"]["code"] == -32600  # INVALID_REQUEST


# ── Streaming tests ──────────────────────────────────────────────────


@pytest.mark.anyio
async def test_streaming_generate(client):
    """Streaming response returns SSE events."""
    async with client.stream(
        "POST",
        "/rpc",
        json={
            "jsonrpc": "2.0",
            "method": "generate",
            "params": {"tokens": 3, "delay": 0.05},
            "id": "s1",
        },
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        events = []
        async for line in resp.aiter_lines():
            line = line.strip()
            if line.startswith("data:"):
                import json

                events.append(json.loads(line[5:].strip()))

    # Expect: stream_start, 3 tokens, done, stream_end
    types = [e.get("type") for e in events]
    assert types[0] == "stream_start"
    assert types[-1] == "stream_end"
    token_events = [e for e in events if e.get("type") == "token"]
    assert len(token_events) == 3
