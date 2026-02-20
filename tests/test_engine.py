"""Tests for the Engine client.

Tests use ``httpx.ASGITransport`` pointed at the real Starlette app
so we get a genuine HTTP-level integration without starting a server.
"""

import httpx
import pytest
from app.server import app
from engine.client import EngineClient, RpcError


@pytest.fixture
async def engine():
    """EngineClient wired to the in-process Starlette app."""
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    client = EngineClient.__new__(EngineClient)
    client.base_url = "http://test"
    client.max_retries = 3
    client._client = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield client
    await client.close()


@pytest.mark.anyio
async def test_call_echo(engine):
    result = await engine.call("echo", {"msg": "hello"})
    assert result == {"msg": "hello"}


@pytest.mark.anyio
async def test_call_add(engine):
    result = await engine.call("add", {"a": 10, "b": 20})
    assert result == {"result": 30}


@pytest.mark.anyio
async def test_call_method_not_found(engine):
    with pytest.raises(RpcError) as exc_info:
        await engine.call("does_not_exist")
    assert exc_info.value.error.code == -32601


@pytest.mark.anyio
async def test_stream_generate(engine):
    events = []
    async for event in engine.stream("generate", {"tokens": 3, "delay": 0.05}):
        events.append(event)

    types = [e.get("type") for e in events]
    assert "stream_start" in types
    assert "stream_end" in types
    tokens = [e for e in events if e.get("type") == "token"]
    assert len(tokens) == 3


@pytest.mark.anyio
async def test_cancel_nonexistent_stream(engine):
    result = await engine.cancel_stream("nonexistent_id")
    assert result["cancelled"] is False
