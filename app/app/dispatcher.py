"""Method dispatch registry.

Handlers register themselves via the ``@registry.handler`` decorator.
The dispatcher maps JSON-RPC method names to async callables — nothing more.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from shared.jsonrpc import METHOD_NOT_FOUND

log = logging.getLogger(__name__)

# Type alias for an RPC handler: async (params) -> result
HandlerFn = Callable[[dict[str, Any]], Awaitable[Any]]


class MethodNotFoundError(Exception):
    """Raised when no handler is registered for the requested method."""

    def __init__(self, method: str) -> None:
        self.method = method
        self.code = METHOD_NOT_FOUND
        super().__init__(f"Method not found: {method}")


class Registry:
    """A simple method → handler mapping.

    Usage::

        registry = Registry()

        @registry.handler("echo")
        async def echo(params):
            return params

        result = await registry.dispatch("echo", {"msg": "hi"})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    # -- Registration --------------------------------------------------
    def handler(self, method: str) -> Callable[[HandlerFn], HandlerFn]:
        """Decorator that registers *fn* under *method*."""

        def decorator(fn: HandlerFn) -> HandlerFn:
            if method in self._handlers:
                log.warning("overwriting handler for %r", method)
            self._handlers[method] = fn
            log.debug("registered handler %r → %s", method, fn.__qualname__)
            return fn

        return decorator

    # -- Dispatch ------------------------------------------------------
    async def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        """Call the handler for *method* and return its result.

        Raises ``MethodNotFoundError`` if the method is not registered.
        """
        fn = self._handlers.get(method)
        if fn is None:
            raise MethodNotFoundError(method)
        return await fn(params)

    # -- Introspection -------------------------------------------------
    @property
    def methods(self) -> list[str]:
        return list(self._handlers.keys())

    def is_registered(self, method: str) -> bool:
        return method in self._handlers
