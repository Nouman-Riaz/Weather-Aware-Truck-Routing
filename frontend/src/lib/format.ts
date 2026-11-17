export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m} min`
  return `${h}h ${String(m).padStart(2, '0')}m`
}

const timeFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })
const dateTimeFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
})

export const formatTime = (iso: string | Date) => timeFormat.format(new Date(iso))
export const formatDateTime = (iso: string | Date) => dateTimeFormat.format(new Date(iso))

export const formatMiles = (miles: number) => `${Math.round(miles).toLocaleString()} mi`

/** Value for <input type="datetime-local"> in the browser's time zone. */
export function toLocalInputValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 16)
}

export function defaultDeparture(): string {
  const date = new Date(Date.now() + 30 * 60_000)
  date.setMinutes(Math.ceil(date.getMinutes() / 15) * 15, 0, 0)
  return toLocalInputValue(date)
}
