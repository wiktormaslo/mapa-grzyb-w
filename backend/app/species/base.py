"""Species configuration schema + global model settings.

Every tunable number of the model lives either in a species file or in MODEL below.
"""
from __future__ import annotations

from dataclasses import dataclass, field

Points = list[tuple[float, float]]


@dataclass(frozen=True)
class SpeciesConfig:
    id: str
    name_pl: str
    name_short: str
    latin: str
    gbif_names: list[str]

    # host genus -> importance 0..1 (genus names from app.species.trees)
    host_trees: dict[str, float]
    # value for part of stand with unknown composition
    unknown_companion_host: float

    # forest site type (typ siedliskowy lasu) preferences
    site_fertility: dict[str, float]  # B, BM, LM, L, OL, LL
    site_moisture: dict[str, float]   # S (suchy), SW (świeży), W (wilgotny), B (bagienny)
    mountain_factor: float            # multiplier for mountain (G) / upland (WYZ) variants

    # soil
    ph_pref: tuple[float, float, float, float]    # trapezoid a,b,c,d
    sand_pref: tuple[float, float, float, float]  # % sand trapezoid

    stand_age_pref: tuple[float, float, float, float]  # years trapezoid
    elevation_pref: tuple[float, float, float, float]  # m a.s.l. trapezoid

    # season: day-of-year curve
    season: tuple[float, float, float, float]  # rise_start, peak_start, peak_end, fall_end

    # weather response curves
    rain_lag: tuple[float, float, float]  # peak_day, width_before, width_after
    rain_response: Points                  # lag-weighted mean mm/day -> 0..1
    temperature_pref: Points               # 14d mean air temp C
    soil_temperature_pref: Points          # 7d mean soil temp C
    soil_moisture_pref: Points             # 14d mean m3/m3
    humidity_pref: Points                  # 7d mean RH %
    vpd_pref: Points                       # 7d mean of daily max VPD kPa
    water_balance_pref: Points             # 14d rain - ET0 (mm)

    # penalties (max multiplicative reduction)
    drought_max_penalty: float
    heat_max_penalty: float
    frost_max_penalty: float
    heat_tmax: tuple[float, float]   # mean daily tmax over 7d: no penalty .. full penalty
    frost_tmin: float                # daily tmin at/below counts as frost day

    habitat_weights: dict[str, float] | None = None  # override MODEL defaults
    weather_weights: dict[str, float] | None = None


@dataclass(frozen=True)
class ModelSettings:
    habitat_weights: dict[str, float] = field(default_factory=lambda: {
        "host": 0.35, "habitat": 0.20, "soil": 0.15,
        "stand": 0.15, "terrain": 0.05, "prior": 0.10,
    })
    # values used when a habitat component is UNKNOWN (not the same as "bad")
    unknown_component: dict[str, float] = field(default_factory=lambda: {
        "host": 0.5, "habitat": 0.5, "soil": 0.5,
        "stand": 0.6, "terrain": 0.8, "prior": 0.5,
    })
    weather_weights: dict[str, float] = field(default_factory=lambda: {
        "rainfall_lag": 0.30, "soil_moisture": 0.25, "temperature": 0.20,
        "soil_temperature": 0.10, "humidity_vpd": 0.10, "water_balance": 0.05,
    })
    weather_unknown: float = 0.5
    weather_floor: float = 0.30  # Base = H * (floor + (1-floor) * W) * S
    # water is a hard requirement for fruiting: W *= floor + (1-floor) * mean(rain_lag, soil_moisture),
    # so good temperature/humidity cannot compensate for missing rain
    water_trigger_floor: float = 0.4
    # final calibration score = 100 * adjusted^gamma: average-good conditions land ~40-65,
    # 85+ only when habitat, rain, moisture, temperature and season are all near optimum
    score_gamma: float = 2.2

    # limiting-factor gate: bad host or bad site caps habitat regardless of weather
    gate_floor: float = 0.25
    gate_threshold: float = 0.5

    # host composition
    default_dominant_share: float = 0.7
    host_saturation: float = 0.6  # weighted host share giving full host score

    # GBIF prior: 0.5 (no info / no records) .. prior_max (many records nearby); kept small because
    # presence-only data mostly reflects where people walk and report, and the final gamma amplifies it
    prior_scale_records: float = 3.0
    prior_max: float = 0.7
    historical_adjustment_max: float = 0.02

    # drought: evaluated on window ending `min_effect_lag` days before target
    min_effect_lag: int = 3
    drought_rain_30d: tuple[float, float] = (60.0, 15.0)   # mm: no drought .. full drought
    drought_dry_days: tuple[float, float] = (12.0, 30.0)   # days since >=10 mm

    # confidence weights (sum 100)
    confidence_weights: dict[str, float] = field(default_factory=lambda: {
        "tree_species": 25, "site_type": 12, "stand_age": 6, "species_share": 5,
        "weather_core": 25, "soil_moisture": 8, "humidity": 4,
        "soil": 8, "gbif": 5, "elevation": 2,
    })
    confidence_lead_day_penalty: float = 4.0
    confidence_coarse_weather_penalty: float = 12.0
    confidence_resolution_penalty: dict[int, float] = field(default_factory=lambda: {
        250: 0, 500: 0, 1000: 2, 2000: 5, 4000: 8, 8000: 12, 16000: 15, 32000: 18,
    })

    # reason thresholds
    good: float = 0.75
    bad: float = 0.3


MODEL = ModelSettings()
