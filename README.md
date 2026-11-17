# Weather-Aware Truck Routing

A React + Django app that helps a truck driver pick the safest route. It looks at the forecast weather the truck will actually meet along each route, the load weight and the travel time.

- **Live app:** _add hosted URL_
- **Walkthrough:** _add Loom URL_

## Features

- **3 route options** from OSRM. The fastest route comes first.
- **Weather checkpoints every 10, 25 or 50 miles.** Each checkpoint is forecast for the hour the truck is expected to get there, not the departure time.
- **Risk levels** from the assessment's wind, rain and snow thresholds, plus the load-weight rules.
- **A recommendation with reasons**, e.g. "Fewer Severe miles than Route A (0 mi vs 42 mi)" or "Adds 46 min over the fastest route in exchange for lower risk".
- **Map:** every route, with the selected route coloured by risk. Checkpoints have popups showing ETA, conditions and why they got their rating. Each route has a summary label (time, peak risk, ★ for the recommended route), and hours-of-service stops are marked.
- **Corridor heatmap with a 0–48 h slider.** You can switch it between overall risk, wind, rain and snow, and play it as an animation. Truck markers move along each route to where the truck would be at that hour.

## How it works

```
origin/destination ─► geocode (Photon)
                   ─► 3 routes (OSRM) ─► checkpoints every N miles, each with an ETA (truck speed + HOS)
                                     ─► hourly forecast at each checkpoint's ETA (Open-Meteo)
                                     ─► risk level per checkpoint ─► miles per level ─► ranked recommendation
routes ─► corridor grid (≤220 points) ─► 49 hourly forecasts ─► heatmap + slider
```

### Routing (`backend/routing/services/routing.py`)
- OSRM `alternatives` often returns only 1–2 routes. To fill the gap, the app routes through via-points placed to either side of the midpoint. A candidate is dropped if:
  - it is more than 1.6× slower than the fastest route,
  - it overlaps an existing option by more than 85%, or
  - it doubles back (a via-point that snapped onto a side road).
- **Truck speed:** OSRM's car-profile durations are capped at 65 mph on every road segment.

### ETAs (`checkpoints.py`, `hos.py`)
- The ETA at any mile comes from the per-segment durations OSRM returns along the route, not from an average speed.
- With **HOS** turned on (the default), the trip includes the FMCSA hours-of-service stops:
  - a 30-minute break after 8 hours of driving,
  - a 10-hour rest after 11 hours of driving.
- These stops change when the truck reaches later checkpoints, and so which weather it meets.

### Risk (`risk.py`)

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | <25 | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain (in/hr) | <0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow (in/hr) | <0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

- **Boundaries:** each range includes its lower bound, so 0.25 in/hr of rain is High. "No Travel" for rain and snow is strictly greater than the top value, as the table is written.
- **Load rules:**
  - ≥55 mph is No Travel for any load.
  - 45–54 mph with a load over 30,000 lb is No Travel.
  - 35–44 mph with a load over 40,000 lb is Severe.
- **Checkpoint level:** the worst of the wind, rain and snow levels.
- **Inputs:**
  - Wind is the sustained 10 m wind speed. Gusts are shown but not scored.
  - Rain is the hourly rain plus showers.
  - Snow is the hourly snowfall depth.

### Recommendation (`recommend.py`)
- **Miles per level:** each checkpoint stands for the stretch halfway to its neighbours, so the miles across all levels add up to the route length.
- **Ranking order:**
  0. Fewest **No Travel** miles. The brief doesn't list No Travel, but it is worse than Severe, so it is compared first.
  1. Fewest **Severe** miles
  2. Fewest **High** miles
  3. Lowest **average risk**, weighted by distance (Low = 0 … No Travel = 4)
  4. Shortest **trip time**, including HOS stops
- **Tolerances:** differences under 0.5 mi or 0.05 average risk count as ties. This keeps a trivial risk difference from outweighing hours of driving.

### Heatmap (`heatmap.py`, `frontend/src/map`)
- **Grid:** points are kept within a corridor around the routes. The spacing grows until there are at most 220 points, which keeps the weather API usage low.
- **Payload:** the backend returns all 49 hourly values for each point. On the client they become flat properties (`r0..r48`, `w0..w48`, …).
- **Smooth slider:** moving the slider only swaps the MapLibre `heatmap-weight` expression. There is no data reload and no re-tiling. Fractional hours blend the two nearest forecast hours, so playback is smooth.
- **Colours:** layers are scaled using the same thresholds as the risk table, so heatmap colours match the risk legend.

### Performance
- Forecasts are cached for 30 minutes per ~11 km cell per day. Routes and checkpoints share these cells.
- Routes are cached for 1 hour.
- Weather requests are batched at 100 locations per call and run in parallel.
- Route geometry is simplified before it is sent to the browser. Responses are gzipped.

## APIs (no keys required)

| Purpose | Service |
|---|---|
| Routing | [OSRM](https://project-osrm.org/) public server |
| Geocoding | [Photon](https://photon.komoot.io/) (OpenStreetMap) |
| Weather | [Open-Meteo](https://open-meteo.com/) forecast API |
| Basemap | [OpenFreeMap](https://openfreemap.org/) vector tiles |

All the service URLs can be changed with environment variables (`OSRM_URL`, `PHOTON_URL`, `OPEN_METEO_URL`, `OPEN_METEO_API_KEY`).

## Running locally

```bash
# Backend (http://localhost:8000)
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py runserver

# Frontend (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Tests: `cd backend && pytest`. They cover risk thresholds, load rules, HOS timing, checkpoint spacing and coverage, ranking, and the API with mocked providers.

## Deployment

A single Docker image builds the React app, and Django serves it alongside the API using WhiteNoise. To deploy on Render, push the repo and create a Blueprint from `render.yaml`. Any Docker host works the same way:

```bash
docker build -t truck-routing . && docker run -p 8000:8000 truck-routing
```

## Limitations
- OSRM's car profile only approximates truck routing. It has no height, weight or hazmat restrictions. A truck-specific provider such as HERE could replace it behind `routing.py`.
- Forecasts are available up to about 16 days ahead. Miles beyond that are shown as unrated.
- Times are shown in the browser's time zone.
