import { memo } from 'react'
import { formatDuration, formatMiles, formatTime } from '../lib/format'
import { LEVEL_COLOR, LEVEL_LABEL, LEVELS, levelColor, UNKNOWN_COLOR } from '../lib/risk'
import type { RouteOption } from '../types'

interface Props {
  route: RouteOption
  recommended: boolean
  selected: boolean
  onSelect: (id: string) => void
}

/** Stacked bar of miles per risk level. */
function RiskBar({ route }: { route: RouteOption }) {
  const { miles_by_level: miles, unknown_miles: unknown } = route.metrics
  const total = route.distance_mi || 1
  return (
    <div className="risk-bar" role="img" aria-label="Miles by risk level">
      {LEVELS.map((level) =>
        miles[level] > 0 ? (
          <span
            key={level}
            style={{ width: `${(miles[level] / total) * 100}%`, background: LEVEL_COLOR[level] }}
            title={`${LEVEL_LABEL[level]}: ${formatMiles(miles[level])}`}
          />
        ) : null,
      )}
      {unknown > 0 && <span style={{ width: `${(unknown / total) * 100}%`, background: UNKNOWN_COLOR }} title={`No forecast: ${formatMiles(unknown)}`} />}
    </div>
  )
}

function RouteCard({ route, recommended, selected, onSelect }: Props) {
  const m = route.metrics
  const stopTime = route.total_s - route.drive_s
  const hazards = (['no_travel', 'severe', 'high'] as const).filter((level) => m.miles_by_level[level] > 0)
  return (
    <button
      type="button"
      className={`route-card${selected ? ' selected' : ''}${recommended ? ' recommended' : ''}`}
      onClick={() => onSelect(route.id)}
      aria-pressed={selected}
    >
      <div className="route-card-head">
        <span className={`route-dot route-${route.id}`}>{route.id}</span>
        <div className="route-title">
          <strong>{route.name}</strong>
          <span className="muted" title={route.summary}>
            via {route.summary || 'local roads'}
          </span>
        </div>
        {recommended ? <span className="badge">★ Recommended</span> : <span className="rank">#{route.rank}</span>}
      </div>

      <dl className="route-stats">
        <div>
          <dt>Distance</dt>
          <dd>{formatMiles(route.distance_mi)}</dd>
        </div>
        <div>
          <dt>Trip time</dt>
          <dd title={stopTime > 0 ? `${formatDuration(route.drive_s)} driving + ${formatDuration(stopTime)} HOS stops` : undefined}>
            {formatDuration(route.total_s)}
          </dd>
        </div>
        <div>
          <dt>Arrive</dt>
          <dd>{formatTime(route.arrival)}</dd>
        </div>
        <div>
          <dt>Peak risk</dt>
          <dd>
            <span className="chip" style={{ '--chip': levelColor(m.max_level) } as React.CSSProperties}>
              {m.max_level ? LEVEL_LABEL[m.max_level] : 'Unknown'}
            </span>
          </dd>
        </div>
      </dl>

      <RiskBar route={route} />
      <div className="route-foot muted">
        {hazards.length
          ? hazards.map((level) => `${formatMiles(m.miles_by_level[level])} ${LEVEL_LABEL[level]}`).join(' · ')
          : 'No High or Severe miles'}
        <span> · avg risk {m.avg_risk.toFixed(2)}</span>
      </div>
    </button>
  )
}

export default memo(RouteCard)
