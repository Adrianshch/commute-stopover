#!/usr/bin/env python3
"""Scan the websites of food places near the line for dish words (from data/food.json).

Writes data/menus.json: {"hosts": {"example.com": ["dosa", "masala dosa", "lassi", ...]}} (exact dish words found). The app links a place to its
website's host, so a sushi bar whose menu lists ramen shows up for "ramen".

Run:  python3 scripts/crawl_menus.py      (optional: pip install pypdf  -> also reads PDF menus)
"""
import concurrent.futures as cf, html.parser, io, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
FOOD_AMENITIES = {"restaurant", "fast_food", "cafe", "food_court", "pub", "bar", "ice_cream", "biergarten"}
FOOD_SHOPS = {"bakery", "pastry", "deli", "confectionery", "coffee", "tea"}
SKIP_HOSTS = re.compile(r"(facebook|instagram|twitter|x\.com|tiktok|tripadvisor|deliveroo|ubereats|just-eat|justeat|google|linktr\.ee|yelp|opentable|resy|sevenrooms|wikipedia|wix\.com$)")
MENU_LINK = re.compile(r"menu|food|eat|dish|carte|drinks|lunch|dinner|brunch|breakfast", re.I)
UA = "Mozilla/5.0 (compatible; commute-stopover/1.0; personal menu index)"
MAX_BYTES = 2_500_000

try:
    import pypdf  # type: ignore
except Exception:  # noqa: BLE001
    pypdf = None


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"[^a-z0-9]+", " ", s) + " "


class TextAndLinks(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self._skip, self._a = [], [], 0, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript", "svg") and a.get("type") != "application/ld+json":
            self._skip += 1
        if tag == "a" and a.get("href"):
            self._a = [a["href"], ""]
            self.links.append(self._a)
        if tag == "img" and a.get("alt"):
            self.text.append(a["alt"])

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self._skip:
            self._skip -= 1
        if tag == "a":
            self._a = None

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._a is not None:
            self._a[1] += data


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"})
    with urllib.request.urlopen(req, timeout=12) as r:
        ctype = r.headers.get("Content-Type", "")
        body = r.read(MAX_BYTES)
        return r.geturl(), ctype, body


def page_text(url):
    final, ctype, body = fetch(url)
    if "pdf" in ctype or final.lower().endswith(".pdf"):
        if not pypdf:
            return final, "", []
        reader = pypdf.PdfReader(io.BytesIO(body))
        return final, " ".join((p.extract_text() or "") for p in reader.pages[:8]), []
    charset = re.search(r"charset=([\w-]+)", ctype)
    html = body.decode(charset.group(1) if charset else "utf-8", "replace")
    p = TextAndLinks()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001
        pass
    return final, " ".join(p.text), p.links


def scan_host(base, terms):
    found, pages = set(), 0
    try:
        final, text, links = page_text(base)
        pages += 1
    except Exception:  # noqa: BLE001
        return None
    corpus = [norm(text)]
    host = urllib.parse.urlparse(final).netloc
    cands = []
    for href, label in links:
        u = urllib.parse.urljoin(final, href.strip())
        pu = urllib.parse.urlparse(u)
        if pu.scheme not in ("http", "https"):
            continue
        same = pu.netloc == host or pu.netloc.endswith("." + host.removeprefix("www."))
        is_pdf = pu.path.lower().endswith(".pdf")
        if (same or is_pdf) and (MENU_LINK.search(label or "") or MENU_LINK.search(pu.path)):
            score = 0 if re.search("menu", (label or "") + pu.path, re.I) else 1
            cands.append((score, u.split("#")[0]))
    seen = {final.split("#")[0]}
    picked = []
    for _, u in sorted(cands):
        if u not in seen:
            seen.add(u); picked.append(u)
        if len(picked) >= 3:
            break
    if not picked:
        picked = [urllib.parse.urljoin(final, "/menu")]
    for u in picked:
        try:
            _, t, _ = page_text(u)
            corpus.append(norm(t)); pages += 1
        except Exception:  # noqa: BLE001
            pass
    blob = " ".join(corpus)
    for canon, variants in terms:
        if any(v in blob for v in variants):
            found.add(canon)
    return sorted(found)


def main():
    food = json.load(open(os.path.join(DATA, "food.json")))
    terms = sorted({t.lower() for d in food["dishes"] for t in d["terms"]})
    terms = [(t, [norm(t)]) for t in terms]
    places = json.load(open(os.path.join(DATA, "places.json")))["places"]
    hosts = {}
    for p in places:
        if p.get("amenity") in FOOD_AMENITIES or p.get("shop") in FOOD_SHOPS:
            w = p.get("web")
            if not w:
                continue
            if not w.startswith("http"):
                w = "https://" + w
            host = urllib.parse.urlparse(w).netloc.lower()
            if not host or SKIP_HOSTS.search(host):
                continue
            hosts.setdefault(host.removeprefix("www."), w)
    print(f"scanning {len(hosts)} websites…", file=sys.stderr)
    out, ok, t0 = {}, 0, time.time()
    with cf.ThreadPoolExecutor(24) as ex:
        futs = {ex.submit(scan_host, url, terms): h for h, url in hosts.items()}
        for i, f in enumerate(cf.as_completed(futs), 1):
            res = f.result()
            if res is not None:
                ok += 1
                if res:
                    out[futs[f]] = res
            if i % 100 == 0:
                print(f"  {i}/{len(hosts)}  ({time.time()-t0:.0f}s)", file=sys.stderr)
    path = os.path.join(DATA, "menus.json")
    json.dump({"generated": time.strftime("%Y-%m-%d"), "scanned": len(hosts), "reachable": ok, "hosts": dict(sorted(out.items()))},
              open(path, "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"reachable {ok}/{len(hosts)}, with dishes {len(out)} -> {path} ({os.path.getsize(path)//1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
