import fs from 'fs';
import path from 'path';

export default function handler(req, res) {
  const town = req.query.town || "Sedgefield";
  const file = path.join(process.cwd(), 'data', 'events.json');
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  const events = data.events.filter(e => e.town === town);
  res.json({ town, total: events.length, events });
}