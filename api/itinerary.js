// api/itinerary.js - VERCEL API HANDLER - Paste OVER current file
let _events = null;
let _restaurants = null;

async function loadData() {
  if (_events && _restaurants) return { events: _events, restaurants: _restaurants };
  try {
    const base = process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : '';
    const [eRes, rRes] = await Promise.all([
      fetch(`${base}/data/events.json`),
      fetch(`${base}/data/restaurants.json`)
    ]);
    const eJson = await eRes.json();
    const rJson = await rRes.json();
    _events = eJson.events || eJson;
    _restaurants = rJson.restaurants || rJson;
  } catch (err) {
    _events = [];
    _restaurants = [];
  }
  return { events: _events, restaurants: _restaurants };
}

function tagVibe(item) {
  const text = `${item.title || item.name || ''} ${item.description || ''} ${item.category || ''} ${item.cuisine || ''}`.toLowerCase();
  const vibes = [];
  if (/market|food|wine|braai|farm/.test(text)) vibes.push('foodie');
  if (/music|concert|live|dj|jazz/.test(text)) vibes.push('music');
  if (/kids|family|easter|school/.test(text)) vibes.push('family');
  if (/hike|trail|surf|adventure|run|bike/.test(text)) vibes.push('adventure');
  if (/art|gallery|theatre|book|poetry/.test(text)) vibes.push('culture');
  if (/romantic|sunset|wine|couple/.test(text)) vibes.push('romantic');
  if (/free/.test(text) || item.price === 0 || item.price === 'Free') vibes.push('free');
  return vibes.length ? vibes : ['general'];
}
function scoreItem(item, query) {
  let score = 0;
  const q = (query || '').toLowerCase();
  const text = `${item.title || item.name || ''} ${item.description || ''} ${item.town || ''} ${item.cuisine || ''}`.toLowerCase();
  const vibes = tagVibe(item);
  if (vibes.some(v => q.includes(v))) score += 50;
  q.split(' ').forEach(word => { if (word.length > 3 && text.includes(word)) score += 10; });
  if (item.date) score += 20;
  return score;
}
function recommend(allItems, query, limit = 12) {
  return allItems.map(item => ({ ...item, vibes: tagVibe(item), score: scoreItem(item, query) }))
    .filter(i => i.score > 0).sort((a,b) => b.score - a.score).slice(0, limit);
}
function explain(item, query) {
  if (item.vibes.includes('free')) return `Free and matches "${query}" - good for a budget day in ${item.town}.`;
  if (item.vibes.includes('family')) return `Family-friendly in ${item.town} - fits "${query}".`;
  return `Matches "${query}" in ${item.town} - ${item.vibes.join(', ')}.`;
}
function inTown(item, town) {
  if (!town) return true;
  return (item.town || '').toLowerCase().includes(town.toLowerCase());
}

export default async function handler(req, res) {
  try {
    const town = req.query.town || 'Knysna';
    const query = req.query.query || req.query.q || 'family';
    const days = parseInt(req.query.days || '2');

    const { events, restaurants } = await loadData();

    const topEvents = recommend(events.filter(e => inTown(e, town)), query, 10);
    const topRestaurants = recommend(
      restaurants.filter(r => inTown(r, town)).map(r => ({ ...r, title: r.name, description: `${r.cuisine || ''} ${r.description || ''}` })),
      query, 10
    );

    const plan = [];
    for (let d = 1; d <= days; d++) {
      const morningEvent = topEvents[(d - 1) * 2];
      const afternoonEvent = topEvents[(d - 1) * 2 + 1];
      const lunch = topRestaurants[d - 1];
      const dinner = topRestaurants[d + 1];
      plan.push({
        day: d,
        title: `Day ${d} in ${town} - ${query}`,
        morning: morningEvent ? { ...morningEvent, why: explain(morningEvent, query) } : null,
        lunch: lunch ? { ...lunch, why: explain(lunch, query) } : null,
        afternoon: afternoonEvent ? { ...afternoonEvent, why: explain(afternoonEvent, query) } : null,
        dinner: dinner ? { ...dinner, why: explain(dinner, query) } : null,
      });
    }

    res.status(200).json({
      query, town, days, plan,
      summary: `A ${days}-day ${query} plan for ${town} - ${topEvents.length} events + ${topRestaurants.length} restaurants matched.`
    });
  } catch (e) {
    res.status(500).json({ error: 'Itinerary failed', detail: String(e) });
  }
}