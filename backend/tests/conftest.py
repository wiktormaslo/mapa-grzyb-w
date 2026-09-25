import httpx
import pytest

from app import config
from app.prediction import service
from app.sources import gbif, http, open_meteo, soilgrids
from tests.mock_sources import MockState, make_transport


@pytest.fixture
def mock_sources(monkeypatch):
    state = MockState()
    monkeypatch.setattr(config, "DISABLE_GBIF", True)
    monkeypatch.setattr(config, "CACHE_DIR", "/nonexistent-cache-dir")
    http.set_client(httpx.AsyncClient(transport=make_transport(state)))
    for c in (service._forest_cache, service._response_cache, open_meteo._cache, soilgrids._cache):
        c._data.clear()
    service._tile_sem = None
    open_meteo._variant_idx = 0
    gbif.reset()
    yield state
    http.set_client(None)
