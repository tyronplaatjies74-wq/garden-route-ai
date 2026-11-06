# scrape_restaurants.py
# Garden Route AI - Restaurants Scraper
# Fixed: include way + relation (buildings), not just nodes
# Output: data/restaurants.json

import requests
import json
import time
from pathlib import Path

TOWNS = {
    "Knysna": (-34.0364, 23.0472, 8000),
    "George": (-33.9640, 22.4617, 9000),
    "Plettenberg Bay": (-34.0570, 23.3645, 8000),
    "Wilderness": (-33.9940, 22.5770, 6000),
    "Sedgefield": (-34.0260, 22.7890, 6000),
    "Mossel Bay": (-34.1830, 22.1460, 9000),
    "Oudtshoorn": (-33.5900, 22.2010, 7000),
    "Buffalo Bay": (-34.0830, 22.9830, 4000),
    "Herolds Bay": (-34.0530, 22.3830, 4000),
    "Victoria Bay": (-34.0000, 22.5500, 3000),
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "GardenRouteAI/1.0 (contact: gardenroute.ai)"}

def fetch_town(town, lat, lon, radius):
    # nwr = node + way + relation - THIS IS THE FIX
    query = f"""
    [out:json][timeout:60];
    (
      nwr["amenity"="restaurant"](around:{radius},{lat},{lon});
      nwr["amenity"="cafe"](around:{radius},{lat},{lon});
      nwr["amenity"="fast_food"](around:{radius},{lat},{lon});
      nwr["amenity"="biergarten"](around:{radius},{lat},{lon});
    );
    out center;
    """
    for attempt in range(3):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=60)
            if r.status_code == 429:
                print(f"  Rate limited {town}, waiting 10s...")
                time.sleep(10)
                continue
            r.raise_for_status()
            data = r.json()
            results = []
            for el in data.get("elements", []):
                tags = el.get("tags", {})
                name = tags.get("name")
                if not name:
                    continue
                cuisine = tags.get("cuisine", "")
                if cuisine:
                    cuisine = ", ".join([c.strip().capitalize() for c in cuisine.replace("_", " ").split(";")])
                address = tags.get("addr:full") or tags.get("addr:street", "")
                phone = tags.get("phone", "") or tags.get("contact:phone", "")
                website = tags.get("website", "") or tags.get("contact:website", "")
                opening = tags.get("opening_hours", "")
                # way/relation use center, node uses lat/lon
                center = el.get("center", {})
                el_lat = el.get("lat") or center.get("lat")
                el_lon = el.get("lon") or center.get("lon")
                gmaps = f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(name + ' ' + town + ' Garden Route')}"
                results.append({
                    "name": name,
                    "town": town,
                    "cuisine": cuisine or "Restaurant",
                    "type": tags.get("amenity", "restaurant"),
                    "address": address,
                    "phone": phone,
                    "website": website,
                    "opening_hours": opening,
                    "lat": el_lat,
                    "lon": el_lon,
                    "link": gmaps,
                    "source": "OpenStreetMap"
                })
            return results
        except Exception as e:
            print(f"Error {town} attempt {attempt+1}: {e}")
            time.sleep(5)
    return []

def main():
    all_restaurants = []
    seen = set()
    for town, (lat, lon, radius) in TOWNS.items():
        print(f"Fetching {town}...")
        items = fetch_town(town, lat, lon, radius)
        for item in items:
            key = (item["name"].lower().strip(), item["town"].lower())
            if key in seen:
                continue
            seen.add(key)
            all_restaurants.append(item)
        print(f"  -> {len(items)} found")
        time.sleep(2)

    # SAFETY: Don't overwrite good data with 0
    if len(all_restaurants) == 0:
        print("WARNING: Found 0 restaurants - NOT overwriting file. Keeping old data.")
        return

    all_restaurants.sort(key=lambda x: (x["town"], x["name"]))
    Path("data").mkdir(exist_ok=True)
    out = {
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S+02:00"),
        "count": len(all_restaurants),
        "restaurants": all_restaurants
    }
    with open("data/restaurants.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nDONE: {len(all_restaurants)} restaurants saved to data/restaurants.json")

if __name__ == "__main__":
    main()