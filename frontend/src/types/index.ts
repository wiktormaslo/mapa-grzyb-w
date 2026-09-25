export interface SpeciesInfo {
  id: string;
  name_pl: string;
  name_short: string;
  latin: string;
}

export interface SpeciesResponse {
  species: SpeciesInfo[];
  today: string;
  forecast_days: number;
}

export interface CellProps {
  score: number;
  confidence: number;
  species: string;
  scores?: Record<string, number>;
}

export interface WeatherRequest {
  url: string;
  params: Record<string, string | number>;
}

export interface WeatherGap {
  weather_missing?: [number, number][];
  weather_request?: WeatherRequest;
}

export interface BboxMeta extends WeatherGap {
  species: string;
  date: string;
  resolution_m: number | null;
  cells: number;
  errors: string[];
  weather_source?: "open-meteo" | "grid" | "partial";
}

export interface CellFeature {
  type: "Feature";
  properties: CellProps;
  geometry: { type: "Polygon"; coordinates: number[][][] };
}

export interface BboxResponse {
  type: "FeatureCollection";
  features: CellFeature[];
  meta: BboxMeta;
}

export interface PointPrediction {
  species: string;
  name_pl: string;
  latin: string;
  date: string;
  score: number;
  confidence: number;
  components: Record<string, number | null | Record<string, number | null>>;
  positive_factors: string[];
  negative_factors: string[];
  missing_data: string[];
  features: Record<string, number | string | null>;
}

export interface PointResponse extends WeatherGap {
  lat: number;
  lon: number;
  date: string;
  in_forest: boolean;
  errors: string[];
  sources: string[];
  forest?: {
    trees: { genus: string; name_pl: string; share: number | null }[];
    species_codes: string[];
    site_type: string | null;
    site_type_label: string | null;
    stand_age: number | null;
    address: string | null;
  };
  results: PointPrediction[];
}
