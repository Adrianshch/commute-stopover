#!/usr/bin/env python3
"""Check food places against the Food Standards Agency hygiene register (FHRS) to spot ones that have closed.

Every UK food business must register with its council, and closed businesses drop off the register.
For each food place in data/places.json:
  - "v" on the register (by its OSM fhrs:id, or same name nearby / same postcode): ["v", rating, inspection date, osm check date]
        The app shows it as confirmed if inspected in the last 18 months (or checked on OSM in the last year),
        otherwise as "probably open" — councils can be slow to remove closed businesses.
  - "x" likely closed: ["x", reason] — its website says it has closed; or it dropped off the register; or Overture Maps
        (Meta/Microsoft/Foursquare data) marks it permanently closed and no recent inspection says otherwise;
        or its website domain is dead
  - "t" temporarily closed (website notice)
  - "?" not on the register: ["?", osm check date] (only written when there's a check date)
Writes data/verify.json.  Optional: pip install duckdb  -> also uses Overture Maps closure flags.

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


def load_overture_closed(places):
    """Overture Maps places marked permanently_closed near our places (needs duckdb; skipped if unavailable)."""
    try:
        import duckdb  # type: ignore
    except Exception:  # noqa: BLE001
        print("duckdb not installed: skipping Overture check", file=sys.stderr)
        return []
    try:
        cat = json.load(urllib.request.urlopen("https://stac.overturemaps.org/catalog.json", timeout=60))
        release = cat["latest"]
        lats, lons = [p["la"] for p in places], [p["lo"] for p in places]
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
        rows = con.execute(f"""
            SELECT names.primary, ST_Y(geometry), ST_X(geometry), operating_status
            FROM read_parquet('s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*', hive_partitioning=1)
            WHERE bbox.xmin BETWEEN {min(lons) - 0.002} AND {max(lons) + 0.002}
              AND bbox.ymin BETWEEN {min(lats) - 0.002} AND {max(lats) + 0.002}
              AND names.primary IS NOT NULL""").fetchall()
        print(f"overture {release}: {len(rows)} places, {sum(1 for r in rows if r[3] == 'permanently_closed')} marked closed", file=sys.stderr)
        return rows
    except Exception as e:  # noqa: BLE001
        print(f"Overture check failed, skipping: {e}", file=sys.stderr)
        return []


def months_ago(date_str):
    try:
        y, m = int(date_str[:4]), int(date_str[5:7])
    except Exception:  # noqa: BLE001
        return 999
    now = time.gmtime()
    return (now.tm_year - y) * 12 + (now.tm_mon - m)


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

    food = [p for p in places if p.get("amenity") in FOOD_A or p.get("shop") in FOOD_S]
    ov_grid = collections.defaultdict(list)
    for name, lat, lon, st in load_overture_closed(food):
        ov_grid[(round(lat * 400), round(lon * 400))].append((norm(name), lat, lon, st))

    def overture_status(p, n):
        k = (round(p["la"] * 400), round(p["lo"] * 400))
        sts = {st for dx in (-1, 0, 1) for dy in (-1, 0, 1) for (on, la, lo, st) in ov_grid[(k[0] + dx, k[1] + dy)]
               if dist(p["la"], p["lo"], la, lo) < 80 and sim(n, on) >= 0.85}
        return "closed" if sts == {"permanently_closed"} else ("open" if "open" in sts else "")

    out, stats = {}, collections.Counter()
    for p in food:
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
        chk = (p.get("chk") or "")[:10]
        reg = by_id[fid] if fid and fid in by_id else best[2] if best else None
        ov = overture_status(p, n)
        recent = (reg and months_ago(reg["d"]) <= 18) or months_ago(chk) <= 12
        if site == "closed":
            out[p["id"]] = ["x", "site"]
        elif site == "temp":
            out[p["id"]] = ["t", "site"]
        elif reg and not (ov == "closed" and not recent):
            out[p["id"]] = ["v", reg["r"], reg["d"], chk]
        elif reg or ov == "closed":
            out[p["id"]] = ["x", "overture"]
        elif fid:
            out[p["id"]] = ["x", "fhrs"]
        elif site == "dead":
            out[p["id"]] = ["x", "dead"]
        elif chk:
            out[p["id"]] = ["?", chk]
        stats[out.get(p["id"], ["?"])[0] + ("" if out.get(p["id"], ["?"])[0] != "v" else "-recent" if recent else "-old")] += 1
    json.dump({"generated": time.strftime("%Y-%m-%d"), "places": out},
              open(os.path.join(DATA, "verify.json"), "w"), separators=(",", ":"))
    print("verified (v) / likely closed (x) / temporarily closed (t) / unverified (?):", dict(stats), file=sys.stderr)


if __name__ == "__main__":
    main()
