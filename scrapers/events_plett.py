from scrapers.sources import scrape_all
from scrapers.common import matches_town

def scrape():
    return [
        e for e in scrape_all()
        if isinstance(e, dict) and matches_town(e.get("town"), "Plettenberg Bay")
    ]