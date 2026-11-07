import hashlib
from datetime import datetime

def normalise_town(raw):
    t = (raw or "").strip().lower()
    mapping = {
        "sedgefield": "Sedgefield",
        "knysna": "Knysna",
        "plett": "Plettenberg Bay",
        "plettenberg bay": "Plettenberg Bay",
        "george": "George",
    }
    return mapping.get(t, (raw or "").strip().title())

def make_id(title, date, town):
    key = f"{title}|{date}|{town}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:12]

def clean_date(raw):
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).isoformat()
    except Exception:
        return None