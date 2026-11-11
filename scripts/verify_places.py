#!/usr/bin/env python3
"""Check food places against the Food Standards Agency hygiene register (FHRS) to spot ones that have closed.

Every UK food business must register with its council, and closed businesses drop off the register.
For each food place in data/places.json:
  - "v" verified: found in the register (by its OSM fhrs:id, or same name nearby / same postcode)
  - "x" likely closed: its fhrs:id is no longer in the register and nothing with its name is nearby,
        or its website says it has closed / the domain is dead (from data/menus.json)
  - "t" temporarily closed (website notice)
  - (absent) unverified: no evidence either way
Writes data/verify.json: {"places": {"n123": ["v", "5", "2026-03-18"], "w456": ["x", "fhrs"], ...}}

Run:  python3 scripts/verify_places.py   (after build_places.py and crawl_menus.py)
"""
import collections, difflib, json, math, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
# Councils the route passes through (FHRS local authority codes)
COUNCILS = {"506": "Camden", "508": "City of London", "512": "Hackney", "519": "Islington", "525": "Newham",
            "526": "Redbridge", "530": "Tower Hamlets", "531": "Waltham Forest", "533": "Westminster",
            "522": "Lambeth", "528": "Southwark", "115": "Epping Forest"}
FOOD_A = {"restaurant", "fast_food", "cafe", "pub", "bar", "food_court", "ice_cream", "biergarten"}
FOOD_S = {"supermarket", "convenience", "bakery", "deli", "greengrocer", "butcher", "confectionery", "pastry", "coffee",
          "alcohol", "seafood", "cheese", "chocolate", "tea", "health_food", "frozen_food", "food", "grocery", "beverages", "wine"}
STOP = {"the", "ltd", "limited", "restaurant", "cafe", "bar", "london", "and", "co", "uk", "kitchen", "plc", "t", "a",
        "coffee", "food", "foods", "s", "store", "shop", "pub", "takeaway", "express", "local", "ltd.", "llp"}


def norm(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower().replace("&", " and ").replace("é", "e"))
    return " ".join(w for w in s.split() if w not in STOP)


def sim(a, b):
    if not a or not b:
        return 0.0
    if a == b or (min(len(a), len(b)) > 3 and (a in b or b in a)):
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb)
    return max(jac, difflib.SequenceMatcher(None, a, b).ratio())


def dist(a, b, c, d):
    return 6371000 * 2 * math.asin(math.sqrt(math.sin(math.radians(c - a) / 2) ** 2 +
                                             math.cos(math.radians(a)) * math.cos(math.radians(c)) * math.sin(math.radians(d - b) / 2) ** 2))


def load_register():
    reg = []
    for code in COUNCILS:
        url = f"https://ratings.food.gov.uk/api/open-data-files/FHRS{code}en-GB.json"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "commute-stopover/1.0 (personal project)"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.load(r)
                break
            except Exception as e:  # noqa: BLE001
                print(f"{code}: {e}", file=sys.stderr)
                time.sleep(10 * (attempt + 1))
        else:
            sys.exit(f"couldn't download register for {COUNCILS[code]}")
        for e in data["FHRSEstablishment"]["EstablishmentCollection"]:
            g = e.get("Geocode") or {}
            try:
                lat, lon = float(g["Latitude"]), float(g["Longitude"])
            except Exception:  # noqa: BLE001
                lat = lon = None
            reg.append({"id": str(e["FHRSID"]), "n": norm(e["BusinessName"]), "pc": (e.get("PostCode") or "").replace(" ", "").upper(),
                        "lat": lat, "lon": lon, "r": e.get("RatingValue") or "", "d": (e.get("RatingDate") or "")[:10]})
    print(f"register: {len(reg)} businesses in {len(COUNCILS)} councils", file=sys.stderr)
    return reg


def host_of(u):
    if not u:
        return ""
    if not u.startswith("http"):
        u = "https://" + u
    return urllib.parse.urlparse(u).netloc.lower().removeprefix("www.")


def main():
    reg = load_register()
    by_id = {r["id"]: r for r in reg}
    grid, by_pc = collections.defaultdict(list), collections.defaultdict(list)
    for r in reg:
        if r["lat"] is not None:
            grid[(round(r["lat"] * 200), round(r["lon"] * 200))].append(r)
        by_pc[r["pc"]].append(r)
    places = json.load(open(os.path.join(DATA, "places.json")))["places"]
    try:
        site_status = json.load(open(os.path.join(DATA, "menus.json"))).get("status", {})
    except FileNotFoundError:
        site_status = {}

    out, stats = {}, collections.Counter()
    for p in places:
        if p.get("amenity") not in FOOD_A and p.get("shop") not in FOOD_S:
            continue
        n = norm(p.get("name") or p.get("brand"))
        pc = (p.get("pc") or "").replace(" ", "").upper()
        k = (round(p["la"] * 200), round(p["lo"] * 200))
        cands = [r for dx in (-1, 0, 1) for dy in (-1, 0, 1) for r in grid[(k[0] + dx, k[1] + dy)]]
        if pc:
            cands += by_pc.get(pc, [])
        best = None
        for r in cands:
            d = dist(p["la"], p["lo"], r["lat"], r["lon"]) if r["lat"] is not None else 1e9
            s = sim(n, r["n"])
            near = d < 150 or (pc and r["pc"] == pc)
            if near and (s >= 0.8 or (s >= 0.6 and d < 40)):
                if not best or (s, -d) > (best[0], -best[1]):
                    best = (s, d, r)
        fid = (p.get("fhrs") or "").strip()
        site = site_status.get(host_of(p.get("web")), "")
        if fid and fid in by_id:
            r = by_id[fid]
            out[p["id"]] = ["v", r["r"], r["d"]]
        elif best:
            out[p["id"]] = ["v", best[2]["r"], best[2]["d"]]
        elif site == "closed":
            out[p["id"]] = ["x", "site"]
        elif fid:
            out[p["id"]] = ["x", "fhrs"]
        elif site == "dead":
            out[p["id"]] = ["x", "dead"]
        if site == "temp" and p["id"] in out and out[p["id"]][0] == "v":
            out[p["id"]] = ["t", "site"]
        elif site == "temp" and p["id"] not in out:
            out[p["id"]] = ["t", "site"]
        stats[out.get(p["id"], ["?"])[0]] += 1
    json.dump({"generated": time.strftime("%Y-%m-%d"), "places": out},
              open(os.path.join(DATA, "verify.json"), "w"), separators=(",", ":"))
    print("verified (v) / likely closed (x) / temporarily closed (t) / unverified (?):", dict(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
