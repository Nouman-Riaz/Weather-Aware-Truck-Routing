import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { levelColor } from '../lib/risk'
import type { HeatmapLayer, HeatmapResponse, LngLat, PlanResponse, RouteOption } from '../types'

const EARTH_RADIUS_MI = 3958.8

export function haversineMi(a: LngLat, b: LngLat): number {
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b[1] - a[1])
  const dLon = toRad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h))
}

const lerp = (a: LngLat, b: LngLat, t: number): LngLat => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]

/** Point `fraction` (0..1) of the way along a line. */
export function pointAlong(line: LngLat[], fraction: number): LngLat {
  const lengths = line.slice(1).map((c, i) => haversineMi(line[i], c))
  let remaining = lengths.reduce((s, l) => s + l, 0) * fraction
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i]) return lerp(line[i], line[i + 1], lengths[i] ? remaining / lengths[i] : 0)
    remaining -= lengths[i]
  }
  return line[line.length - 1]
}

/**
 * Split a route line into runs coloured by the risk of the checkpoint covering them. Each checkpoint
 * covers the stretch halfway to its neighbours, matching how the backend counts miles per level.
 */
export function riskSegments(route: RouteOption): Feature<LineString>[] {
  const line = route.geometry
  const cps = route.checkpoints
  const rawLength = line.slice(1).reduce((sum, c, i) => sum + haversineMi(line[i], c), 0)
  // The display geometry is simplified, so rescale its length to the route's true mileage.
  const scale = rawLength > 0 ? route.distance_mi / rawLength : 1
  const bounds = cps.slice(0, -1).map((cp, i) => (cp.mile + cps[i + 1].mile) / 2)

  const features: Feature<LineString>[] = []
  let k = 0
  let current: LngLat[] = [line[0]]
  let mile = 0
  const flush = (end: LngLat) => {
    current.push(end)
    const color = levelColor(cps[k].level)
    const previous = features[features.length - 1]
    if (previous && previous.properties!.color === color) previous.geometry.coordinates.push(...current.slice(1))
    else features.push({ type: 'Feature', properties: { id: route.id, color }, geometry: { type: 'LineString', coordinates: current } })
  }

  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1]
    const b = line[i]
    const length = haversineMi(a, b) * scale
    while (k < bounds.length && mile + length >= bounds[k]) {
      const split = lerp(a, b, length ? (bounds[k] - mile) / length : 0)
      flush(split)
      current = [split]
      k++
    }
    current.push(b)
    mile += length
  }
  if (current.length > 1) flush(current.pop()!)
  return features
}

export function routeLines(plan: PlanResponse): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.map((r) => ({
      type: 'Feature',
      properties: { id: r.id },
      geometry: { type: 'LineString', coordinates: r.geometry },
    })),
  }
}

export function riskLines(plan: PlanResponse): FeatureCollection<LineString> {
  return { type: 'FeatureCollection', features: plan.routes.flatMap(riskSegments) }
}

export function checkpointPoints(plan: PlanResponse): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((r) =>
      r.checkpoints.map((cp, index) => ({
        type: 'Feature' as const,
        id: checkpointFeatureId(r.id, index),
        properties: { routeId: r.id, index, color: levelColor(cp.level) },
        geometry: { type: 'Point' as const, coordinates: cp.coord },
      })),
    ),
  }
}

/** Numeric feature id so checkpoints can use feature-state for hover highlighting. */
export const checkpointFeatureId = (routeId: string, index: number) => (routeId.charCodeAt(0) - 64) * 100_000 + index

export function stopPoints(plan: PlanResponse): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: plan.routes.flatMap((r) =>
      r.stops.map((s, index) => ({
        type: 'Feature' as const,
        properties: { routeId: r.id, index, kind: s.kind },
        geometry: { type: 'Point' as const, coordinates: s.coord },
      })),
    ),
  }
}

export const HEATMAP_PREFIX: Record<HeatmapLayer, string> = { risk: 'r', wind_mph: 'w', rain_in_hr: 'p', snow_in_hr: 's' }

/** One feature per grid point with scalar properties per hour (e.g. r0..r48), so the forecast hour can
 *  be changed with a paint-property update alone (no re-tiling) - this keeps the slider smooth. */
export function heatmapPoints(data: HeatmapResponse): FeatureCollection<Point> {
  const layers = Object.keys(HEATMAP_PREFIX) as HeatmapLayer[]
  return {
    type: 'FeatureCollection',
    features: data.points.map((coord, i) => {
      const properties: Record<string, number> = {}
      for (const layer of layers) {
        data[layer][i].forEach((value, hour) => {
          if (value !== null) properties[`${HEATMAP_PREFIX[layer]}${hour}`] = value
        })
      }
      return { type: 'Feature', properties, geometry: { type: 'Point', coordinates: coord } }
    }),
  }
}

/** Truck position `elapsedS` seconds after departure (stays at the destination after arrival). */
export function truckPosition(route: RouteOption, elapsedS: number): LngLat {
  const { step_s: step, coords } = route.progress
  const x = Math.max(0, elapsedS / step)
  const i = Math.floor(x)
  if (i >= coords.length - 1) return coords[coords.length - 1]
  return lerp(coords[i], coords[i + 1], x - i)
}
