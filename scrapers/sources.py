import requests, re, json, os, time, copy, tempfile
from bs4 import BeautifulSoup
from scrapers.common import normalise_town, make_id, clean_date
from scrapers.dates import parse_event_dates, apply_dates   # CHANGED: new date parser
from datetime import datetime, timedelta

HEADERS = {"User-Agent": "Mozilla/5.0 GardenRouteAI-Bot/1.0"}
TOWNS = ["George","Knysna","Plettenberg Bay","Plett","Mossel Bay","Sedgefield","Wilderness","Oudtshoorn","Hartenbos","Great Brak River","Little Brak River","Tsitsikamma","Natures Valley","Stilbaai","Riversdale","Heidelberg"]

PLACEHOLDER_DATE = "See link for date"

# ---------------------------------------------------------------------------
# Disk cache shared by the per-town wrappers (events_george, events_knysna, ...).
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
        os.replace(tmp, _CACHE_FILE)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# DATE PARSING
# clean_date() in common.py only understands ISO. This understands humans.
# (parse_human_date is kept for compatibility; add_event now uses
# parse_event_dates from scrapers/dates.py, which also returns end dates.)
# ---------------------------------------------------------------------------
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}

def parse_human_date(raw, now=None):
    """'14-16 November 2026' -> '2026-11-14', '14 Nov' -> '2026-11-14', 'Every Saturday' -> next Saturday ISO."""
    if not raw:
        return None
    iso = clean_date(raw)
    if iso:
        return iso[:10]

    s = str(raw).strip()
    low = s.lower()
    now = now or datetime.now()
    year = now.year

    m = re.search(r"every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b", low)
    if m:
        target = _WEEKDAYS[m.group(1)]
        delta = (target - now.weekday()) % 7
        return (now + timedelta(days=delta)).date().isoformat()

    m = re.search(r"(1st|2nd|3rd|4th|last)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", low)
    if m:
        target = _WEEKDAYS[m.group(2)]
        delta = (target - now.weekday()) % 7
        if delta == 0:
            delta = 7
        return (now + timedelta(days=delta)).date().isoformat()

    m = re.search(r"(\d{1,2})(?:\s*-\s*\d{1,2})?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\b\s*(\d{4})?", low)
    if m:
        day = int(m.group(1))
        month = _MONTHS[m.group(2)]
        y = int(m.group(3)) if m.group(3) else year
        try:
            d = datetime(y, month, day)
            if not m.group(3) and d < now.replace(hour=0, minute=0, second=0, microsecond=0):
                d = datetime(y + 1, month, day)
            return d.date().isoformat()
        except ValueError:
            pass

    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|june|july|august|september|october|november|december)\s+(\d{1,2})(?:\s*-\s*\d{1,2})?,?\s*(\d{4})?", low)
    if m:
        month = _MONTHS[m.group(1)]
        day = int(m.group(2))
        y = int(m.group(3)) if m.group(3) else year
        try:
            d = datetime(y, month, day)
            if not m.group(3) and d < now.replace(hour=0, minute=0, second=0, microsecond=0):
                d = datetime(y + 1, month, day)
            return d.date().isoformat()
        except ValueError:
            pass

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            pass
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date().isoformat()
        except ValueError:
            pass

    return None

def find_date_in_text(text):
    """Look for any date pattern in a chunk of card text."""
    if not text:
        return ""
    m = DATE_RE.search(text)
    if m:
        return m.group(1).strip()
    m = re.search(r"\d{1,2}(?:\s*-\s*\d{1,2})?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\b[^\n|]{0,12}", text, re.I)
    if m:
        return m.group(0).strip()
    m = re.search(r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\s+\d{1,2}[^\n|]{0,12}", text, re.I)
    if m:
        return m.group(0).strip()
    m = re.search(r"Every\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b[^\n|]{0,20}", text, re.I)
    if m:
        return m.group(0).strip()
    return ""

# ---------------------------------------------------------------------------
# Junk filter
# ---------------------------------------------------------------------------
BAD_EXACT = {
    "menu", "login", "log in", "sign in", "subscribe", "advertisement", "advertisements",
    "cookies", "cookie", "privacy", "read more", "load more", "view all", "share",
}
BAD_PHRASES = re.compile(
    r"\b(cookie (policy|settings|notice|consent|preferences)|privacy (policy|notice)|"
    r"terms (and|&) conditions|subscribe to|sign up for|newsletter sign ?up|accept (all )?cookies|"
    # CHANGED: page banners that were being scraped as events
    r"support (local )?journalism|follow us on|advertise with us|become a member|donate (now|today))\b",
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

def add_event(events, title, town, date, link, source=""):
    title = clean(title)
    if len(title) < 3 or len(title) > 120:
        return
    if is_junk_title(title):
        return
    town = normalise_town(town)

    # CHANGED: parse_event_dates returns start, end and recurrence
    info = parse_event_dates(date) if date else None
    iso_date = info["start"] if info else None
    if iso_date:
        date_val = iso_date
        has_date = True
    else:
        date_val = clean(date) or PLACEHOLDER_DATE
        has_date = date_val != PLACEHOLDER_DATE

    key = (title.lower(), town.lower())
    existing = events.by_key.get(key)
    if existing is not None:
        old_has_date = existing["date"] != PLACEHOLDER_DATE
        old_is_iso = bool(re.match(r"^\d{4}-\d{2}-\d{2}", existing["date"]))
        new_is_iso = bool(re.match(r"^\d{4}-\d{2}-\d{2}", date_val))
        if not has_date:
            return
        if not old_has_date:
            apply_dates(existing, title, town, date_val, info, make_id)   # CHANGED
            if source:
                existing["source"] = source
            return
        if old_is_iso and not new_is_iso:
            return  # don't downgrade ISO to raw string
        if not old_is_iso and new_is_iso:
            apply_dates(existing, title, town, date_val, info, make_id)   # CHANGED
            if source:
                existing["source"] = source
            return
        if existing["date"] == date_val:
            return
        key = key + (date_val,)
        if key in events.by_key:
            return

    rec = {
        "id": make_id(title, date_val, town),
        "title": title,
        "town": town,
        "date": date_val,
        "link": link,
        "source": source or town.lower()
    }
    apply_dates(rec, title, town, date_val, info, make_id)   # CHANGED
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

    # --- GardenRoute ---
    soup = fetch("https://gardenroute.com/events/")
    if soup:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/event" in href:
                parent = a.find_parent(["article", "div", "li"])
                ctx = parent.get_text(" ", strip=True) if parent else a.get_text(" ", strip=True)
                d = find_date_in_text(ctx)
                add_event(events, a.get_text(), guess_town(ctx + href), d, href if href.startswith("http") else "https://gardenroute.com" + href, source="gardenroute")

    # --- TooDoo ---
    soup = fetch("https://toodoo.co.za/events/")
    if soup:
        for card in soup.find_all(["article","div"], class_=re.compile("event|card|post", re.I)):
            h = card.find(["h2","h3","h4"])
            a = card.find("a", href=True)
            if not h or not a: continue
            link = a["href"] if a["href"].startswith("http") else "https://toodoo.co.za" + a["href"]
            d = ""
            time_el = card.find("time")
            if time_el and time_el.get("datetime"):
                d = time_el["datetime"]
            if not d:
                date_el = card.find(class_=re.compile("date|time|when|meta", re.I))
                if date_el:
                    d = find_date_in_text(date_el.get_text(" ", strip=True))
            if not d:
                d = find_date_in_text(card.get_text(" ", strip=True))
            add_event(events, h.get_text(), guess_town(card.get_text()), d, link, source="toodoo")

    # --- OnTheRoute ---
    for url in ["https://ontheroute.co.za/", "https://ontheroute.co.za/garden-route-market-guide/"]:
        soup = fetch(url)
        if not soup: continue
        for h in soup.find_all(["h2","h3"]):
            title = h.get_text()
            nxt = h.find_next_sibling()
            txt = (nxt.get_text() if nxt else "") + "\n" + title
            m = DATE_RE.search(txt)
            add_event(events, title, guess_town(txt), m.group(1).strip() if m else "", url, source="ontheroute")

    # --- Markets (recurring) ---
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
        add_event(events, title, town, date, "https://ontheroute.co.za/garden-route-market-guide/", source="market")

    # --- George Herald Eyes on Arts ---
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
                    add_event(events, title, guess_town(text[m.start():m.start()+500]), m.group(1).strip(), link, source="georgeherald")
                break

    result = list(events)
    if _FETCH_FAILED:
        print("Some sites failed - not caching, so the next caller retries.")
    else:
        _save_cache(result)
    return result
