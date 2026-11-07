import fs from 'fs';
import path from 'path';

function parseDate(d) {
  if (!d) return null;
  const dt = new Date(d);
  return isNaN(dt) ? null : dt;
}

function getWeekendRange() {
  const now = new Date();
  const day = now.getDay(); // 0=Sun, 6=Sat
  const toSat = (6 - day + 7) % 7;
  const sat = new Date(now);
  sat.setHours(0, 0, 0, 0);
  sat.setDate(sat.getDate() + toSat);
  const sun = new Date(sat);
  sun.setDate(sun.getDate() + 1);
  sun.setHours(23, 59, 59, 999);
  return { sat, sun };
}

function normaliseTown(t) {
  const low = (t || "").toLowerCase().trim();
  if (low === "plett" || low.includes("plettenberg")) return "plettenberg bay";
  if (low === "great brak" || low.includes("great brak")) return "great brak river";
  if (low === "little brak" || low.includes("little brak")) return "little brak river";
  return low;
}

export default function handler(req, res) {
  try {
    const townRaw = req.query.town || "Sedgefield";
    const town = normaliseTown(townRaw);
    const weekend = req.query.weekend === "1" || req.query.weekend === "true";
    const dateQ = req.query.date ? parseDate(req.query.date) : null;
    const limit = Math.min(parseInt(req.query.limit || "10", 10) || 10, 30);

    const file = path.join(process.cwd(), 'data', 'events.json');
    const data = JSON.parse(fs.readFileSync(file, 'utf8'));
    let events = data.events || [];

    // 1. Town - case-insensitive + plett alias, fallback to Garden Route if none
    let townEvents = events.filter(e =>
      (e.town || "").toLowerCase().includes(town)
    );
    // If town has < 3 events, fill with nearby Garden Route events so itinerary isn't empty
    if (townEvents.length < 3) {
      const rest = events.filter(e => !(e.town || "").toLowerCase().includes(town));
      townEvents = [...townEvents, ...rest];
    }

    // 2. Date / Weekend filter
    let range = null;
    if (weekend) range = getWeekendRange();
    if (weekend || dateQ) {
      townEvents = townEvents.filter(e => {
        const d = parseDate(e.date);
        if (!d) return false; // itinerary needs a real date, undated can't be planned
        if (range && (d < range.sat || d > range.sun)) return false;
        if (dateQ) {
          // same calendar day
          return d.toDateString() === dateQ.toDateString();
        }
        return true;
      });
    }

    // 3. Sort: soonest first, undated last
    townEvents.sort((a, b) => {
      const da = parseDate(a.date);
      const db = parseDate(b.date);
      if (!da && !db) return 0;
      if (!da) return 1;
      if (!db) return -1;
      return da - db;
    });

    // 4. Build a simple morning / afternoon / evening plan
    const picked = townEvents.slice(0, limit);
    const plan = picked.map((e, i) => ({
      order: i + 1,
      slot: i === 0 ? "Morning" : i === 1 ? "Midday" : i === 2 ? "Afternoon" : "Evening",
      title: e.title,
      town: e.town,
      date: e.date,
      link: e.link || null
    }));

    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate=60');
    res.json({
      town: townRaw,
      weekend,
      date: req.query.date || null,
      total: townEvents.length,
      events: picked,
      plan,
      last_updated: data.last_updated || null
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "Could not load events.json", detail: String(err).slice(0, 200) });
  }
}