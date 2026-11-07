import requests, re
from bs4 import BeautifulSoup
from scrapers.common import normalise_town, make_id, clean_date

HEADERS = {"User-Agent": "Mozilla/5.0 GardenRouteAI-Bot/1.0"}
TOWNS = ["George","Knysna","Plettenberg Bay","Plett","Mossel Bay","Sedgefield","Wilderness","Oudtshoorn","Hartenbos","Great Brak River","Little Brak River","Tsitsikamma","Nature's Valley","Stilbaai","Riversdale","Heidelberg"]

def guess_town(text):
    text = (text or "").lower()
    for t in TOWNS:
        if t.lower() in text:
            return "Plettenberg Bay" if t == "Plett" else t
    return "Garden Route"

def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()

def add_event(events, title, town, date, link):
    title = clean(title)
    if len(title) < 3 or len(title) > 120:
        return
    if any(x in title.lower() for x in ["cookie","privacy","subscribe","advertisement","menu","login"]):
        return
    town = normalise_town(town)
    key = (title.lower(), town.lower())
    if key in [(e["title"].lower(), e["town"].lower()) for e in events]:
        return
    iso_date = clean_date(date) if date else None
    events.append({
        "id": make_id(title, date, town),
        "title": title,
        "town": town,
        "date": iso_date or clean(date) or "See link for date",
        "link": link,
        "source": town.lower()
    })

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"FAIL {url}: {e}")
        return None

def scrape_all():
    events = []
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
            txt = (nxt.get_text() if nxt else "") + " " + title
            m = re.search(r"Date:\s*([^\n\-]+)", txt, re.I)
            add_event(events, title, guess_town(txt), m.group(1).strip() if m else "", url)
    markets = [
        ("Wild Oats Community Farmers' Market", "Sedgefield", "Every Saturday 07:30-12:00"),
        ("Outeniqua Family Market", "George", "Every Saturday 08:00-14:00"),
        ("Mosaic Village Market", "Sedgefield", "Every Saturday 08:00-14:00"),
        ("Scarab Village Craft