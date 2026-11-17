import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, fetchHeatmap, planTrip } from './api'
import CheckpointList from './components/CheckpointList'
import PlanForm from './components/PlanForm'
import RouteCard from './components/RouteCard'
import TimeSlider from './components/TimeSlider'
import MapView, { type FocusedCheckpoint } from './map/MapView'
import type { HeatmapLayer, HeatmapResponse, PlanRequest, PlanResponse } from './types'

const message = (err: unknown) => (err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [planning, setPlanning] = useState(false)
  const [planError, setPlanError] = useState<string | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState<string | null>(null)
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null)

  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null)
  const [heatmapLoading, setHeatmapLoading] = useState(false)
  const [heatmapError, setHeatmapError] = useState<string | null>(null)
  const [heatmapLayer, setHeatmapLayer] = useState<HeatmapLayer>('risk')
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const heatmapAbort = useRef<AbortController | null>(null)

  const submit = useCallback(async (request: PlanRequest) => {
    setPlanning(true)
    setPlanError(null)
    try {
      const result = await planTrip(request)
      setPlan(result)
      setSelectedRouteId(result.recommendation.route_id)
      setFocusedIndex(null)
      setHour(0)
      setPlaying(false)
    } catch (err) {
      setPlanError(message(err))
    } finally {
      setPlanning(false)
    }
  }, [])

  // Load the corridor heatmap once routes are known; routes render immediately without waiting for it.
  useEffect(() => {
    heatmapAbort.current?.abort()
    setHeatmap(null)
    setHeatmapError(null)
    if (!plan) return
    const controller = new AbortController()
    heatmapAbort.current = controller
    setHeatmapLoading(true)
    fetchHeatmap(
      plan.routes.map((r) => r.geometry),
      plan.departure,
      plan.load_lb,
      controller.signal,
    )
      .then(setHeatmap)
      .catch((err) => {
        if (!controller.signal.aborted) setHeatmapError(message(err))
      })
      .finally(() => {
        if (!controller.signal.aborted) setHeatmapLoading(false)
      })
    return () => controller.abort()
  }, [plan])

  const selectRoute = useCallback((id: string) => {
    setSelectedRouteId(id)
    setFocusedIndex(null)
  }, [])

  const selectedRoute = plan?.routes.find((r) => r.id === selectedRouteId) ?? null
  // Memoised so slider frames (which re-render App) don't re-trigger the map's focus effect.
  const focused = useMemo<FocusedCheckpoint | null>(
    () => (selectedRouteId && focusedIndex !== null ? { routeId: selectedRouteId, index: focusedIndex } : null),
    [selectedRouteId, focusedIndex],
  )
  const recommendation = plan?.recommendation

  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <img src="/truck.svg" alt="" width={28} height={28} />
          <div>
            <h1>Weather-Aware Truck Routing</h1>
            <p className="muted">Safest route by forecast weather, load and time</p>
          </div>
        </header>

        <PlanForm loading={planning} onSubmit={submit} />

        {planError && (
          <div className="alert error" role="alert">
            {planError}
          </div>
        )}

        {plan && recommendation && (
          <>
            <section className="recommendation" aria-live="polite">
              <h2>
                Take <span className={`route-dot route-${recommendation.route_id}`}>{recommendation.route_id}</span> Route {recommendation.route_id}
              </h2>
              <ul>
                {recommendation.reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
              {recommendation.warnings.map((w) => (
                <div key={w} className="alert warning">
                  {w}
                </div>
              ))}
            </section>

            <section className="routes" aria-label="Route options">
              {[...plan.routes]
                .sort((a, b) => a.rank - b.rank)
                .map((route) => (
                  <RouteCard
                    key={route.id}
                    route={route}
                    recommended={route.id === recommendation.route_id}
                    selected={route.id === selectedRouteId}
                    onSelect={selectRoute}
                  />
                ))}
            </section>

            {selectedRoute && <CheckpointList route={selectedRoute} focusedIndex={focusedIndex} onFocus={setFocusedIndex} />}

            <p className="footnote muted">
              Weather is sampled every {plan.interval_mi} mi at the truck's ETA. Risk uses sustained wind, rain and snow rates with
              load rules for {plan.load_lb.toLocaleString()} lb. Ranking: fewest No Travel → Severe → High miles → lowest average
              risk → shortest time.
            </p>
          </>
        )}
      </aside>

      <main className="map-wrap">
        <MapView
          plan={plan}
          selectedRouteId={selectedRouteId}
          onSelectRoute={selectRoute}
          focused={focused}
          heatmap={heatmap}
          heatmapLayer={heatmapLayer}
          showHeatmap={showHeatmap}
          hour={hour}
        />
        {plan && (
          <TimeSlider
            heatmap={heatmap}
            loading={heatmapLoading}
            error={heatmapError}
            hour={hour}
            onHour={setHour}
            layer={heatmapLayer}
            onLayer={setHeatmapLayer}
            visible={showHeatmap}
            onVisible={setShowHeatmap}
            playing={playing}
            onPlaying={setPlaying}
          />
        )}
      </main>
    </div>
  )
}
