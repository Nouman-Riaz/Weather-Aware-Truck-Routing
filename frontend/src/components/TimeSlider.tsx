import { useEffect, useRef } from 'react'
import { formatDateTime } from '../lib/format'
import { LAYER_SCALE, LEVEL_COLOR } from '../lib/risk'
import type { HeatmapLayer, HeatmapResponse } from '../types'

const MAX_HOUR = 48
const PLAY_HOURS_PER_SECOND = 3

interface Props {
  heatmap: HeatmapResponse | null
  loading: boolean
  error: string | null
  hour: number
  onHour: (hour: number) => void
  layer: HeatmapLayer
  onLayer: (layer: HeatmapLayer) => void
  visible: boolean
  onVisible: (visible: boolean) => void
  playing: boolean
  onPlaying: (playing: boolean) => void
}

function Legend({ layer }: { layer: HeatmapLayer }) {
  const scale = LAYER_SCALE[layer]
  const colors = [LEVEL_COLOR.low, LEVEL_COLOR.moderate, LEVEL_COLOR.high, LEVEL_COLOR.severe, LEVEL_COLOR.no_travel]
  const ticks = layer === 'risk' ? ['Low', 'Mod', 'High', 'Sev', 'No travel'] : ['0', ...scale.stops.map(String)]
  return (
    <div className="legend">
      <div className="legend-ramp" style={{ background: `linear-gradient(90deg, ${colors.join(', ')})` }} />
      <div className="legend-ticks">
        {ticks.map((t) => (
          <span key={t}>{t}</span>
        ))}
      </div>
      {scale.unit && <div className="legend-unit">{scale.unit}</div>}
    </div>
  )
}

export default function TimeSlider(props: Props) {
  const { heatmap, loading, error, hour, onHour, layer, onLayer, visible, onVisible, playing, onPlaying } = props
  const hourRef = useRef(hour)
  hourRef.current = hour

  // Animate with requestAnimationFrame; fractional hours blend smoothly between forecast hours.
  useEffect(() => {
    if (!playing) return
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      const next = hourRef.current + ((now - last) / 1000) * PLAY_HOURS_PER_SECOND
      last = now
      if (next >= MAX_HOUR) {
        onHour(MAX_HOUR)
        onPlaying(false)
        return
      }
      onHour(next)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, onHour, onPlaying])

  const current = heatmap ? new Date(new Date(heatmap.hours[0]).getTime() + hour * 3_600_000) : null

  return (
    <div className="time-slider" aria-label="Forecast timeline">
      <div className="slider-top">
        <button
          type="button"
          className="play"
          disabled={!heatmap}
          onClick={() => {
            if (!playing && hour >= MAX_HOUR) onHour(0)
            onPlaying(!playing)
          }}
          aria-label={playing ? 'Pause' : 'Play forecast'}
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <div className="slider-time">
          <strong>+{Math.floor(hour)}h</strong>
          <span className="muted">
            {loading ? 'Loading corridor forecast…' : error ? error : current ? formatDateTime(current) : 'Plan a trip to see the forecast'}
          </span>
        </div>
        <div className="layer-select" role="radiogroup" aria-label="Heatmap layer">
          {(Object.keys(LAYER_SCALE) as HeatmapLayer[]).map((key) => (
            <button type="button" key={key} role="radio" aria-checked={layer === key} className={layer === key ? 'on' : undefined} onClick={() => onLayer(key)}>
              {LAYER_SCALE[key].label.replace('Overall ', '')}
            </button>
          ))}
        </div>
        <label className="toggle compact">
          <input type="checkbox" checked={visible} onChange={(e) => onVisible(e.target.checked)} />
          <span>Heatmap</span>
        </label>
      </div>
      <input
        type="range"
        min={0}
        max={MAX_HOUR}
        step={0.1}
        value={hour}
        disabled={!heatmap}
        onChange={(e) => {
          onPlaying(false)
          onHour(Number(e.target.value))
        }}
        aria-label="Forecast hour after departure"
      />
      <div className="slider-ticks muted">
        {[0, 12, 24, 36, 48].map((h) => (
          <span key={h}>{h}h</span>
        ))}
      </div>
      <Legend layer={layer} />
    </div>
  )
}
