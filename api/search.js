import fs from 'fs';
import path from 'path';

export default function handler(req, res) {
  const q = (req.query.q || "").toLowerCase();
  const file = path.join(process.cwd(), 'data', 'events.json');
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const events = data.events.filter(e => e.title.toLowerCase().includes(q));
  res.json({ q, total: events.length, events });
}