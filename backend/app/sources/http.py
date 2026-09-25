"""Shared async HTTP client."""
from __future__ import annotations

import httpx

from app import config

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT_S,
            headers={"User-Agent": config.USER_AGENT},
            follow_redirects=True,
        )
    return _client


def set_client(client: httpx.AsyncClient | None) -> None:
    """Used by tests to inject a mocked transport."""
    global _client
    _client = client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class SourceError(Exception):
    def __init__(self, source: str, message: str):
        super().__init__(f"{source}: {message}")
        self.source = source
