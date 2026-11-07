import json, os
from scrapers import events_george, events_sedgefield, events_knysna, events_plett, restaurants

os.makedirs("data", exist_ok=True)

events = []
for mod in [events_george, events_sedgefield, events_knysna, events_plett]:
    try:
        events.extend(mod.scrape())
    except Exception as e:
        print(f"FAILED {mod.__name__}: {e}")

try:
    rests = restaurants.scrape()
except Exception as e:
    print(f"FAILED restaurants: {e}")
    rests = []

with open("data/events.json", "w") as f:
    json.dump({"events": events}, f, indent=2)

with open("data/restaurants.json", "w") as f:
    json.dump({"restaurants": rests}, f, indent=2)

print(f"Done: {len(events)} events, {len(rests)} restaurants")