// api/search.js - FIXED FOR VERCEL - Brain inside, uses fetch() not import
// Paste OVER your current api/search.js

let _events = null;
let _restaurants = null;

async function loadData() {
  if (_events && _restaurants) return { events: _events, restaurants: _restaurants };
  try {
    const [eRes, rRes] = await Promise.all([
      fetch('/data/events.json'),
      fetch('/data/restaurants.json')
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

// ============ BRAIN ============
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
  const q = query.toLowerCase();
  const text = `${item.title || item.name || ''} ${item.description || ''} ${item.town || ''} ${item.cuisine || ''}`.toLowerCase();
  const vibes = tagVibe(item);
  if (vibes.some(v => q.includes(v))) score += 50;
  q.split(' ').forEach(word => {
    if (word.length > 3 && text.includes(word)) score += 10;
  });
  if (item.date) score += 20;
  if (item.link || item.url) score += 10;
  return score;
}
function recommend(allItems, query, limit = 12) {
  return allItems
    .map(item => ({ ...item, vibes: tagVibe(item), score: scoreItem(item, query) }))
    .filter(i => i.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit);
}
function explain(item, query) {
  if (item.vibes.includes('free')) return `Free and matches "${query}" - good for a budget day in ${item.town}.`;
  if (item.vibes.includes('family')) return `Family-friendly in ${item.town} - fits "${query}".`;
  return `Matches "${query}" in ${item.town} - ${item.vibes.join(', ')}.`;
}
// ============ BRAIN END ============

function isWeekend(dateStr) {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const day = d.getDay();
  return day === 0 || day === 6;
}
function isThisWeekend(dateStr) {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  const now = new Date();
  const sat = new Date(now);
  sat.setDate(now.getDate() + ((6 - now.getDay() + 7) % 7));
  sat.setHours(0,0,0,0);
  const sun = new Date(sat);
  sun.setDate(sat.getDate() + 1);
  sun.setHours(23,59,59,999);
  return d >= sat && d <= sun;
}

export async function search({ query = '', town = '', when = 'any', type = 'all' } = {}) {
  const { events, restaurants } = await loadData();
  const q = query.toLowerCase().trim();
  let eventResults = [...events];
  let restaurantResults = [...restaurants];

  if (town) {
    const t = town.toLowerCase();
    eventResults = eventResults.filter(e => (e.town || '').toLowerCase().includes(t));
    restaurantResults = restaurantResults.filter(r => (r.town || '').toLowerCase().includes(t));
  }
  if (when === 'weekend') eventResults = eventResults.filter(e => isWeekend(e.date));
  if (when === 'this-weekend') eventResults = eventResults.filter(e => isThisWeekend(e.date));

  if (q) {
    eventResults = recommend(eventResults, q, 12).map(item => ({ ...item, vibes: tagVibe(item), why: explain(item, q) }));
    restaurantResults = recommend(
      restaurantResults.map(r => ({ ...r, title: r.name, description: `${r.cuisine || ''} ${r.category || ''} ${r.description || ''}` })),
      q, 12
    ).map(item => ({ ...item, vibes: tagVibe(item), why: explain(item, q) }));
  } else {
    eventResults.sort((a,b) => new Date(a.date || '2100-01-01') - new Date(b.date || '2100-01-01'));
    eventResults = eventResults.slice(0,20).map(item => ({ ...item, vibes: tagVibe(item), why: `In ${item.town}${item.date ? ` on ${item.date}` : ''}` }));
    restaurantResults = restaurantResults.slice(0,20).map(item => ({ ...item, vibes: tagVibe(item), why: `In ${item.town}` }));
  }

  if (type === 'events') return { events: eventResults, restaurants: [] };
  if (type === 'restaurants') return { events: [], restaurants: restaurantResults };
  return { events: eventResults, restaurants: restaurantResults };
}

export async function searchEvents(query, town, when) {
  return (await search({ query, town, when, type: 'events' })).events;
}
export async function searchRestaurants(query, town) {
  return (await search({ query, town, type: 'restaurants' })).restaurants;
}
export default search;