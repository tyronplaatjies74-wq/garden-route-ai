import requests, re, json, os, time, copy, tempfile
from bs4 import BeautifulSoup
from scrapers.common import normalise_town, make_id, clean_date

HEADERS = {"User-Agent": "Mozilla/5.0 GardenRouteAI-Bot/1.0"}
TOWNS = ["George","Knysna","Plettenberg Bay","Plett","Mossel Bay","Sedgefield","Wilderness","Oudtshoorn","Hartenbos","Great Brak River","Little Brak River","Tsitsikamma","Natures Valley","Stilbaai","Riversdale","Heidelberg"]

PLACEHOLDER_DATE = "See link for date"

# ---------------------------------------------------------------------------
# Disk cache shared by the per-town wrappers (events_george, events_knysna, ...).
# Each wrapper runs in its own process, so only the file is shared. Without it,
# every wrapper would re-fetch all the sites (4x scraping).
#   - Not saved if any fetch failed (so a broken run is retried, not frozen in).
#   - Set GR_NO_CACHE=1 to bypass it while developing.
# ---------------------------------------------------------------------------
_CACHE_FILE = os.path.join(tempfile.gettempdir(), "gardenroute_scrape_cache.json")
_CACHE_TTL = 3600
_MEMORY_CACHE = None
_FETCH_FAILED = False

def _cache_enabled():
    return os.environ.get("GR_NO_CACHE") != "1"

def _load_cache():
    global _MEMORY_CACHE
    if not _cache_enabled():
        return None
    if _MEMORY_CACHE is not None:
        return copy.deepcopy(_MEMORY_CACHE)
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - data.get("ts", 0) < _CACHE_TTL:
                _MEMORY_CACHE = data.get("events", [])
                return copy.deepcopy(_MEMORY_CACHE)
    except Exception:
        pass
    return None

def _save_cache(events):
    global _MEMORY_CACHE
    if not _cache_enabled():
        return
    _MEMORY_CACHE = copy.deepcopy(events)
    try:
        tmp = _CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "events": events}, f)
        os.replace(tmp, _CACHE_FILE)          # atomic: readers never see a half-written file
    except Exception:
        pass

# Only reject real boilerplate, not any title that merely contains a word
# ("Menu Tasting Evening" and "Cookie Decorating Workshop" are real events).
BAD_EXACT = {
    "menu", "login", "log in", "sign in", "subscribe", "advertisement", "advertisements",
    "cookies", "cookie", "privacy", "read more", "load more", "view all", "share",
}
BAD_PHRASES = re.compile(
    r"\b(cookie (policy|settings|notice|consent|preferences)|privacy (policy|notice)|"
    r"terms (and|&) conditions|subscribe to|sign up for|newsletter sign ?up|accept (all )?cookies)\b",
    re.I,
)

def guess_town(text):
    text = (text or "").lower()
    for t in TOWNS:
        if t.lower() in text:
            return "Plettenberg Bay" if t == "Plett" else t
    return "Garden Route"

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def is_junk_title(title):
    t = title.lower().strip(" .:-|")
    return t in BAD_EXACT or bool(BAD_PHRASES.search(t))

class EventList(list):
    """A list that also remembers (title, town) -> record, so dedupe is O(1) per event."""
    def __init__(self):
        super().__init__()
        self.by_key = {}

def add_event(events, title, town, date, link):
    title = clean(title)
    if len(title) < 3 or len(title) > 120:
        return
    if is_junk_title(title):
        return
    town = normalise_town(town)
    iso_date = clean_date(date) if date else None
    date_val = iso_date or clean(date) or PLACEHOLDER_DATE
    has_date = date_val != PLACEHOLDER_DATE

    key = (title.lower(), town.lower())
    existing = events.by_key.get(key)
    if existing is not None:
        old_has_date = existing["date"] != PLACEHOLDER_DATE
        if not has_date:
            return                                   # nothing new to learn
        if not old_has_date:
            existing["date"] = date_val              # upgrade the dateless copy
            existing["id"] = make_id(title, date, town)
            return
        if existing["date"] == date_val:
            return                                   # true duplicate
        key = key + (date_val,)                      # same title, different date = separate occurrence
        if key in events.by_key:
            return

    rec = {
        "id": make_id(title, date, town),
        "title": title,
        "town": town,
        "date": date_val,
        "link": link,
        "source": town.lower()
    }
    events.by_key[key] = rec
    events.append(rec)

def fetch(url):
    global _FETCH_FAILED
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        _FETCH_FAILED = True
        print(f"FAIL {url}: {e}")
        return None

# Capture the whole date text (ranges like "14-16 November 2026" contain a hyphen),
# but stop at the next labelled field or end of line.
DATE_RE = re.compile(
    r"Date:\s*([^\n|]+?)(?=\s*(?:Time|Venue|Location|Price|Cost|Contact|Where|Entry|Tickets?)\s*:|\n|\||$)",
    re.I,
)

def scrape_all():
    global _FETCH_FAILED
    cached = _load_cache()
    if cached is not None:
        return cached
    _FETCH_FAILED = False
    events = EventList()
    soup = fetch("https://gardenroute.com/events/")
    if soup:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/event" in href:
                add_event(events, a.get_text(), guess_town(a.get_text() + href), "", href if href.startswith("http") else "https://gardenroute.com" + href)
    soup = fetch("https://toodoo.co.za/events/")
    if soup:
        for card in soup.find_all(["article","div"], class_=re.compile("event|card|post", re.I)):
            h = card.find(["h2","h3","h4"])
            a = card.find("a", href=True)
            if not h or not a: continue
            link = a["href"] if a["href"].startswith("http") else "https://toodoo.co.za" + a["href"]
            add_event(events, h.get_text(), guess_town(card.get_text()), "", link)
    for url in ["https://ontheroute.co.za/", "https://ontheroute.co.za/garden-route-market-guide/"]:
        soup = fetch(url)
        if not soup: continue
        for h in soup.find_all(["h2","h3"]):
            title = h.get_text()
            nxt = h.find_next_sibling()
            txt = (nxt.get_text() if nxt else "") + "\n" + title   # newline so the date match can't run into the title
            m = DATE_RE.search(txt)
            add_event(events, title, guess_town(txt), m.group(1).strip() if m else "", url)
    markets = [
        ("Wild Oats Community Farmers Market", "Sedgefield", "Every Saturday 07:30-12:00"),
        ("Outeniqua Family Market", "George", "Every Saturday 08:00-14:00"),
        ("Mosaic Village Market", "Sedgefield", "Every Saturday 08:00-14:00"),
        ("Scarab Village Craft Market", "Sedgefield", "Every Saturday 08:30-13:00"),
        ("Friday Market Knysna", "Knysna", "Every Friday 16:00-20:00"),
        ("Milkwood Village Friday Night Market", "Wilderness", "Every Friday from 17:00"),
        ("Sunday Market at the Botanical Garden", "George", "Every Sunday 09:00-14:00"),
        ("Wednesday Market at Old Nick", "Plettenberg Bay", "Every Wednesday 09:00-14:00"),
        ("The Goods Shed Outside Market", "Mossel Bay", "3rd Saturday 09:00-14:00"),
        ("Hartenbos Boeremark", "Hartenbos", "2nd and last Saturday 08:00-14:00"),
    ]
    for title, town, date in markets:
        add_event(events, title, town, date, "https://ontheroute.co.za/garden-route-market-guide/")
    soup = fetch("https://georgeherald.com/search/?q=Eyes+on+arts") or fetch("https://georgeherald.com/")
    if soup:
        for a in soup.find_all("a", href=True):
            if "eyes-on-arts" in a["href"].lower():
                link = a["href"] if a["href"].startswith("http") else "https://georgeherald.com" + a["href"]
                sub = fetch(link)
                if not sub: continue
                text = sub.get_text()
                for m in re.finditer(r"(\d{1,2}(?:-\d{1,2})?\s*(?:October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\n|]{0,5}\|?\s*)([A-Z][^\n]{5,90})", text):
                    title = m.group(2).strip().split(" at ")[0].split(" - ")[0]
                    add_event(events, title, guess_town(text[m.start():m.start()+500]), m.group(1).strip(), link)
                break
    result = list(events)   # plain list: safe across the process boundary and for JSON
    if _FETCH_FAILED:
        print("Some sites failed - not caching, so the next caller retries.")
    else:
        _save_cache(result)
    return result
