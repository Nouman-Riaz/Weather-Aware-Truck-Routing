import { useEffect, useId, useRef, useState } from 'react'
import { searchPlaces } from '../api'
import type { Place } from '../types'

interface Props {
  label: string
  value: Place
  onChange: (place: Place) => void
  placeholder?: string
}

/** Text input with debounced place autocomplete. Typing clears the coordinates; picking a suggestion sets them. */
export default function PlaceInput({ label, value, onChange, placeholder }: Props) {
  const id = useId()
  const [suggestions, setSuggestions] = useState<Required<Place>[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const typed = useRef(false)

  useEffect(() => {
    if (!typed.current || value.label.trim().length < 3) {
      setSuggestions([])
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      searchPlaces(value.label, controller.signal)
        .then((data) => {
          setSuggestions(data.results)
          setActive(0)
          setOpen(true)
        })
        .catch(() => setSuggestions([]))
    }, 250)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [value.label])

  const pick = (place: Required<Place>) => {
    typed.current = false
    onChange(place)
    setOpen(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') setActive((a) => (a + 1) % suggestions.length)
    else if (e.key === 'ArrowUp') setActive((a) => (a - 1 + suggestions.length) % suggestions.length)
    else if (e.key === 'Enter') pick(suggestions[active])
    else if (e.key === 'Escape') setOpen(false)
    else return
    e.preventDefault()
  }

  const listId = `${id}-list`
  return (
    <div className="field place-input">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        value={value.label}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open && suggestions.length > 0}
        aria-controls={listId}
        onChange={(e) => {
          typed.current = true
          onChange({ label: e.target.value })
        }}
        onFocus={() => suggestions.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={onKeyDown}
        required
      />
      {value.lat !== undefined && <span className="resolved" title="Location confirmed" aria-label="Location confirmed">✓</span>}
      {open && suggestions.length > 0 && (
        <ul className="suggestions" id={listId} role="listbox">
          {suggestions.map((s, i) => (
            <li
              key={`${s.lat},${s.lon},${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'active' : undefined}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(s)
              }}
            >
              {s.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
