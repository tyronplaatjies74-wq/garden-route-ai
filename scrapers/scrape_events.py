import requests, json, re, os
from bs4 import BeautifulSoup
from datetime import datetime

HEADERS = {"User-Agent": "Mozilla/5.0 GardenRouteAI-Bot/1.0"}
TOWNS = ["George","Knysna","Plettenberg Bay","Plett","Mossel Bay","Sedgefield","Wilderness","Oudtshoorn","Hartenbos","Great Brak River","Little Brak River","Tsitsikamma","Nature's Valley","Stilbaai","Riversdale","Heidelberg"]

def guess_town(text):
    text = text.lower()
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
    key = (title.lower(), town.lower())
    if key in [(e["title"].lower(), e["town"].lower()) for e in events]:
        return
    events.append({
        "title": title,
        "town": town,
        "date": clean(date) or "See link for date",
        "link": link
    })

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"FAIL {url}: {e}")
        return None

# --- SOURCE 1: Your original source ---
def scrape_source_1(events):
    print("Scraping source 1...")
    soup = fetch("https://gardenroute.com/events/")
    if not soup: return
    for a in soup.find_all("a", href=True):
        title = a.get_text()
        href = a["href"]
        if "/event" in href or "/events" in href:
            add_event(events, title, guess_town(title + href), "", href if href.startswith("http") else "https://gardenroute.com" + href)

# --- SOURCE 2: Toodoo ---
def scrape_toodoo(events):
    print("Scraping toodoo...")
    soup = fetch("https://toodoo.co.za/events/")
    if not soup: return
    for card in soup.find_all(["article","div"], class_=re.compile("event|card|post", re.I)):
        h = card.find(["h2","h3","h4"])
        a = card.find("a", href=True)
        if not h or not a: continue
        title = h.get_text()
        town_el = card.find(string=re.compile("TOWN:", re.I))
        town = guess_town(card.get_text())
        date_el = card.find(string=re.compile(r"\d{1,2} \w+ 202\d|When:", re.I))
        date = date_el.strip() if date_el else ""
        link = a["href"] if a["href"].startswith("http") else "https://toodoo.co.za" + a["href"]
        add_event(events, title, town, date, link)
    # Fallback: all links
    if len(events) < 5:
        for a in soup.find_all("a", href=True):
            if "/event" in a["href"]:
                add_event(events, a.get_text(), guess_town(a.get_text()), "", a["href"] if a["href"].startswith("http") else "https://toodoo.co.za" + a["href"])

# --- SOURCE 3: On The Route - Events + Markets ---
def scrape_ontheroute(events):
    print("Scraping ontheroute...")
    for url in ["https://ontheroute.co.za/", "https://ontheroute.co.za/garden-route-market-guide/"]:
        soup = fetch(url)
        if not soup: continue
        # Headings are events: ### Chicago, ### Indigenous Plant Fair etc.
        for h in soup.find_all(["h2","h3"]):
            title = h.get_text()
            # Next sibling has Date: and Venue:
            nxt = h.find_next_sibling()
            txt = (nxt.get_text() if nxt else "") + " " + title
            town = guess_town(txt)
            m = re.search(r"Date:\s*([^\n\-]+)", txt, re.I)
            date = m.group(1).strip() if m else ""
            add_event(events, title, town, date, url)
    # Hardcoded weekly markets - these never change, fixes your Markets filter forever
    markets = [
        ("Wild Oats Community Farmers' Market", "Sedgefield", "Every Saturday 07:30-12:00"),
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

# --- SOURCE 4: George Herald - Eyes on Arts ---
def scrape_herald(events):
    print("Scraping George Herald...")
    soup = fetch("https://georgeherald.com/search/?q=Eyes+on+arts")
    if not soup:
        soup = fetch("https://georgeherald.com/")
    if not soup: return
    for a in soup.find_all("a", href=True):
        if "eyes-on-arts" in a["href"].lower():
            link = a["href"] if a["href"].startswith("http") else "https://georgeherald.com" + a["href"]
            sub = fetch(link)
            if not sub: continue
            text = sub.get_text()
            # Pattern: "> 28 Oct-7 Nov | Chicago: The Musical" or "28 Oct | Title"
            for m in re.finditer(r"(\d{1,2}(?:-\d{1,2})?\s*(?:October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\n|]{0,5}\|?\s*)([A-Z][^\n]{5,90})", text):
                date = m.group(1).strip()
                title = m.group(2).strip().split(" at ")[0].split(" - ")[0]
                add_event(events, title, guess_town(text[m.start():m.start()+500]), date, link)
            break

def main():
    events = []
    scrape_source_1(events)
    scrape_toodoo(events)
    scrape_ontheroute(events)
    scrape_herald(events)

    print(f"TOTAL: {len(events)} events")
    os.makedirs("data", exist_ok=True)
    with open("data/events.json", "w", encoding="utf-8") as f:
        json.dump({
            "last_updated": datetime.now().strftime("%d/%m/%Y, %H:%M:%S"),
            "count": len(events),
            "events": sorted(events, key=lambda x: x["title"])
        }, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()