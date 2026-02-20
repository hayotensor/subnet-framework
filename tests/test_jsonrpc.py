"""Tests for shared JSON-RPC 2.0 models."""

import pytest
from shared.jsonrpc import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
)


class TestJsonRpcRequest:
    def test_to_dict(self):
        req = JsonRpcRequest(method="echo", params={"a": 1}, id="abc")
        d = req.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["method"] == "echo"
        assert d["params"] == {"a": 1}
        assert d["id"] == "abc"

    def test_from_dict_valid(self):
        raw = {"jsonrpc": "2.0", "method": "test", "params": {"x": 1}, "id": "1"}
        req = JsonRpcRequest.from_dict(raw)
        assert req.method == "test"
        assert req.params == {"x": 1}
        assert req.id == "1"

    def test_from_dict_auto_id(self):
        raw = {"jsonrpc": "2.0", "method": "test"}
        req = JsonRpcRequest.from_dict(raw)
        assert req.method == "test"
        assert req.id  # auto-generated, non-empty

    def test_from_dict_missing_jsonrpc(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            JsonRpcRequest.from_dict({"method": "test"})

    def test_from_dict_missing_method(self):
        with pytest.raises(ValueError, match="method"):
            JsonRpcRequest.from_dict({"jsonrpc": "2.0"})

    def test_from_dict_bad_params(self):
        with pytest.raises(ValueError, match="params"):
            JsonRpcRequest.from_dict({"jsonrpc": "2.0", "method": "t", "params": [1, 2]})

    def test_from_dict_not_dict(self):
        with pytest.raises(ValueError, match="JSON object"):
            JsonRpcRequest.from_dict("hello")  # type: ignore


class TestJsonRpcResponse:
    def test_success(self):
        resp = JsonRpcResponse.success("1", {"value": 42})
        d = resp.to_dict()
        assert d["jsonrpc"] == "2.0"
        assert d["id"] == "1"
        assert d["result"] == {"value": 42}
        assert "error" not in d

    def test_fail(self):
        resp = JsonRpcResponse.fail("2", METHOD_NOT_FOUND, "Method not found")
        d = resp.to_dict()
        assert d["id"] == "2"
        assert d["error"]["code"] == METHOD_NOT_FOUND
        assert d["error"]["message"] == "Method not found"
        assert "result" not in d

    def test_fail_no_id(self):
        resp = JsonRpcResponse.fail(None, PARSE_ERROR, "bad")
        assert resp.id == "null"


class TestJsonRpcError:
    def test_to_dict_without_data(self):
        err = JsonRpcError(code=INTERNAL_ERROR, message="oops")
        d = err.to_dict()
        assert d == {"code": INTERNAL_ERROR, "message": "oops"}
        assert "data" not in d

    def test_to_dict_with_data(self):
        err = JsonRpcError(code=INTERNAL_ERROR, message="oops", data={"trace": "..."})
        d = err.to_dict()
        assert d["data"] == {"trace": "..."}


class TestErrorCodes:
    def test_standard_codes(self):
        assert PARSE_ERROR == -32700
        assert INVALID_REQUEST == -32600
        assert METHOD_NOT_FOUND == -32601
        assert INTERNAL_ERROR == -32603
