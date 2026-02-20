"""JSON-RPC 2.0 wire-format models.

Pure data — no I/O, no business logic.  Both Engine and Application
import these for serialisation only.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

# ── Standard error codes (JSON-RPC 2.0 §5.1) ────────────────────────
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


# ── Models ───────────────────────────────────────────────────────────
@dataclass(slots=True)
class JsonRpcError:
    """JSON-RPC 2.0 error object."""

    code: int
    message: str
    data: Any = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


@dataclass(slots=True)
class JsonRpcRequest:
    """Inbound JSON-RPC 2.0 request.

    ``id`` is auto-generated if not supplied (unary calls).
    Notifications (no ``id``) are not supported in this design.
    """

    method: str
    params: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    jsonrpc: str = "2.0"

    # -- Convenience ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "JsonRpcRequest":
        """Parse a raw dict into a request — raises ``ValueError`` on bad input."""
        if not isinstance(raw, dict):
            raise ValueError("request must be a JSON object")
        if raw.get("jsonrpc") != "2.0":
            raise ValueError("missing or invalid 'jsonrpc' field")
        method = raw.get("method")
        if not isinstance(method, str) or not method:
            raise ValueError("missing or invalid 'method' field")
        params = raw.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("'params' must be a JSON object")
        req_id = raw.get("id")
        if req_id is None:
            req_id = uuid.uuid4().hex
        return cls(method=method, params=params, id=str(req_id))


@dataclass(slots=True)
class JsonRpcResponse:
    """Outbound JSON-RPC 2.0 response."""

    id: str
    result: Any = None
    error: JsonRpcError | None = None
    jsonrpc: str = "2.0"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error.to_dict()
        else:
            d["result"] = self.result
        return d

    # -- Factories -----------------------------------------------------
    @classmethod
    def success(cls, req_id: str, result: Any) -> "JsonRpcResponse":
        return cls(id=req_id, result=result)

    @classmethod
    def fail(
        cls, req_id: str | None, code: int, message: str, data: Any = None
    ) -> "JsonRpcResponse":
        return cls(
            id=req_id or "null",
            error=JsonRpcError(code=code, message=message, data=data),
        )
