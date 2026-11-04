# Commute Stopover

Find errands along my Central line commute (Woodford ⇄ Holborn), ranked by the extra time each stop adds.

- **On the line**: shops/restaurants within walking distance of the 13 stations, from a weekly OpenStreetMap snapshot (`data/places.json`). Added time = walk there and back + a "mid-trip" cost (exit, re-enter, wait for next train) at intermediate stations.
- **Off the line**: if there's little on the route (e.g. IKEA), it searches London with [Photon](https://photon.komoot.io) and asks the TfL Journey Planner for the round trip from the best Central line station.

No API keys needed. Static site: `index.html` + `data/`.

## Update the places data

```bash
python3 scripts/build_places.py
```

The `Refresh places data` workflow (in `.github/workflows`) does this every Monday; GitHub Pages redeploys from `main` automatically.

## Run locally

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000/?q=pho
