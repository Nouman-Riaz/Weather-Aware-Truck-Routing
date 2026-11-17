import * as maplibregl from 'maplibre-gl'
import type { ExpressionSpecification, GeoJSONSource, MapLayerMouseEvent } from 'maplibre-gl'
// MapLibre 6 resolves its worker with a runtime URL that bundlers can't see, so let Vite bundle the
// worker (with its shared chunk) and hand MapLibre the emitted URL.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { memo, useEffect, useRef, useState } from 'react'
import { formatDuration } from '../lib/format'
import { LAYER_SCALE, LEVEL_COLOR, LEVEL_LABEL } from '../lib/risk'
import type { HeatmapLayer, HeatmapResponse, PlanResponse } from '../types'
import {
  checkpointFeatureId,
  checkpointPoints,
  HEATMAP_PREFIX,
  heatmapPoints,
  pointAlong,
  riskLines,
  routeLines,
  stopPoints,
  truckPosition,
} from './geometry'
import { checkpointPopup, stopPopup } from './popup'

maplibregl.setWorkerUrl(workerUrl)

const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'
const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
const HEATMAP_MAX_HOUR = 48

export interface FocusedCheckpoint {
  routeId: string
  index: number
}

interface Props {
  plan: PlanResponse | null
  selectedRouteId: string | null
  onSelectRoute: (id: string) => void
  focused: FocusedCheckpoint | null
  heatmap: HeatmapResponse | null
  heatmapLayer: HeatmapLayer
  showHeatmap: boolean
  /** Forecast hour offset from the first heatmap hour; fractional values blend adjacent hours. */
  hour: number
}

/** Heatmap weight for a fractional hour: blend the two neighbouring hourly values, each mapped onto
 *  0..1 using the layer's risk thresholds (so colours line up with the risk legend). */
function heatmapWeight(layer: HeatmapLayer, hour: number): ExpressionSpecification {
  const h0 = Math.min(Math.floor(hour), HEATMAP_MAX_HOUR)
  const h1 = Math.min(h0 + 1, HEATMAP_MAX_HOUR)
  const t = hour - h0
  const [s1, s2, s3, s4] = LAYER_SCALE[layer].stops
  const scaled = (h: number): ExpressionSpecification => [
    'interpolate',
    ['linear'],
    ['coalesce', ['get', `${HEATMAP_PREFIX[layer]}${h}`], -1],
    -1, 0,
    0, 0.08,
    s1, 0.25,
    s2, 0.5,
    s3, 0.75,
    s4, 1,
  ]
  return ['+', ['*', 1 - t, scaled(h0)], ['*', t, scaled(h1)]]
}

/** Kernel radius tied to the grid spacing so neighbouring points blend into a continuous surface. */
function heatmapRadius(data: HeatmapResponse): ExpressionSpecification {
  const midLat = data.points.reduce((s, p) => s + p[1], 0) / Math.max(data.points.length, 1)
  const spacingPxAtZoom0 = ((data.spacing_deg / Math.cos((midLat * Math.PI) / 180)) * 256) / 360
  const r0 = spacingPxAtZoom0 * 3
  return ['interpolate', ['exponential', 2], ['zoom'], 0, r0, 10, r0 * 1024]
}

const HEATMAP_COLOR: ExpressionSpecification = [
  'interpolate',
  ['linear'],
  ['heatmap-density'],
  0, 'rgba(0,0,0,0)',
  0.015, 'rgba(34,160,107,0)',
  0.04, 'rgba(34,160,107,0.2)',
  0.2, 'rgba(34,160,107,0.3)',
  0.25, 'rgba(226,178,3,0.5)',
  0.5, 'rgba(245,129,31,0.6)',
  0.75, 'rgba(226,51,74,0.68)',
  1, 'rgba(123,44,191,0.75)',
]

function routeLabelHtml(id: string, duration: string, level: string, color: string, recommended: boolean) {
  return `<span class="route-dot route-${id}">${id}</span><span>${duration}</span><span class="label-level" style="--chip:${color}">${level}</span>${recommended ? '<span class="label-star" title="Recommended">★</span>' : ''}`
}

function MapView({ plan, selectedRouteId, onSelectRoute, focused, heatmap, heatmapLayer, showHeatmap, hour }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)
  const markersRef = useRef<maplibregl.Marker[]>([])
  const trucksRef = useRef<Map<string, maplibregl.Marker>>(new Map())
  const popupRef = useRef<maplibregl.Popup | null>(null)
  const hoveredRef = useRef<number | null>(null)
  // Latest props for map event handlers registered once.
  const latest = useRef({ plan, onSelectRoute })
  latest.current = { plan, onSelectRoute }

  // --- Map initialisation (once) --------------------------------------------------------------
  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current!,
      style: STYLE_URL,
      center: [-98.5, 39.5],
      zoom: 3.6,
      attributionControl: { compact: true },
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-right')
    popupRef.current = new maplibregl.Popup({ closeButton: true, maxWidth: '280px', offset: 10 })

    map.on('load', () => {
      const firstSymbol = map.getStyle().layers.find((l) => l.type === 'symbol')?.id
      for (const id of ['heatmap', 'routes', 'risk', 'checkpoints', 'stops']) map.addSource(id, { type: 'geojson', data: EMPTY })

      // Heatmap sits under the base map's labels so place names stay readable.
      map.addLayer(
        {
          id: 'heatmap',
          type: 'heatmap',
          source: 'heatmap',
          paint: {
            'heatmap-weight': 0,
            // Summed kernels over a grid with radius = 3x spacing give ~7.5x the weight; normalise back to ~1x.
            'heatmap-intensity': 0.14,
            'heatmap-color': HEATMAP_COLOR,
            'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.9, 10, 0],
          },
        },
        firstSymbol,
      )
      map.addLayer({
        id: 'routes-casing',
        type: 'line',
        source: 'routes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 },
      })
      map.addLayer({
        id: 'routes-base',
        type: 'line',
        source: 'routes',
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#7b8794', 'line-width': 4, 'line-opacity': 0.75 },
      })
      map.addLayer({
        id: 'risk-casing',
        type: 'line',
        source: 'risk',
        filter: ['==', ['get', 'id'], ''],
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': '#0f172a', 'line-width': 9, 'line-opacity': 0.85 },
      })
      map.addLayer({
        id: 'risk-line',
        type: 'line',
        source: 'risk',
        filter: ['==', ['get', 'id'], ''],
        layout: { 'line-join': 'round', 'line-cap': 'round' },
        paint: { 'line-color': ['get', 'color'], 'line-width': 6 },
      })
      map.addLayer({
        id: 'routes-hit',
        type: 'line',
        source: 'routes',
        paint: { 'line-color': '#000', 'line-width': 18, 'line-opacity': 0 },
      })
      map.addLayer({
        id: 'checkpoints',
        type: 'circle',
        source: 'checkpoints',
        paint: {
          'circle-color': ['get', 'color'],
          'circle-stroke-color': '#ffffff',
          'circle-radius': ['case', ['boolean', ['feature-state', 'hover'], false], 9, 4],
          'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hover'], false], 3, 1.5],
          'circle-opacity': 0.9,
        },
      })
      map.addLayer({
        id: 'stops',
        type: 'circle',
        source: 'stops',
        filter: ['==', ['get', 'routeId'], ''],
        paint: {
          'circle-color': ['match', ['get', 'kind'], 'rest', '#1e293b', '#64748b'],
          'circle-radius': ['match', ['get', 'kind'], 'rest', 7, 5],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 2,
        },
      })

      map.on('click', 'routes-hit', (e) => {
        // Checkpoints and stops have their own handlers.
        if (map.queryRenderedFeatures(e.point, { layers: ['checkpoints', 'stops'] }).length) return
        const id = e.features?.[0]?.properties?.id
        if (id) latest.current.onSelectRoute(id)
      })
      map.on('click', 'checkpoints', (e: MapLayerMouseEvent) => {
        const props = e.features?.[0]?.properties
        const route = latest.current.plan?.routes.find((r) => r.id === props?.routeId)
        if (!route || props == null) return
        const cp = route.checkpoints[props.index]
        latest.current.onSelectRoute(route.id)
        popupRef.current!.setLngLat(cp.coord).setHTML(checkpointPopup(route, cp)).addTo(map)
      })
      map.on('click', 'stops', (e: MapLayerMouseEvent) => {
        const props = e.features?.[0]?.properties
        const route = latest.current.plan?.routes.find((r) => r.id === props?.routeId)
        if (!route || props == null) return
        const stop = route.stops[props.index]
        popupRef.current!.setLngLat(stop.coord).setHTML(stopPopup(route, stop)).addTo(map)
      })
      for (const layer of ['routes-hit', 'checkpoints', 'stops']) {
        map.on('mouseenter', layer, () => (map.getCanvas().style.cursor = 'pointer'))
        map.on('mouseleave', layer, () => (map.getCanvas().style.cursor = ''))
      }
      map.on('mousemove', 'checkpoints', (e) => {
        const id = e.features?.[0]?.id as number | undefined
        if (id === hoveredRef.current) return
        if (hoveredRef.current !== null) map.setFeatureState({ source: 'checkpoints', id: hoveredRef.current }, { hover: false })
        hoveredRef.current = id ?? null
        if (id !== undefined) map.setFeatureState({ source: 'checkpoints', id }, { hover: true })
      })
      map.on('mouseleave', 'checkpoints', () => {
        if (hoveredRef.current !== null) map.setFeatureState({ source: 'checkpoints', id: hoveredRef.current }, { hover: false })
        hoveredRef.current = null
      })
      setReady(true)
    })

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // --- Plan: routes, checkpoints, labels, endpoints -------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const source = (id: string) => map.getSource(id) as GeoJSONSource
    markersRef.current.forEach((m) => m.remove())
    markersRef.current = []
    trucksRef.current.forEach((m) => m.remove())
    trucksRef.current.clear()
    popupRef.current?.remove()

    if (!plan) {
      for (const id of ['routes', 'risk', 'checkpoints', 'stops']) source(id).setData(EMPTY)
      return
    }
    source('routes').setData(routeLines(plan))
    source('risk').setData(riskLines(plan))
    source('checkpoints').setData(checkpointPoints(plan))
    source('stops').setData(stopPoints(plan))

    const addMarker = (el: HTMLElement, lngLat: [number, number], anchor: maplibregl.PositionAnchor = 'center') => {
      const marker = new maplibregl.Marker({ element: el, anchor }).setLngLat(lngLat).addTo(map)
      markersRef.current.push(marker)
      return marker
    }
    for (const [place, kind] of [
      [plan.origin, 'origin'],
      [plan.destination, 'destination'],
    ] as const) {
      const el = document.createElement('div')
      el.className = `endpoint endpoint-${kind}`
      el.title = place.label
      addMarker(el, [place.lon, place.lat])
    }

    // Route summary labels, staggered along each route so they don't stack on shared stretches.
    plan.routes.forEach((route, i) => {
      const el = document.createElement('button')
      el.className = 'route-label'
      el.dataset.route = route.id
      const level = route.metrics.max_level
      el.innerHTML = routeLabelHtml(
        route.id,
        formatDuration(route.total_s),
        level ? LEVEL_LABEL[level] : '—',
        level ? LEVEL_COLOR[level] : '#9aa4b2',
        route.id === plan.recommendation.route_id,
      )
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        latest.current.onSelectRoute(route.id)
      })
      addMarker(el, pointAlong(route.geometry, 0.3 + 0.2 * i), 'bottom')

      const truck = document.createElement('div')
      truck.className = `truck route-${route.id}`
      truck.textContent = route.id
      trucksRef.current.set(route.id, new maplibregl.Marker({ element: truck }).setLngLat(route.geometry[0]).addTo(map))
    })

    const bounds = new maplibregl.LngLatBounds()
    plan.routes.forEach((r) => r.geometry.forEach((c) => bounds.extend(c)))
    const narrow = window.matchMedia('(max-width: 900px)').matches
    map.fitBounds(bounds, { padding: narrow ? 40 : { top: 60, bottom: 140, left: 60, right: 60 }, duration: 900 })
  }, [plan, ready])

  // --- Selected route ---------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const id = selectedRouteId ?? ''
    map.setFilter('risk-line', ['==', ['get', 'id'], id])
    map.setFilter('risk-casing', ['==', ['get', 'id'], id])
    map.setFilter('stops', ['==', ['get', 'routeId'], id])
    map.setPaintProperty('checkpoints', 'circle-opacity', ['case', ['==', ['get', 'routeId'], id], 1, 0.55])
    map.setPaintProperty('checkpoints', 'circle-stroke-opacity', ['case', ['==', ['get', 'routeId'], id], 1, 0.4])
    // Draw the selected route's checkpoints above the others.
    map.setLayoutProperty('checkpoints', 'circle-sort-key', ['case', ['==', ['get', 'routeId'], id], 1, 0])
    markersRef.current.forEach((m) => {
      const el = m.getElement()
      if (el.dataset.route) el.classList.toggle('selected', el.dataset.route === id)
    })
    trucksRef.current.forEach((m, routeId) => m.getElement().classList.toggle('selected', routeId === id))
  }, [selectedRouteId, ready, plan])

  // --- Focused checkpoint (from the sidebar) ----------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !plan || !focused) return
    const route = plan.routes.find((r) => r.id === focused.routeId)
    const cp = route?.checkpoints[focused.index]
    if (!route || !cp) return
    const id = checkpointFeatureId(route.id, focused.index)
    map.setFeatureState({ source: 'checkpoints', id }, { hover: true })
    popupRef.current!.setLngLat(cp.coord).setHTML(checkpointPopup(route, cp)).addTo(map)
    if (!map.getBounds().contains(cp.coord)) map.easeTo({ center: cp.coord, duration: 500 })
    return () => {
      map.setFeatureState({ source: 'checkpoints', id }, { hover: false })
    }
  }, [focused, plan, ready])

  // --- Heatmap data -----------------------------------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    ;(map.getSource('heatmap') as GeoJSONSource).setData(heatmap ? heatmapPoints(heatmap) : EMPTY)
    if (heatmap) map.setPaintProperty('heatmap', 'heatmap-radius', heatmapRadius(heatmap))
  }, [heatmap, ready])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setLayoutProperty('heatmap', 'visibility', showHeatmap ? 'visible' : 'none')
  }, [showHeatmap, ready])

  // --- Forecast hour: heatmap weights + truck positions (runs on every slider frame) -------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setPaintProperty('heatmap', 'heatmap-weight', heatmapWeight(heatmapLayer, hour))
    if (!plan) return
    const start = heatmap ? new Date(heatmap.hours[0]).getTime() : new Date(plan.departure).getTime()
    const elapsedS = (start + hour * 3_600_000 - new Date(plan.departure).getTime()) / 1000
    for (const route of plan.routes) trucksRef.current.get(route.id)?.setLngLat(truckPosition(route, elapsedS))
  }, [hour, heatmapLayer, heatmap, plan, ready])

  return <div ref={containerRef} className="map" />
}

export default memo(MapView)
