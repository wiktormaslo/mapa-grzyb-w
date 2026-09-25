"""Opieńka miodowa. Parasite/saprotroph on wood of many trees (stumps, older stands);
late season, likes cool moist weather after rain."""
from app.species.base import SpeciesConfig

CONFIG = SpeciesConfig(
    id="armillaria_mellea",
    name_pl="Opieńka miodowa",
    name_short="Opieńka",
    latin="Armillaria mellea",
    gbif_names=["Armillaria mellea", "Armillaria ostoyae", "Armillaria gallica"],
    host_trees={
        "Quercus": 1.0, "Fagus": 0.95, "Picea": 0.9, "Pinus": 0.8, "Carpinus": 0.9,
        "Betula": 0.8, "Alnus": 0.7, "Acer": 0.8, "Fraxinus": 0.8, "Abies": 0.8,
        "Populus": 0.7, "Tilia": 0.7, "Larix": 0.6,
    },
    unknown_companion_host=0.6,
    site_fertility={"B": 0.6, "BM": 0.85, "LM": 1.0, "L": 1.0, "OL": 0.4, "LL": 0.6},
    site_moisture={"S": 0.5, "SW": 1.0, "W": 0.9, "B": 0.4},
    mountain_factor=1.0,
    ph_pref=(3.5, 4.5, 7.0, 8.2),
    sand_pref=(5, 20, 90, 100),
    stand_age_pref=(15, 40, 200, 300),
    elevation_pref=(-50, 0, 1000, 1500),
    season=(232, 258, 298, 330),
    rain_lag=(7, 3, 8),
    rain_response=[(0, 0), (0.5, 0.05), (1.5, 0.5), (2.5, 0.9), (3.5, 1.0), (12, 1.0), (20, 0.8)],
    temperature_pref=[(2, 0), (6, 0.5), (9, 1), (15, 1), (19, 0.4), (24, 0)],
    soil_temperature_pref=[(2, 0), (6, 0.5), (8, 1), (14, 1), (18, 0.4), (23, 0)],
    soil_moisture_pref=[(0.05, 0), (0.11, 0.3), (0.19, 1), (0.42, 1), (0.52, 0.6)],
    humidity_pref=[(50, 0), (65, 0.4), (80, 1), (100, 1)],
    vpd_pref=[(0, 1), (0.6, 1), (1.3, 0.5), (2.2, 0.1), (4, 0)],
    water_balance_pref=[(-60, 0), (-30, 0.3), (0, 0.8), (15, 1)],
    drought_max_penalty=0.5,
    heat_max_penalty=0.6,
    frost_max_penalty=0.7,
    heat_tmax=(22, 28),
    frost_tmin=-3.0,
)
