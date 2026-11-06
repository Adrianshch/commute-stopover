# Commute Stopover

Find food and errands within a 15-minute walk of my Central line commute (Woodford ⇄ Holborn) and of Bush House (work, walked from Holborn). Results are sorted by walk time from the nearest stop.

## How search works (free, no API keys)

- **Places:** a weekly OpenStreetMap snapshot of everything named near the 13 stations and Bush House (`data/places.json`, built by `scripts/build_places.py`).
- **Food knowledge** (`data/food.json`), hand-written and easy to extend:
  - *groups*: "mexican" also matches tex-mex, tacos and burritos; "asian" matches chinese, korean, oriental and more
  - *types*: "grocery" means supermarket, convenience, greengrocer and so on; "boots" also means shoe shops
  - *dishes*: "dosa" is confirmed by a name or menu, and is *likely* at South Indian or Sri Lankan places
  - *nameHints*: guesses a cuisine from the name ("China Ark" → chinese), since about half of places have no cuisine tag
  - *chains*: known menus (Wagamama → ramen, Dishoom → lassi)
- **Menus:** `scripts/crawl_menus.py` reads each restaurant website's home and menu pages, PDF menus included, and records which dish words appear (`data/menus.json`).
- Results come in two groups: **Serves X** (confirmed by name, cuisine tag, menu or chain) and **Might serve X** (the cuisine usually has it).
- **Off the line:** if fewer than 3 places are confirmed nearby, it searches wider London with [Photon](https://photon.komoot.io) and shows the TfL Journey Planner time from the best stop.

There's no free source of reviews, so unlike Google it can't search review text. Menus and the knowledge file stand in for that.

## Refresh the data

```bash
pip install pypdf
python3 scripts/build_places.py
python3 scripts/crawl_menus.py
```

The `Refresh places and menus` workflow does this every Monday, and GitHub Pages redeploys automatically.

## Run locally

```bash
python3 -m http.server 8000
```

Then open http://localhost:8000/?q=dosa

## Google Maps mode (paused)

The page also supports Google Places search (ratings, live hours, photos) once a key is pasted into the "Google Maps data" panel. It's paused for now; the setup notes are kept below.

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
