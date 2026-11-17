import type { HeatmapLayer, RiskLevel } from '../types'

export const LEVELS: RiskLevel[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const LEVEL_LABEL: Record<RiskLevel, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
}

export const LEVEL_COLOR: Record<RiskLevel, string> = {
  low: '#22a06b',
  moderate: '#e2b203',
  high: '#f5811f',
  severe: '#e2334a',
  no_travel: '#7b2cbf',
}

export const UNKNOWN_COLOR = '#9aa4b2'

export function levelColor(level: RiskLevel | null): string {
  return level ? LEVEL_COLOR[level] : UNKNOWN_COLOR
}

/** Thresholds at which each heatmap layer reaches Moderate, High, Severe and No Travel. */
export const LAYER_SCALE: Record<HeatmapLayer, { label: string; unit: string; stops: [number, number, number, number] }> = {
  risk: { label: 'Overall risk', unit: '', stops: [1, 2, 3, 4] },
  wind_mph: { label: 'Wind', unit: 'mph', stops: [25, 35, 45, 55] },
  rain_in_hr: { label: 'Rain', unit: 'in/hr', stops: [0.1, 0.25, 0.5, 1] },
  snow_in_hr: { label: 'Snow', unit: 'in/hr', stops: [0.5, 1, 2, 3] },
}
