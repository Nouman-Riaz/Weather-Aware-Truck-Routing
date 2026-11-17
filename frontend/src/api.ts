import type { HeatmapResponse, LngLat, Place, PlanRequest, PlanResponse } from './types'

export class ApiError extends Error {}

function describe(body: unknown): string {
  if (body && typeof body === 'object') {
    if ('detail' in body) return String((body as { detail: unknown }).detail)
    // DRF validation errors: { field: ["message"] } (possibly nested).
    return Object.entries(body)
      .map(([field, value]) => `${field.replace('_', ' ')}: ${Array.isArray(value) ? value.join(' ') : describe(value)}`)
      .join('; ')
  }
  return 'Unexpected error'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw new ApiError('Network error: could not reach the server.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(describe(body))
  return body as T
}

export function searchPlaces(query: string, signal?: AbortSignal): Promise<{ results: Required<Place>[] }> {
  return request(`geocode?q=${encodeURIComponent(query)}`, { signal })
}

export function planTrip(body: PlanRequest): Promise<PlanResponse> {
  return request('plan', { method: 'POST', body: JSON.stringify(body) })
}

export function fetchHeatmap(routes: LngLat[][], departure: string, loadLb: number, signal?: AbortSignal): Promise<HeatmapResponse> {
  return request('heatmap', {
    method: 'POST',
    body: JSON.stringify({ routes, departure, load_lb: loadLb }),
    signal,
  })
}
