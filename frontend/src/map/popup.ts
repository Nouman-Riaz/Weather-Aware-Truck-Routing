import { formatDateTime } from '../lib/format'
import { LEVEL_LABEL, levelColor } from '../lib/risk'
import type { Checkpoint, RouteOption, Stop } from '../types'

const escape = (text: string) =>
  text.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)

export function checkpointPopup(route: RouteOption, cp: Checkpoint): string {
  const level = cp.level ? LEVEL_LABEL[cp.level] : 'No forecast'
  const wx = cp.weather
  const conditions = wx
    ? `<dl class="popup-grid">
        <dt>Wind</dt><dd>${wx.wind_mph.toFixed(0)} mph <span class="muted">(gusts ${wx.gust_mph.toFixed(0)})</span></dd>
        <dt>Rain</dt><dd>${wx.rain_in_hr.toFixed(2)} in/hr</dd>
        <dt>Snow</dt><dd>${wx.snow_in_hr.toFixed(2)} in/hr</dd>
        <dt>Temp</dt><dd>${wx.temp_f}°F</dd>
      </dl>`
    : '<p class="muted">Beyond the forecast horizon.</p>'
  const reasons = cp.reasons.length ? `<ul class="popup-reasons">${cp.reasons.map((r) => `<li>${escape(r)}</li>`).join('')}</ul>` : ''
  return `
    <div class="popup">
      <div class="popup-head">
        <span class="route-dot route-${route.id}">${route.id}</span>
        <strong>Mile ${Math.round(cp.mile)}</strong>
        <span class="chip" style="--chip:${levelColor(cp.level)}">${level}</span>
      </div>
      <div class="popup-eta">ETA ${formatDateTime(cp.eta)}</div>
      ${conditions}
      ${reasons}
    </div>`
}

export function stopPopup(route: RouteOption, stop: Stop): string {
  const title = stop.kind === 'rest' ? '10-hour rest (HOS)' : '30-minute break (HOS)'
  return `
    <div class="popup">
      <div class="popup-head"><span class="route-dot route-${route.id}">${route.id}</span><strong>${title}</strong></div>
      <div class="popup-eta">${formatDateTime(stop.start)} → ${formatDateTime(stop.end)}</div>
    </div>`
}
