import { memo } from 'react'
import { formatTime } from '../lib/format'
import { LEVEL_LABEL, levelColor } from '../lib/risk'
import type { RouteOption } from '../types'

interface Props {
  route: RouteOption
  focusedIndex: number | null
  onFocus: (index: number | null) => void
}

function CheckpointList({ route, focusedIndex, onFocus }: Props) {
  return (
    <section className="checkpoints" aria-label={`${route.name} checkpoints`}>
      <h3>
        {route.name} checkpoints <span className="muted">({route.checkpoints.length})</span>
      </h3>
      <table>
        <thead>
          <tr>
            <th>Mile</th>
            <th>ETA</th>
            <th>Risk</th>
            <th title="Sustained wind, mph">Wind</th>
            <th title="Rain, in/hr">Rain</th>
            <th title="Snow, in/hr">Snow</th>
          </tr>
        </thead>
        <tbody onMouseLeave={() => onFocus(null)}>
          {route.checkpoints.map((cp, i) => (
            <tr
              key={i}
              className={i === focusedIndex ? 'focused' : undefined}
              onMouseEnter={() => onFocus(i)}
              onClick={() => onFocus(i)}
              title={cp.reasons.join('\n') || undefined}
            >
              <td>{Math.round(cp.mile)}</td>
              <td>{formatTime(cp.eta)}</td>
              <td>
                <span className="dot" style={{ background: levelColor(cp.level) }} />
                {cp.level ? LEVEL_LABEL[cp.level] : '—'}
              </td>
              <td>{cp.weather ? cp.weather.wind_mph.toFixed(0) : '—'}</td>
              <td>{cp.weather ? cp.weather.rain_in_hr.toFixed(2) : '—'}</td>
              <td>{cp.weather ? cp.weather.snow_in_hr.toFixed(1) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

export default memo(CheckpointList)
