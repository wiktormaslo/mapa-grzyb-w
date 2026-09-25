/** Human-readable texts for reason codes computed by the backend model. */
export const POSITIVE: Record<string, string> = {
  HOST_TREE_STRONG: "odpowiedni drzewostan (drzewa żywicielskie)",
  HABITAT_GOOD: "sprzyjający typ siedliska leśnego",
  SOIL_GOOD: "odpowiednia gleba",
  STAND_AGE_GOOD: "odpowiedni wiek drzewostanu",
  HISTORICAL_RECORDS_NEARBY: "historyczne obserwacje gatunku w okolicy (GBIF)",
  RAIN_LAG_FAVORABLE: "korzystne opady z ostatnich tygodni",
  SOIL_MOISTURE_GOOD: "dobra wilgotność gleby",
  TEMPERATURE_GOOD: "odpowiednia temperatura",
  SOIL_TEMPERATURE_GOOD: "odpowiednia temperatura gleby",
  HUMIDITY_GOOD: "wysoka wilgotność powietrza",
  IN_SEASON: "pełnia sezonu",
};

export const NEGATIVE: Record<string, string> = {
  HOST_MISSING: "brak właściwych drzew żywicielskich",
  HOST_WEAK: "mały udział drzew żywicielskich",
  HABITAT_POOR: "niekorzystny typ siedliska",
  SOIL_UNFAVORABLE: "niekorzystna gleba",
  STAND_AGE_UNFAVORABLE: "niekorzystny wiek drzewostanu",
  RAIN_LAG_LOW: "za mało opadów w ostatnich tygodniach",
  SOIL_DRY: "sucha gleba",
  TEMPERATURE_UNFAVORABLE: "niekorzystna temperatura",
  SOIL_TEMPERATURE_UNFAVORABLE: "niekorzystna temperatura gleby",
  VPD_HIGH: "suche powietrze (wysoki VPD) w ostatnich dniach",
  RECENT_DROUGHT: "susza w ostatnich tygodniach",
  HEAT: "upał",
  FROST: "przymrozki",
  OUTSIDE_SEASON: "poza sezonem",
  SEASON_EDGE: "początek lub koniec sezonu",
};

export const MISSING: Record<string, string> = {
  TREE_SPECIES_MISSING: "brak danych o gatunkach drzew",
  SITE_TYPE_MISSING: "brak typu siedliska",
  STAND_AGE_MISSING: "brak wieku drzewostanu",
  WEATHER_MISSING: "brak danych pogodowych",
  SOIL_MOISTURE_MISSING: "brak wilgotności gleby",
  SOILGRIDS_MISSING: "gleba oszacowana z typu siedliska (bez SoilGrids)",
  SOIL_MISSING: "brak danych o glebie",
  GBIF_MISSING: "brak danych historycznych GBIF",
};

export const text = (dict: Record<string, string>, code: string) => dict[code] ?? code;
