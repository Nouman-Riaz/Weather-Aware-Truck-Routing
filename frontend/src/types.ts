export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'
export type LngLat = [number, number]

export interface Place {
  label: string
  lat?: number
  lon?: number
}

export interface Weather {
  wind_mph: number
  gust_mph: number
  rain_in_hr: number
  snow_in_hr: number
  temp_f: number
  code: number
}

export interface Checkpoint {
  mile: number
  coord: LngLat
  eta: string
  coverage_mi: number
  level: RiskLevel | null
  factors: Record<'wind' | 'rain' | 'snow', RiskLevel> | null
  reasons: string[]
  weather: Weather | null
}

export interface Stop {
  kind: 'break' | 'rest'
  coord: LngLat
  start: string
  end: string
}

export interface RouteOption {
  id: string
  name: string
  summary: string
  is_alternative_via: boolean
  rank: number
  distance_mi: number
  drive_s: number
  total_s: number
  arrival: string
  metrics: {
    miles_by_level: Record<RiskLevel, number>
    unknown_miles: number
    avg_risk: number
    max_level: RiskLevel | null
  }
  geometry: LngLat[]
  checkpoints: Checkpoint[]
  stops: Stop[]
  progress: { step_s: number; coords: LngLat[] }
}

export interface PlanRequest {
  origin: Place
  destination: Place
  departure: string
  load_lb: number
  interval_mi: 10 | 25 | 50
  hos: boolean
}

export interface PlanResponse {
  origin: Required<Place>
  destination: Required<Place>
  departure: string
  load_lb: number
  interval_mi: number
  hos: boolean
  recommendation: {
    route_id: string
    ranking: string[]
    reasons: string[]
    warnings: string[]
  }
  routes: RouteOption[]
}

export type HeatmapLayer = 'risk' | 'wind_mph' | 'rain_in_hr' | 'snow_in_hr'

export interface HeatmapResponse {
  hours: string[]
  spacing_deg: number
  points: LngLat[]
  risk: (number | null)[][]
  wind_mph: (number | null)[][]
  rain_in_hr: (number | null)[][]
  snow_in_hr: (number | null)[][]
}
