import { memo, useState } from 'react'
import { defaultDeparture } from '../lib/format'
import type { Place, PlanRequest } from '../types'
import PlaceInput from './PlaceInput'

const EXAMPLES: { label: string; origin: Required<Place>; destination: Required<Place> }[] = [
  {
    label: 'Denver → Salt Lake City',
    origin: { label: 'Denver, Colorado, US', lat: 39.7392, lon: -104.9849 },
    destination: { label: 'Salt Lake City, Utah, US', lat: 40.7596, lon: -111.8868 },
  },
  {
    label: 'Chicago → Memphis',
    origin: { label: 'Chicago, Illinois, US', lat: 41.8756, lon: -87.6244 },
    destination: { label: 'Memphis, Tennessee, US', lat: 35.1495, lon: -90.049 },
  },
  {
    label: 'Dallas → Chicago',
    origin: { label: 'Dallas, Texas, US', lat: 32.7763, lon: -96.7969 },
    destination: { label: 'Chicago, Illinois, US', lat: 41.8756, lon: -87.6244 },
  },
]

const INTERVALS = [10, 25, 50] as const

interface Props {
  loading: boolean
  onSubmit: (request: PlanRequest) => void
}

function PlanForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place>({ label: '' })
  const [destination, setDestination] = useState<Place>({ label: '' })
  const [departure, setDeparture] = useState(defaultDeparture)
  const [load, setLoad] = useState('38000')
  const [intervalMi, setIntervalMi] = useState<(typeof INTERVALS)[number]>(25)
  const [hos, setHos] = useState(true)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      load_lb: Number(load),
      interval_mi: intervalMi,
      hos,
    })
  }

  return (
    <form className="plan-form" onSubmit={submit}>
      <div className="places">
        <PlaceInput label="Origin" value={origin} onChange={setOrigin} placeholder="City or address" />
        <button
          type="button"
          className="swap"
          title="Swap origin and destination"
          aria-label="Swap origin and destination"
          onClick={() => {
            setOrigin(destination)
            setDestination(origin)
          }}
        >
          ⇅
        </button>
        <PlaceInput label="Destination" value={destination} onChange={setDestination} placeholder="City or address" />
      </div>

      <div className="row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input id="departure" type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="with-unit">
            <input
              id="load"
              type="number"
              min={0}
              max={200000}
              step={500}
              value={load}
              onChange={(e) => setLoad(e.target.value)}
              required
            />
            <span>lb</span>
          </div>
        </div>
      </div>

      <div className="row align-end">
        <div className="field">
          <span className="label">Weather sample every</span>
          <div className="segmented" role="radiogroup" aria-label="Weather sampling interval">
            {INTERVALS.map((value) => (
              <button
                type="button"
                key={value}
                role="radio"
                aria-checked={intervalMi === value}
                className={intervalMi === value ? 'on' : undefined}
                onClick={() => setIntervalMi(value)}
              >
                {value} mi
              </button>
            ))}
          </div>
        </div>
        <label className="toggle" title="FMCSA hours of service: 30-min break after 8 h driving, 10-h rest after 11 h">
          <input type="checkbox" checked={hos} onChange={(e) => setHos(e.target.checked)} />
          <span>HOS breaks</span>
        </label>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? <span className="spinner" aria-hidden /> : null}
        {loading ? 'Checking routes & forecasts…' : 'Find safest route'}
      </button>

      <div className="examples">
        <span>Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            type="button"
            key={ex.label}
            className="link"
            onClick={() => {
              setOrigin(ex.origin)
              setDestination(ex.destination)
            }}
          >
            {ex.label}
          </button>
        ))}
      </div>
    </form>
  )
}

export default memo(PlanForm)
