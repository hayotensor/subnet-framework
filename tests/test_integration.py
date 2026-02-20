"""Integration tests — full roundtrip through both compartments.

Uses httpx.ASGITransport for a realistic HTTP test without processes.
"""

import httpx
import pytest
from app.server import app
from engine.client import EngineClient


@pytest.fixture
async def engine():
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    client = EngineClient.__new__(EngineClient)
    client.base_url = "http://test"
    client.max_retries = 3
    client._client = httpx.AsyncClient(transport=transport, base_url="http://test")
    yield client
    await client.close()


@pytest.mark.anyio
async def test_full_unary_roundtrip(engine):
    """Engine → App → Engine: unary echo."""
    result = await engine.call("echo", {"roundtrip": True, "value": 42})
    assert result == {"roundtrip": True, "value": 42}


@pytest.mark.anyio
async def test_full_streaming_roundtrip(engine):
    """Engine → App → Engine: streaming generate."""
    events = []
    async for event in engine.stream(
        "generate", {"prompt": "integration", "tokens": 4, "delay": 0.01}
    ):
        events.append(event)

    # Verify the full lifecycle
    assert events[0]["type"] == "stream_start"
    assert events[-1]["type"] == "stream_end"

    tokens = [e for e in events if e.get("type") == "token"]
    assert len(tokens) == 4
    assert all(e["prompt"] == "integration" for e in tokens)


@pytest.mark.anyio
async def test_sequential_calls_are_independent(engine):
    """Multiple calls should not share state."""
    r1 = await engine.call("add", {"a": 1, "b": 2})
    r2 = await engine.call("add", {"a": 100, "b": 200})
    assert r1 == {"result": 3}
    assert r2 == {"result": 300}


@pytest.mark.anyio
async def test_error_does_not_corrupt_connection(engine):
    """A failed call should not break subsequent calls."""
    # This should fail
    try:
        await engine.call("nonexistent")
    except Exception:
        pass

    # This should still work
    result = await engine.call("echo", {"still": "works"})
    assert result == {"still": "works"}
