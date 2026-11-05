# scrapers/scrape_events.py - Garden Route AI - Events Scraper
import requests, json, re, os
from datetime import datetime
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "GardenRouteAI/1.0"}
EVENTS = []

def clean(text):
    return re.sub(r'\s+', ' ', text or '').strip()

def add_event(title, town, date_text, venue, description, source, url):
    if not title: return
    EVENTS.append({
        "title": clean(title),
        "town": clean(town) or "Garden Route",
        "date_text": clean(date_text),
        "venue": clean(venue),
        "description": clean(description)[:600],
        "source": source,
        "url": url,
        "scraped_at": datetime.now().isoformat()
    })

def scrape_gardenroute():
    try:
        urls = ["https://gardenroute.com/events/", "https://gardenroute.com/event/"]
        found_links = set()
        for list_url in urls:
            r = requests.get(list_url, headers=HEADERS, timeout=20)
            if r.status_code != 200: continue
            soup = BeautifulSoup(r.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'gardenroute.com' in href and len(href) > 30:
                    if href.startswith('/'):
                        href = 'https://gardenroute.com' + href
                    found_links.add(href)
            if len(found_links) > 60: break
        print(f"gardenroute.com: found {len(found_links)} links")
        for url in list(found_links)[:40]:
            try:
                r = requests.get(url, headers=HEADERS, timeout=15)
                if r.status_code != 200: continue
                s = BeautifulSoup(r.text, 'html.parser')
                h1 = s.find('h1')
                title = h1.get_text() if h1 else ''
                if not title or len(title) < 3: continue
                text = s.get_text()
                town = "Garden Route"
                for t in ["Knysna","Plettenberg Bay","Plett","George","Wilderness","Mossel Bay","Oudtshoorn","Sedgefield","Buffalo Bay","Great Brak River"]:
                    if t.lower() in text.lower() or t.lower() in title.lower():
                        town = t; break
                desc = s.find('meta', attrs={'name':'description'})
                desc = desc['content'] if desc else ''
                m = re.search(r'(\d{1,2}\s(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{4})', text)
                date_text = m.group(0) if m else "See event page for date"
                add_event(title, town, date_text, "", desc or text[:500], "gardenroute.com", url)
            except: continue
    except Exception as e:
        print(f"gardenroute error: {e}")

def scrape_ontheroute():
    try:
        r = requests.get("https://ontheroute.co.za/", headers=HEADERS, timeout=20)
        soup = BeautifulSoup(r.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            if 'event-guide' in a['href'].lower():
                guide_url = a['href']
                if guide_url.startswith('/'):
                    guide_url = 'https://ontheroute.co.za' + guide_url
                gr = requests.get(guide_url, headers=HEADERS, timeout=20)
                gs = BeautifulSoup(gr.text, 'html.parser')
                for h in gs.find_all(['h2','h3']):
                    title = clean(h.get_text())
                    if len(title) < 4 or title.lower() in ['mossel bay','george','knysna','plett','wilderness']: continue
                    nxt = h.find_next('p')
                    desc = nxt.get_text() if nxt else ""
                    add_event(title, "Garden Route", "Check guide for date", "", desc, "ontheroute.co.za", guide_url)
                break
    except Exception as e:
        print(f"ontheroute error: {e}")

if __name__ == "__main__":
    scrape_gardenroute()
    scrape_ontheroute()
    seen = set(); unique = []
    for e in EVENTS:
        k = e['title'].lower().strip()
        if k not in seen:
            seen.add(k); unique.append(e)
    os.makedirs('data', exist_ok=True)
    with open('data/events.json','w', encoding='utf-8') as f:
        json.dump({"last_updated": datetime.now().isoformat(), "count": len(unique), "events": unique}, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(unique)} events to data/events.json")