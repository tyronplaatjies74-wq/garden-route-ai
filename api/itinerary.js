// api/itinerary.js - FIXED FOR VERCEL - Brain inside, uses fetch() not import
// Paste OVER your current api/itinerary.js

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

// ============ BRAIN (same as in search.js) ============
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

function inTown(item, town) {
  if (!town) return true