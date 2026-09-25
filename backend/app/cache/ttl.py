"""Tiny in-memory TTL cache with LRU eviction + per-key request coalescing."""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Hashable

_MISSING = object()


class TTLCache:
    def __init__(self, ttl_s: float, max_items: int = 2000):
        self.ttl = ttl_s
        self.max_items = max_items
        self._data: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Future] = {}

    def get(self, key: Hashable, default: Any = None) -> Any:
        item = self._data.get(key)
        if item is None:
            return default
        expires, value = item
        if expires < time.monotonic():
            self._data.pop(key, None)
            return default
        self._data.move_to_end(key)
        return value

    def set(self, key: Hashable, value: Any, ttl_s: float | None = None) -> None:
        self._data[key] = (time.monotonic() + (ttl_s or self.ttl), value)
        self._data.move_to_end(key)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)

    async def get_or_fetch(self, key: Hashable, fetch: Callable[[], Awaitable[Any]]) -> Any:
        """Return cached value or run fetch() once even when called concurrently."""
        value = self.get(key, _MISSING)
        if value is not _MISSING:
            return value
        fut = self._inflight.get(key)
        if fut is not None:
            return await asyncio.shield(fut)
        fut = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            value = await fetch()
            self.set(key, value)
            fut.set_result(value)
            return value
        except BaseException as e:
            fut.set_exception(e)
            fut.exception()  # mark retrieved
            raise
        finally:
            self._inflight.pop(key, None)

    def __len__(self) -> int:
        return len(self._data)
