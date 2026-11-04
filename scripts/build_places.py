#!/usr/bin/env python3
"""Download named shops/amenities near each Central line station (Woodford -> Holborn)
from OpenStreetMap via Overpass, and write a compact data/places.json for the site.

Run:  python3 scripts/build_places.py
"""
import json, os, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STATIONS = json.load(open(os.path.join(HERE, "..", "data", "stations.json")))
RADIUS_M = 925  # ~15 min walk at 80 m/min with a 1.3 street-circuity factor
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
KEYS = ["shop", "amenity", "craft", "leisure", "healthcare"]
SKIP_AMENITY = {
    "parking", "parking_entrance", "parking_space", "bicycle_parking", "motorcycle_parking", "bench",
    "waste_basket", "waste_disposal", "recycling", "telephone", "post_box", "atm", "vending_machine",
    "toilets", "drinking_water", "shelter", "bicycle_rental", "charging_station", "taxi", "clock",
    "fountain", "grit_bin", "loading_dock", "bus_station", "car_sharing", "kick-scooter_rental",
    "letter_box", "smoking_area", "public_bookcase", "give_box", "lounger", "dog_toilet",
}
KEEP_TAGS = ["name", "brand", "shop", "amenity", "craft", "leisure", "healthcare", "cuisine",
             "opening_hours", "website", "addr:housenumber", "addr:street", "addr:postcode"]
SHORT = {"addr:housenumber": "hn", "addr:street": "st", "addr:postcode": "pc", "opening_hours": "oh",
         "website": "web"}


def query():
    parts = []
    for s in STATIONS:
        for k in KEYS:
            parts.append(f'nwr(around:{RADIUS_M},{s["lat"]},{s["lon"]})["{k}"]["name"];')
    return "[out:json][timeout:180];(\n" + "\n".join(parts) + "\n);out center tags;"


def fetch(q):
    body = urllib.parse.urlencode({"data": q}).encode()
    for attempt in range(6):
        for url in ENDPOINTS:
            try:
                req = urllib.request.Request(url, data=body, headers={"User-Agent": "commute-stopover/1.0 (personal project)"})
                with urllib.request.urlopen(req, timeout=200) as r:
                    data = json.load(r)
                    if data.get("elements"):
                        print(f"ok from {url}", file=sys.stderr)
                        return data["elements"]
            except Exception as e:  # noqa: BLE001
                print(f"{url}: {e}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    sys.exit("All Overpass servers failed")


def main():
    els = fetch(query())
    seen, out = set(), []
    for e in els:
        key = e["type"][0] + str(e["id"])
        if key in seen:
            continue
        seen.add(key)
        t = e.get("tags", {})
        if t.get("amenity") in SKIP_AMENITY and not t.get("shop"):
            continue
        if any(t.get(k) for k in ("disused:shop", "disused:amenity", "highway", "railway", "public_transport")):
            continue
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        if lat is None:
            continue
        p = {"id": key, "la": round(lat, 6), "lo": round(lon, 6)}
        for k in KEEP_TAGS:
            if t.get(k):
                p[SHORT.get(k, k)] = t[k]
        out.append(p)
    out.sort(key=lambda p: p["id"])
    path = os.path.join(HERE, "..", "data", "places.json")
    with open(path, "w") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d"), "radius_m": RADIUS_M, "places": out}, f,
                  separators=(",", ":"), ensure_ascii=False)
    print(f"wrote {len(out)} places -> {path} ({os.path.getsize(path)//1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
