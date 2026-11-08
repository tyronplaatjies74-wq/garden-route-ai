"""Date parsing for the event scrapers.

parse_event_dates("14-16 November 2026") ->
    {"start": "2026-11-14", "end": "2026-11-16", "recurrence": None}
parse_event_dates("Every Saturday 07:30-12:00") ->
    {"start": <next Saturday>, "end": <same>, "recurrence": "weekly:saturday"}
parse_event_dates("3rd Saturday 09:00") ->
    the real 3rd Saturday of the month (not just "next Saturday")
Returns None when no date can be found.
"""
import re
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
          "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}
WD_NAMES = list(WEEKDAYS)
ORDINALS = {"1st": 1, "first": 1, "2nd": 2, "second": 2, "3rd": 3, "third": 3,
            "4th": 4, "fourth": 4, "last": -1}

MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
WD = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thur?s?|fri|sat|sun)"
ORD = r"(?:1st|2nd|3rd|4th|first|second|third|fourth|last)"
DASH = r"(?:-|to)"
STALE_DAYS = 60  # a date with no year that is older than this is assumed to be next year


def sa_today():
    """Today's date in South Africa (the GitHub runner clock is UTC)."""
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo("Africa/Johannesburg")).date()
        except Exception:
            pass
    return (datetime.utcnow() + timedelta(hours=2)).date()


def _to_date(now):
    if now is None:
        return sa_today()
    return now.date() if isinstance(now, datetime) else now


def _wd_index(word):
    w = word.lower()
    for name, idx in WEEKDAYS.items():
        if name.startswith(w[:3]):
            return idx
    return None


def _month(word):
    return MONTHS[word.lower()[:3]]


def _year(v):
    if v is None:
        return None
    y = int(v)
    return y if 2000 <= y <= 2100 else None


def _make(day, month, year, today):
    """Build a date. With no year, assume this year unless it is long past."""
    try:
        if year:
            return date(year, month, day)
        d = date(today.year, month, day)
        if d < today - timedelta(days=STALE_DAYS):
            d = date(today.year + 1, month, day)
        return d
    except ValueError:
        return None


def _nth_weekday(year, month, weekday, n):
    if n > 0:
        first = date(year, month, 1)
        d = first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
        return d if d.month == month else None
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _info(start, end=None, recurrence=None):
    end = end or start
    return {"start": start.isoformat(), "end": end.isoformat(), "recurrence": recurrence}


def parse_event_dates(raw, now=None):
    if not raw:
        return None
    today = _to_date(now)
    s = str(raw).strip()
    low = s.lower().replace("\u2013", "-").replace("\u2014", "-")

    # 1. ISO dates (single or "2026-11-14 to 2026-11-16")
    iso = re.findall(r"(\d{4})-(\d{2})-(\d{2})", s)
    if iso:
        try:
            ds = [date(int(a), int(b), int(c)) for a, b, c in iso]
            return _info(min(ds), max(ds))
        except ValueError:
            pass

    # 2. Weekly: "Every Saturday ..."
    m = re.search(rf"every\s+({WD})\b", low)
    if m:
        idx = _wd_index(m.group(1))
        d = today + timedelta(days=(idx - today.weekday()) % 7)
        return _info(d, recurrence="weekly:" + WD_NAMES[idx])

    # 3. Monthly: "3rd Saturday", "2nd and last Saturday"
    m = re.search(rf"({ORD}(?:\s*(?:,|and|&)\s*{ORD})*)\s+({WD})\b", low)
    if m:
        ns = [ORDINALS[t] for t in re.findall(ORD, m.group(1))]
        idx = _wd_index(m.group(2))
        best = None
        for add in range(0, 3):
            mo = today.month - 1 + add
            y, mth = today.year + mo // 12, mo % 12 + 1
            cands = [d for d in (_nth_weekday(y, mth, idx, n) for n in ns) if d and d >= today]
            if cands:
                best = min(cands)
                break
        if best:
            tag = "+".join(str(n) if n > 0 else "last" for n in ns)
            return _info(best, recurrence=f"monthly:{tag}:{WD_NAMES[idx]}")

    low = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", low)

    # 4a. "14-16 November 2026"
    m = re.search(rf"\b(\d{{1,2}})\s*{DASH}\s*(\d{{1,2}})\s+({MON})\b\.?,?\s*(\d{{4}})?", low)
    if m:
        mo, y = _month(m.group(3)), _year(m.group(4))
        a, b = _make(int(m.group(1)), mo, y, today), _make(int(m.group(2)), mo, y, today)
        if a and b:
            if b < a:
                b = _make(int(m.group(2)), mo, (a.year + 1), today) or b
            return _info(a, b)

    # 4b. "28 Nov - 2 Dec 2026"
    m = re.search(rf"\b(\d{{1,2}})\s+({MON})\b\.?,?\s*(\d{{4}})?\s*{DASH}\s*(\d{{1,2}})\s+({MON})\b\.?,?\s*(\d{{4}})?", low)
    if m:
        y1, y2 = _year(m.group(3)), _year(m.group(6))
        m1, m2 = _month(m.group(2)), _month(m.group(5))
        if y2 and not y1:
            y1 = y2 - (1 if m1 > m2 else 0)
        a = _make(int(m.group(1)), m1, y1, today)
        if a:
            b = _make(int(m.group(4)), m2, y2 or a.year, today)
            if b and b < a:
                b = _make(int(m.group(4)), m2, a.year + 1, today)
            if b:
                return _info(a, b)

    # 4c. "14 November 2026" / "14 Nov"
    m = re.search(rf"\b(\d{{1,2}})\s+({MON})\b\.?,?\s*(\d{{4}})?", low)
    if m:
        d = _make(int(m.group(1)), _month(m.group(2)), _year(m.group(3)), today)
        if d:
            return _info(d)

    # 4d. "November 14" / "Nov 14-16, 2026"
    m = re.search(rf"\b({MON})\b\.?\s+(\d{{1,2}})(?:\s*-\s*(\d{{1,2}}))?,?\s*(\d{{4}})?", low)
    if m:
        mo, y = _month(m.group(1)), _year(m.group(4))
        a = _make(int(m.group(2)), mo, y, today)
        b = _make(int(m.group(3)), mo, y, today) if m.group(3) else None
        if a:
            return _info(a, b if b and b >= a else a)

    # 5. "14/11/2026"
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", s)
    if m:
        try:
            return _info(date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    return None


def apply_dates(rec, title, town, date_val, info, make_id):
    """Write date fields onto an event record.
    Recurring events get a stable id, so it does not change every week."""
    rec["date"] = date_val
    if info:
        rec["start_date"] = info["start"]
        rec["end_date"] = info["end"]
        if info.get("recurrence"):
            rec["recurrence"] = info["recurrence"]
        else:
            rec.pop("recurrence", None)
    key = info["recurrence"] if info and info.get("recurrence") else date_val
    rec["id"] = make_id(title, key, town)
