import fs from 'fs';
import path from 'path';

function parseDate(d) {
  if (!d) return null;
  // "2026-11-14" -> Date. Also handles "2026-11-14T..." and "14 Nov 2026" as fallback
  const iso = new Date(d);
  if (!isNaN(iso)) return iso;
  return null;
}

function getWeekendRange() {
  const now = new Date();
  // Saturday = 6, Sunday = 0 in JS. Find next Saturday, then Sunday after it.
  const day = now.getDay();
  const toSat = (6 - day + 7) % 7;
  const sat = new Date(now);
  sat.setHours(0, 0, 0, 0);
  sat.setDate(sat.getDate() + toSat);
  const sun = new Date(sat);
  sun.setDate(sun.getDate() + 1);
  sun.setHours(23, 59, 59, 999);
  return { sat, sun };
}

export default function handler(req, res) {
  try {
    const q = (req.query.q || "").toLowerCase().trim();
    const town = (req.query.town || "").toLowerCase().trim();
    const weekend = req.query.weekend === "1" || req.query.weekend === "true";
    const from = req.query.from ? parseDate(req.query.from) : null;
    const to = req.query.to ? parseDate(req.query.to) : null;
    const limit = Math.min(parseInt(req.query.limit || "100", 10) || 100, 500);

    const file = path.join(process.cwd(), 'data', 'events.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    let events = data.events || [];

    // 1. Text search - title + town
    if (q) {
      events = events.filter(e =>
        (e.title || "").toLowerCase().includes(q) ||
        (e.town || "").toLowerCase().includes(q)
      );
    }

    // 2. Town filter - "plett" matches "Plettenberg Bay"
    if (town && town !== "all" && town !== "garden route") {
      events = events.filter(e => {
        const t = (e.town || "").toLowerCase();
        if (t.includes(town)) return true;
        // alias
        if (town === "plett" && t.includes("plettenberg")) return true;
        return false;
      });
    }

    // 3. Weekend filter - uses ISO dates from new sources.py
    let weekendRange = null;
    if (weekend) {
      weekendRange = getWeekendRange();
    }

    events = events.filter(e => {
      const d = parseDate(e.date);
      // If no parseable date, keep it ONLY if not filtering by date
      // (so "See link for date" events still show in All, but not in Weekend)
      if (!d) {
        return !weekend && !from && !to;
      }
      if (weekendRange && (d < weekendRange.sat || d > weekendRange.sun)) return false;
      if (from && d < from) return false;
      if (to && d > to) return false;
      return true;
    });

    // 4. Sort: dated first (soonest first), undated last
    events.sort((a, b) => {
      const da = parseDate(a.date);
      const db = parseDate(b.date);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      return da - db;
    });

    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=60');
    res.json({
      q,
      town: req.query.town || "",
      weekend,
      total: events.length,
      events: events.slice(0, limit),
      last_updated: data.last_updated || null
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Could not load events.json", detail: String(err).slice(0, 200) });
  }
}