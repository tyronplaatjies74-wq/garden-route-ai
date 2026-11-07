"""Garden Route AI data pipeline (v3) - EVENTS ONLY.
Restaurants are now a manual file: data/restaurants.json
This pipeline never touches it.
"""
import hashlib
import importlib
import json
import multiprocessing as mp
import os
import queue
import re
import shutil
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if HERE.name == "pipeline" else HERE
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
DATA = ROOT / "data"

EVENT_SOURCES = ["events_george", "events_sedgefield", "events_knysna", "events_plett"]
RESTAURANT_SOURCES = []  # REMOVED - restaurants are manual now

SCRAPER_TIMEOUT_S = 120
DROP_THRESHOLD = 0.5
MIN_OLD_FOR_DROP_CHECK = 6
EVENT_GRACE_DAYS = 7
UNDATED_TTL_DAYS = 30

ID_FIELDS = ("title", "name", "date", "date_text", "when", "time",
             "start_time", "town", "venue", "location")
LOOSE_FIELDS = ("title", "name", "town", "date", "date_text", "when")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def read_json_strict(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def load_with_backup(path):
    bak = path.with_name(path.name + ".bak")
    existed = False
    for candidate in (path, bak):
        if not candidate.exists():
            continue
        existed = True
        try:
            data = read_json_strict(candidate)
            if not isinstance(data, dict):
                raise ValueError("top level is not a JSON object")
            if candidate is bak:
                print(f"WARNING: {path.name} unreadable, restored from {bak.name}")
            return data
        except (ValueError, OSError) as e:
            print(f"WARNING: cannot read {candidate.name}: {e}")
    if existed:
        sys.exit(f"ABORT: {path.name} (and backup) are unreadable. Restore it from git history, then re-run.")
    return {}

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            read_json_strict(path)
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        except (json.JSONDecodeError, OSError):
            pass
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def make_id(item):
    key = "|".join(str(item.get(k, "")).strip().lower() for k in ID_FIELDS)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]

def loose_key(item):
    return "|".join(str(item.get(k, "")).strip().lower() for k in LOOSE_FIELDS)

def stamp(items, source):
    ts = now()
    out = []
    for it in items:
        if not isinstance(it, dict) or not (it.get("title") or it.get("name")):
            continue
        it = dict(it)
        it["source"] = source
        it["id"] = make_id(it)
        it["scraped_at"] = ts
        out.append(it)
    return out

def old_items_for(source, old_items):
    suffix = source.split("_", 1)[-1]
    out = []
    for i in old_items:
        s = i.get("source")
        if s == source:
            out.append(i)
        elif not s:
            if suffix in str(i.get("town", "")).lower():
                adopted = dict(i)
                adopted["source"] = source
                adopted.setdefault("id", make_id(adopted))
                out.append(adopted)
    return out

DATE_FORMATS = ["%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
                "%a, %d %b %Y", "%A, %d %B %Y", "%a %d %b %Y", "%d/%m/%Y", "%Y/%m/%d"]
RANGE_SPLIT = re.compile(r"\s+(?:-|–|—|to)\s+", re.I)

def _parse_one(s):
    s = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", s.strip(), flags=re.I)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

COMPACT_RANGE = re.compile(r"^(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s+([A-Za-z]+)\.?,?\s+(\d{4})$", re.I)

def _parse_span(raw):
    s = str(raw).strip()
    whole = _parse_one(s)
    if whole:
        return [whole]
    m = COMPACT_RANGE.match(s)
    if m:
        d1, d2, mon, yr = m.groups()
        return [d for d in (_parse_one(f"{d1} {mon} {yr}"), _parse_one(f"{d2} {mon} {yr}")) if d]
    parts = RANGE_SPLIT.split(s)
    year = re.search(r"\b(\d{4})\s*$", parts[-1])
    out = []
    for p in parts:
        d = _parse_one(p)
        if not d and year and not re.search(r"\d{4}", p):
            d = _parse_one(f"{p.strip()} {year.group(1)}")
        if d:
            out.append(d)
    return out

def date_range(item):
    for k in ("date", "date_text", "when"):
        raw = item.get(k)
        if not raw:
            continue
        found = _parse_span(raw)
        if found:
            return min(found), max(found)
    return None

def age_days(item):
    try:
        ts = datetime.fromisoformat(str(item.get("scraped_at")))
        return (datetime.now(timezone.utc) - ts).days
    except (TypeError, ValueError):
        return 0

def prune_events(events):
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=EVENT_GRACE_DAYS)
    kept = []
    for e in events:
        rng = date_range(e)
        if rng:
            if rng[1] >= cutoff:
                kept.append(e)
        elif age_days(e) <= UNDATED_TTL_DAYS:
            kept.append(e)
    return kept

def sort_events(events):
    def key(e):
        rng = date_range(e)
        return rng[0] if rng else date.max
    return sorted(events, key=key)

def _child(name, q):
    try:
        mod = importlib.import_module(f"scrapers.{name}")
        q.put(("ok", mod.scrape()))
    except BaseException:
        q.put(("err", traceback.format_exc()))

class ScraperError(Exception):
    pass

def scrape_isolated(name, timeout):
    methods = mp.get_all_start_methods()
    ctx = mp.get_context("fork" if "fork" in methods else "spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_child, args=(name, q), daemon=True)
    proc.start()
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                kind, payload = q.get(timeout=1)
                break
            except queue.Empty:
                if not proc.is_alive():
                    try:
                        kind, payload = q.get(timeout=1)
                        break
                    except queue.Empty:
                        raise ScraperError(f"process exited (code {proc.exitcode}) without a result")
                if time.monotonic() > deadline:
                    raise TimeoutError(f"timed out after {timeout}s (process killed)")
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
        else:
            proc.join(1)
        q.close()
        q.cancel_join_thread()
    if kind == "err":
        raise ScraperError(payload)
    return payload or []

def short_error(e):
    text = str(e).strip()
    return (text.splitlines()[-1] if text else type(e).__name__)[:200]

def run_sources(source_names, old_items, status):
    result = []
    for name in source_names:
        old = old_items_for(name, old_items)
        try:
            new = stamp(scrape_isolated(name, SCRAPER_TIMEOUT_S), name)
            if not new:
                raise ValueError("returned 0 items")
            if len(old) >= MIN_OLD_FOR_DROP_CHECK and len(new) < len(old) * DROP_THRESHOLD:
                new_keys = {loose_key(n) for n in new}
                old_unmatched = [o for o in old if loose_key(o) not in new_keys]
                result.extend(new + old_unmatched)
                status[name] = {"status": "suspicious", "count": len(new), "previous": len(old), "kept_old": len(old_unmatched)}
                print(f"SUSPICIOUS {name}: {len(new)} new vs {len(old)} before; merged with old")
            else:
                result.extend(new)
                status[name] = {"status": "ok", "count": len(new)}
        except Exception as e:
            print(f"FAILED {name}:\n{e if isinstance(e, ScraperError) else traceback.format_exc()}")
            result.extend(old)
            status[name] = {"status": "failed", "error": short_error(e), "kept_old": len(old)}
    return result

def dedupe(items):
    seen, out = set(), []
    for it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out

def main():
    def as_list(data, key):
        v = data.get(key, [])
        return [i for i in v if isinstance(i, dict)] if isinstance(v, list) else []

    old_events = as_list(load_with_backup(DATA / "events.json"), "events")
    for item in old_events:
        item.setdefault("scraped_at", now())
    status = {}

    events = dedupe(run_sources(EVENT_SOURCES, old_events, status))

    before = len(events)
    events = sort_events(prune_events(events))
    pruned = before - len(events)

    if not events:
        print("ABORT: no current events at all. Keeping existing files.")
        sys.exit(1)

    # Restaurants are manual - just count what's in the file, never overwrite it
    try:
        rest_data = load_with_backup(DATA / "restaurants.json")
        rest_count = len(as_list(rest_data, "restaurants"))
    except SystemExit:
        rest_count = 0

    ts = now()
    write_json(DATA / "events.json", {"last_updated": ts, "events": events})
    write_json(DATA / "meta.json", {
        "last_updated": ts,
        "events": len(events),
        "restaurants": rest_count,
        "pruned_expired": pruned,
        "sources": status,
    })

    problems = [n for n, s in status.items() if s["status"] != "ok"]
    print(f"Done: {len(events)} events ({pruned} expired), {rest_count} restaurants (manual)"
          + (f" | needs attention: {', '.join(problems)}" if problems else ""))

if __name__ == "__main__":
    main()