import hashlib
import re
from datetime import datetime

# Towns that have an alias / short form
_MAPPING = {
    "sedgefield": "Sedgefield",
    "knysna": "Knysna",
    "plett": "Plettenberg Bay",
    "plettenberg bay": "Plettenberg Bay",
    "plettenberg": "Plettenberg Bay",
    "george": "George",
    "mossel bay": "Mossel Bay",
    "wilderness": "Wilderness",
    "oudtshoorn": "Oudtshoorn",
    "hartenbos": "Hartenbos",
    "great brak river": "Great Brak River",
    "little brak river": "Little Brak River",
    "tsitsikamma": "Tsitsikamma",
    "natures valley": "Natures Valley",
    "stilbaai": "Stilbaai",
    "riversdale": "Riversdale",
    "heidelberg": "Heidelberg",
    "garden route": "Garden Route",
}

# Generic Garden Route listings have no specific town.
# They fall back to this hub so they aren't lost.
# Change this if you'd rather they live under a different town.
FALLBACK_HUB = "George"

def normalise_town(raw):
    """'George, Western Cape' -> 'George', 'plett' -> 'Plettenberg Bay'."""
    if not raw:
        return "Garden Route"
    t = str(raw).strip().lower()
    # Strip suffixes: "George, Western Cape" / "Knysna - Garden Route"
    t = re.split(r"[,;|-]", t)[0].strip()
    # "garden route" anywhere in the remainder means generic
    if "garden route" in t or not t:
        return "Garden Route"
    if t in _MAPPING:
        return _MAPPING[t]
    return t.title()

def matches_town(event_town, wanted):
    """Does this event belong to this town scraper?"""
    event_norm = normalise_town(event_town)
    wanted_norm = normalise_town(wanted)
    if event_norm == wanted_norm:
        return True
    # Generic listings go to the hub instead of vanishing
    if event_norm == "Garden Route" and wanted_norm == FALLBACK_HUB:
        return True
    return False

def make_id(title, date, town):
    # Kept for compatibility with sources.py.
    # build.py overwrites this with its own SHA1 id.
    key = f"{title}|{date}|{town}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:12]

def clean_date(raw):
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).isoformat()
    except Exception:
        return None