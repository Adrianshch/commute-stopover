# Commute Stopover

Find errands along my Central line commute (Woodford ⇄ Holborn), ranked by the extra time each stop adds.

- **On the line**: places within walking distance of the 13 stations. Added time = walk there and back + a "mid-trip" cost (exit, re-enter, wait for next train) at intermediate stations.
- **Off the line**: if there's little on the route (e.g. IKEA), it searches wider London and asks the TfL Journey Planner for the round trip from the best Central line station.

Two data sources:

| | Google Maps (with your key) | OpenStreetMap (no key) |
|---|---|---|
| Search quality | Google's full search: "dim sum" finds Chinese restaurants that serve it, "boots" finds both kinds | Name/tag matching on a weekly snapshot |
| Ratings, live hours, photos | Yes | Hours only where mapped |
| Cost | Free up to 1,000 searches/month (see below) | Free |

Static site: `index.html` + `data/`. The Google key is pasted into the page and stored only in that browser's localStorage, so it's never in this public repo.

## Google Maps setup

About 10 minutes, once. You need a Google account and a card for Google Cloud billing. Google requires the card, but this setup stays inside the free tier.

1. Go to <https://console.cloud.google.com/>, click the project picker → **New project** → name it `commute-stopover`.
2. **Billing** → link a billing account to the project.
3. **APIs & Services → Library**: enable **Maps JavaScript API** and **Places API (New)**.
4. **APIs & Services → Credentials → Create credentials → API key**. Then edit the key:
   - *Application restrictions* → **Websites** → add `https://adrianshch.github.io/*`
   - *API restrictions* → **Restrict key** → tick **Maps JavaScript API** and **Places API (New)**
5. **Cap usage so it can't cost money.** In **APIs & Services → Places API (New) → Quotas & system limits**, find the per-day limit for Text Search requests and set it to **33**. That's at most about 1,000 a month, which is Google's free allowance for searches that include ratings and hours. Also set a **Billing → Budgets & alerts** budget of £1 with email alerts.
6. Open the site, expand **Google Maps data** at the bottom, paste the key, and press **Save**. Do this once on each device (phone, laptop).

**What a search costs:** each search makes about 6 Google requests, one per group of neighbouring stations. A busy group that hits Google's 20-result limit is re-searched station by station, which adds up to 3 more. Searching off the line adds 1. Results are cached in your browser for 12 hours, so repeating a search is free. With the 33/day cap, that's roughly 4–5 searches a day at no cost. Photos only load when you tap a result (1,000 free a month).

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
