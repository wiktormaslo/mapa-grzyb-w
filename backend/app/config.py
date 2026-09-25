"""Runtime settings (env overrides). Endpoints were chosen from current public docs;
they are configurable so a moved endpoint can be fixed without code changes."""
import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


BDL_LAYER_URL = _env(
    "BDL_LAYER_URL",
    "https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services/WMS_BDL/MapServer/5",
)
# forests outside State Forests (private, municipal...) from simplified management plans (PUL);
# same attributes as layer 5. "" disables.
BDL_OTHER_LAYER_URL = _env(
    "BDL_OTHER_LAYER_URL",
    "https://mapserver.bdl.lasy.gov.pl/arcgis/rest/services/WMS_BDL/MapServer/6",
)
OPEN_METEO_URL = _env("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
GBIF_URL = _env("GBIF_URL", "https://api.gbif.org/v1/occurrence/search")
SOILGRIDS_URL = _env("SOILGRIDS_URL", "https://rest.isric.org/soilgrids/v2.0/properties/query")

# fallback weather grid refreshed by GitHub Actions (branch weather-data); "" disables it
WEATHER_GRID_URL = _env(
    "WEATHER_GRID_URL",
    "https://raw.githubusercontent.com/wiktormaslo/mapa-grzyb-w/weather-data/weather_grid.json.gz",
)

HTTP_TIMEOUT_S = float(_env("HTTP_TIMEOUT_S", "25"))
DEBUG = _env("DEBUG", "0") == "1"
DISABLE_GBIF = _env("DISABLE_GBIF", "0") == "1"
CACHE_DIR = _env("CACHE_DIR", "/tmp/mapa-grzybow-cache")
USER_AGENT = "mapa-grzybow/1.0 (personal non-commercial project)"
TIMEZONE = "Europe/Warsaw"
FORECAST_DAYS = 6          # today + 5
PAST_DAYS = 40             # >= 35 days of history for rain lag
