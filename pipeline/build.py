import json, sys, traceback
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scrapers"))

import events_george, events_knysna, events_plett, events_sedgefield
import restaurants as restaurants_scraper
import common

SCRAPERS = {
    "george": events_george.scrape,
    "knysna": events_knysna.scrape,
    "plett": events_plett.scrape,
    "sedgefield": events_sedgefield.scrape,
}

def validate_event(e):
    return all(e.get(f) for f in ["id", "title", "town", "date", "source"])

def main():
    now = datetime.now(timezone.utc).isoformat()
    all_events = []
    health = {}
    seen = set()

    for name, fn in SCRAPERS.items():
        try:
            cleaned = []
            for e in fn():
                e["town"] = common.normalise_town(e.get("town", name))
                e["date"] = common.clean_date(e.get("date"))
                if not e.get("id"):
                    e["id"] = common.make_id(e.get("title",""), e.get("date",""), e["town"])
                e["scraped_at"] = now
                e["source"] = e.get("source", name)
                if validate_event(e) and e["id"] not in seen:
                    seen.add(e["id"])
                    cleaned.append(e)
            health[name] = {"status": "ok", "count": len(cleaned)}
            all_events.extend(cleaned)
        except Exception as ex:
            health[name] = {"status": "failed", "error": str(ex)}
            traceback.print_exc()

    try:
        restaurants = restaurants_scraper.scrape()
        for r in restaurants:
            r["town"] = common.normalise_town(r.get("town"))
            if not r.get("id"):
                r["id"] = common.make_id(r.get("name",""), "", r["town"])
            r["scraped_at"] = now
        health["restaurants"] = {"status": "ok", "count": len(restaurants)}
    except Exception as ex:
        health["restaurants"] = {"status": "failed", "error": str(ex)}
        restaurants = []

    if len(all_events) == 0:
        print("ERROR: 0 events, keeping old file")
        sys.exit(1)

    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "events.json").write_text(json.dumps({
        "meta": {"last_updated": now, "total_events": len(all_events)},
        "events": all_events
    }, indent=2))
    (ROOT / "data" / "restaurants.json").write_text(json.dumps({
        "meta": {"last_updated": now, "total_restaurants": len(restaurants)},
        "restaurants": restaurants
    }, indent=2))
    (ROOT / "data" / "meta.json").write_text(json.dumps({
        "last_updated": now,
        "total_events": len(all_events),
        "total_restaurants": len(restaurants),
        "sources": health
    }, indent=2))
    print(f"DONE: {len(all_events)} events")

if __name__ == "__main__":
    main()