from scrapers.sources import scrape_all
def scrape():
    return [e for e in scrape_all() if e["town"] == "Knysna"]