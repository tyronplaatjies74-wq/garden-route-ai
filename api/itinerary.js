// api/itinerary.js - PORT of planner.py v7.6 to JS (Option A)
// Walking clusters + Hub fallback + Season + Budget
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
    _events = eJson.events || eJson.data || eJson;
    _restaurants = rJson.restaurants || rJson.data || rJson;
    if (!Array.isArray(_events)) _events = [];
    if (!Array.isArray(_restaurants)) _restaurants = [];
  } catch { _events = []; _restaurants = []; }
  return { events: _events, restaurants: _restaurants };
}

// ============ CONFIG - from planner.py v7.6 ============
const FOOD_ALLOWANCE = 100;
const TAXI_R_PER_KM = 1.2;
const LOCAL_HOP_COST = 30;
const WALK_KM = 3.0;
const HOP_KM = 15.0;
const ROUTE_ORDER = ["mossel_bay", "george", "wilderness", "knysna", "plettenberg_bay", "tsitsikamma"];
const TOWN_ALIASES = { mossel: "mossel_bay", plett: "plettenberg_bay", plettenberg: "plettenberg_bay", brenton: "knysna", brenton_on_sea: "knysna", storms_river: "tsitsikamma", stormsriver: "tsitsikamma" };
const SEGMENTS = [[45, 50], [20, 15], [40, 50], [40, 35], [55, 70]]; // (mins, km) west->east
const HUBS = { mossel_bay: "george", george: "knysna", wilderness: "george", knysna: "plettenberg_bay", plettenberg_bay: "knysna", tsitsikamma: "plettenberg_bay" };
const SEASON_OF = { 12: "summer", 1: "summer", 2: "summer", 3: "autumn", 4: "autumn", 5: "autumn", 6: "winter", 7: "winter", 8: "winter", 9: "spring", 10: "spring", 11: "spring" };
const WHALE_MONTHS = new Set([6, 7, 8, 9, 10, 11]);
const WHALE_SPOTS = ["robberg", "st blaize", "point", "heads"];
const PRICE_MULT = { 12: 1.35, 1: 1.30, 2: 1.10, 4: 1.05 };
const SEASON_NOTES = {
  summer: "Warm and busy. Peak hostel prices around Dec-Jan: book early. Best beach/lagoon weather.",
  autumn: "Mild and quieter. Good hiking weather.",
  winter: "Cold with rain fronts and early dark (about 17:30). Beach days are down-ranked; markets and covered spots favoured. Whale season.",
  spring: "Warming up, often windy, sea still cold. Whale watching at its best."
};
const SEASON_WEIGHTS = { winter: { beach: -3, night: -2, indoor: 2 }, spring: { beach: -1 }, summer: { beach: 2 } };
const RAIN_OK = new Set(["indoor", "covered"]);
const MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const REST_NAME = "Free time - rest or explore on your own";

// ============ HELPERS ============
function display(key) { return key.replace(/_/g, " "); }
function resolveTown(name) {
  let key = String(name || "").trim().toLowerCase().replace(/[\s\-]+/g, "_");
  key = TOWN_ALIASES[key] || key;
  return ROUTE_ORDER.includes(key) ? key : null;
}
function getTown(item) { return String(item.town || item.location || item.area || item.city || "").toLowerCase(); }
function getTitle(item) { return item.title || item.name || item.event || "Unnamed"; }
function getDesc(item) { return item.description || item.details || item.about || item.cuisine || ""; }
function getCost(item) {
  if (typeof item.cost === "number") return item.cost;
  if (typeof item.price === "number") return item.price;
  if (String(item.price || "").toLowerCase().includes("free")) return 0;
  const n = parseInt(String(item.price || item.cost || "0").replace(/[^0-9]/g, ""));
  return isNaN(n) ? 0 : n;
}
function itemCoords(item) {
  if (item.coords) {
    try { const [a, b] = String(item.coords).split(","); return [parseFloat(a), parseFloat(b)]; } catch {}
  }
  if (item.lat && item.lng) return [parseFloat(item.lat), parseFloat(item.lng)];
  if (item.latitude && item.longitude) return [parseFloat(item.latitude), parseFloat(item.longitude)];
  return null;
}
function kmBetween(c1, c2) {
  if (!c1 || !c2) return null;
  const [la1, lo1, la2, lo2] = [c1[0], c1[1], c2[0], c2[1]].map(d => d * Math.PI / 180);
  const h = Math.sin((la2 - la1) / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin((lo2 - lo1) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(h));
}
function routeLeg(a, b) {
  const i = ROUTE_ORDER.indexOf(a), j = ROUTE_ORDER.indexOf(b);
  const [s, e] = [Math.min(i, j), Math.max(i, j)];
  let mins = 0, km = 0;
  for (let k = s; k < e; k++) { mins += SEGMENTS[k][0]; km += SEGMENTS[k][1]; }
  return [mins, km];
}
function fareFor(km) { return Math.max(LOCAL_HOP_COST, Math.round(km * TAXI_R_PER_KM / 5) * 5); }
function mapsLink(q) { return "https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(q); }
function fmtCost(c) { return c && c > 0 ? `R${c}` : "FREE"; }
function cleanName(n) { return String(n).replace(/\s*-\s*FREE\b/i, "").replace(/\s*-\s*torch\b/i, " (bring a torch)").trim(); }
function activityKind(item) {
  const n = getTitle(item).toLowerCase() + " " + getDesc(item).toLowerCase();
  if (/market|curry|wrap|soup|self-cook|restaurant|cafe|food/.test(n)) return "indoor";
  if (n.includes("hide")) return "covered";
  if (/stargaz|sunset/.test(n)) return "night";
  if (/beach|lagoon|kayak/.test(n)) return "beach";
  if (/hike|trail|walk|bridge|viewpoint|stroll|botanical|reserve|fynbos/.test(n)) return "hike";
  return "outdoor";
}
function seasonScore(item, ctx) {
  const kind = activityKind(item);
  let s = (SEASON_WEIGHTS[ctx.season] || {})[kind] || 0;
  if (ctx.rain && RAIN_OK.has(kind)) s += 4;
  if (ctx.month && WHALE_MONTHS.has(ctx.month) && WHALE_SPOTS.some(w => getTitle(item).toLowerCase().includes(w))) s += 3;
  return s;
}
function score(item, ctx, used, isMeal, km) {
  let s = 0;
  const styles = (item.styles || []).map(x => String(x).toLowerCase());
  if (styles.includes(ctx.style)) s += 3;
  if (ctx.style === "foodie" && item.food && item.food !== "any") s += 3;
  if (ctx.frugal && getCost(item) > 0) s -= 2;
  if (item.name && used.has(getTitle(item))) s -= 2;
  s += seasonScore(item, ctx);
  if (km !== null && km !== undefined) s += km <= WALK_KM ? 2 : -0.3 * (km - WALK_KM);
  s += ctx.rng() * (ctx.shuffle ? 5 : 0.01);
  // query boost
  const q = (ctx.query || "").toLowerCase();
  if (q) {
    const text = (getTitle(item) + " " + getDesc(item)).toLowerCase();
    q.split(" ").forEach(w => { if (w.length > 3 && text.includes(w)) s += 2; });
  }
  return s;
}
// Seeded RNG (mulberry32)
function makeRng(seed) {
  let a = seed >>> 0;
  return function () { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

function pick(pool, used, remaining, ctx, opts = {}) {
  const { isMeal = false, anchor = null, maxKm = HOP_KM } = opts;
  let best = null, bestHop = 0, bestS = null;
  const a_xy = anchor ? itemCoords(anchor) : null;
  for (const item of pool) {
    if (used.has(getTitle(item))) continue;
    if (ctx.family && item.family === false) continue;
    if (ctx.rain && !RAIN_OK.has(activityKind(item))) continue;
    let km = null, hop = 0;
    if (a_xy) {
      km = kmBetween(a_xy, itemCoords(item));
      if (km !== null) {
        if (km > maxKm) continue;
        if (km > WALK_KM) hop = LOCAL_HOP_COST;
      }
    }
    if (getCost(item) + hop > remaining) continue;
    const sc = score(item, ctx, used, isMeal, km);
    if (best === null || sc > bestS) { best = item; bestHop = hop; bestS = sc; }
  }
  return [best, bestHop];
}

function makeSlot(item, town, extra = 0, ctx = null, suffix = "") {
  if (!item) return { name: REST_NAME, cost: 0, maps: null, text: REST_NAME };
  const name = cleanName(getTitle(item));
  const q = item.coords || `${name} ${town}`;
  const cost = getCost(item) + extra;
  let text = `${name} - ${fmtCost(cost)}`;
  if (extra) text += ` (incl. R${extra} ride)`;
  if (ctx && ctx.month && WHALE_MONTHS.has(ctx.month) && WHALE_SPOTS.some(w => name.toLowerCase().includes(w))) text += " [whale-watching season - sightings not guaranteed]";
  text += suffix;
  return { name, cost, maps: mapsLink(q), text, title: name, description: getDesc(item), town };
}

// ============ CORE - generate_smart_itinerary ============
function generateSmartItinerary(allEvents, allRests, keys, days, opts, warnings) {
  const { style = "family", budgetMax = null, diet = null, familyMode = false, shuffle = false, seed = 42, month = null, rainyDays = new Set() } = opts;
  const budget = budgetMax !== null ? parseFloat(budgetMax) : Infinity;
  const ctx = {
    style, diet,
    family: Boolean(familyMode) || style === "family",
    shuffle: Boolean(shuffle),
    frugal: style === "backpacker" || (budgetMax !== null && budgetMax <= 500),
    rng: makeRng(seed),
    month, season: month ? SEASON_OF[month] : null,
    rainy: rainyDays, rain: false,
    query: opts.query || ""
  };
  // Town pools: events in that town OR if no town field, share pool
  function poolFor(townKey, all) {
    const townName = display(townKey);
    const filtered = all.filter(i => {
      const t = getTown(i);
      if (!t) return true;
      return t.includes(townName) || townName.includes(t) || resolveTown(t) === townKey;
    });
    return filtered.length ? filtered : all;
  }

  let towns = [...keys].sort((a, b) => ROUTE_ORDER.indexOf(a) - ROUTE_ORDER.indexOf(b));
  if (towns.length > days) {
    const dropped = towns.slice(days).map(display).join(", ");
    warnings.push(`${towns.length} towns but only ${days} day(s): skipping ${dropped}. Add days to include them.`);
    towns = towns.slice(0, days);
  }
  // allocate days
  const base = Math.floor(days / towns.length), extra = days % towns.length;
  const blocks = towns.map((_, i) => base + (i < extra ? 1 : 0));

  const used = new Set(), plan = [], baseCosts = [], unverifiedDays = [];
  let dayNo = 1, prev = null;

  for (let ti = 0; ti < towns.length; ti++) {
    const key = towns[ti], nDays = blocks[ti];
    const town = display(key);
    const dayPool = poolFor(key, allEvents);
    const evePool = poolFor(key, allRests); // restaurants = evening meals
    // Hotel estimate - no hotel data in JSON, use season-adjusted estimate
    const hotelBase = 350;
    const mult = month ? (PRICE_MULT[month] || 1.0) : 1.0;
    const hotelCost = Math.round(hotelBase * mult / 10) * 10;
    const hotel = { name: `Hostel / Guesthouse in ${town}`, cost: hotelCost };
    const blockStart = dayNo;
    let ranOut = false, hopDays = 0;

    for (let d = 0; d < nDays; d++) {
      ctx.rain = rainyDays.has(dayNo);
      let remaining = budget - hotel.cost - FOOD_ALLOWANCE;

      let [mItem, mHop] = pick(dayPool, used, remaining, ctx);
      if (mItem) { used.add(getTitle(mItem)); remaining -= getCost(mItem) + mHop; }
      let [aItem, aHop] = pick(dayPool, used, remaining, ctx, { anchor: mItem });
      if (aItem) { used.add(getTitle(aItem)); remaining -= getCost(aItem) + aHop; }

      let morning = makeSlot(mItem, town, mHop, ctx);
      let afternoon = makeSlot(aItem, town, aHop, ctx);
      let fallback = null, eveAnchor = aItem || mItem;

      // HUB FALLBACK - v7.6 rule 1
      if (!mItem && !aItem) {
        const hub = HUBS[key];
        const hubTown = display(hub);
        const [mins, km] = routeLeg(key, hub);
        const fare = fareFor(km);
        const hubPool = poolFor(hub, allEvents);
        if (remaining < 2 * fare) warnings.push(`Day ${dayNo}: trip to ${hubTown} costs ~R${2 * fare} return and pushes this day over budget - only free activities there were considered.`);
        const [hItem] = pick(hubPool, used, remaining - 2 * fare, ctx);
        if (hItem) {
          used.add(getTitle(hItem));
          remaining -= 2 * fare + getCost(hItem);
          const why = ctx.rain ? "rain" : "nothing new left here";
          morning = { name: `Trip to ${hubTown}`, cost: fare, maps: mapsLink(`${hubTown} South Africa`), text: `Not much on in ${town} today (${why}) - head to ${hubTown} (~${mins} min, ~R${fare}) by a shared minibus taxi, the Baz Bus or a hostel lift (ask at reception)`, title: `Trip to ${hubTown}`, description: `Not much on in ${town} today (${why})` };
          afternoon = makeSlot(hItem, hubTown, fare, ctx, " - includes the ride back; confirm the last one before you go");
          fallback = { type: "hub_trip", hub: hubTown, minutes_each_way: mins, fare_each_way: `R${fare}`, reason: why, estimate: true };
          eveAnchor = null;
          hopDays++;
        }
      }

      // Evening = restaurant (meal), walkable from afternoon or self-cook
      let [eItem] = pick(evePool, used, remaining, ctx, { isMeal: true, anchor: eveAnchor, maxKm: WALK_KM });
      if (eItem) used.add(getTitle(eItem));
      let evening = makeSlot(eItem, town, 0, ctx);
      if (!eItem) evening = { name: REST_NAME, cost: 0, maps: null, text: REST_NAME, title: REST_NAME, description: "" };

      if (!fallback && (!mItem || !aItem)) {
        ranOut = true;
        if (ctx.rain && !mItem && !aItem) warnings.push(`Day ${dayNo} (rain): no covered/indoor option within budget in ${town} or ${display(HUBS[key])}. Rest day, or raise budget for a market/indoor trip.`);
      }

      const act = morning.cost + afternoon.cost + evening.cost;
      const allIn = hotel.cost + FOOD_ALLOWANCE + act;
      baseCosts.push(hotel.cost + FOOD_ALLOWANCE);
      const status = budgetMax === null ? "No cap" : allIn <= budgetMax ? `FITS R${budgetMax}` : `OVER R${budgetMax} by R${allIn - budgetMax}`;

      let gettingHere = null;
      if (dayNo === blockStart && prev) {
        const [mins, km] = routeLeg(prev, key);
        gettingHere = `Travel day ${display(prev)} -> ${town}: ~${mins} min, ~${km} km via the N2. Use the Baz Bus (hostel to hostel, book ahead), a hostel lift or a shared minibus taxi. Estimates - confirm times.`;
      }

      let safety = dayNo === blockStart ? `Evening: torch + tell hostel + no night swim` : `Same as Day ${blockStart} (${town})`;
      if (ctx.season === "winter") safety += " - Winter: dark by ~17:30, be back at the hostel before then.";

      plan.push({
        day: dayNo, town, town_verified: town,
        weather_mode: ctx.rain ? "rain" : null,
        getting_here: gettingHere,
        fallback,
        morning: morning.text, morning_maps: morning.maps, morning_item: morning,
        afternoon: afternoon.text, afternoon_maps: afternoon.maps, afternoon_item: afternoon,
        evening: evening.text, evening_maps: evening.maps, evening_item: evening,
        // Compatibility for old index.html that expects lunch/dinner
        lunch: afternoon.text, lunch_item: afternoon,
        dinner: evening.text, dinner_item: evening,
        title: `Day ${dayNo} in ${town} - ${style}`,
        hotel: `${hotel.name} R${hotel.cost}/night`,
        hotel_maps: mapsLink(`${hotel.name} ${town}`),
        day_budget_activities: `R${act}`,
        day_budget_with_hotel: `R${hotel.cost + act}`,
        day_food_estimate: `R${FOOD_ALLOWANCE}`,
        day_budget_all_in: `R${allIn} - ${status}`,
        safety,
        best_time: month ? MONTH_NAMES[month] : "Any month",
        dietary_tags: diet ? `evening NOT verified ${diet} - self-cater or ask first` : "any",
        _totals: [act, hotel.cost, allIn]
      });
      dayNo++;
    }
    if (hopDays >= 2) warnings.push(`${town}: ${hopDays} day(s) need a trip to ${display(HUBS[key])}. Consider spending fewer nights in ${town} or basing in ${display(HUBS[key])}.`);
    if (ranOut) warnings.push(`${town}: still some free-time slots after the hub fallback. Consider fewer days here.`);
    prev = key;
  }

  const minDaily = baseCosts.length ? Math.max(...baseCosts) : 0;
  const daysOver = plan.filter(d => budgetMax !== null && d._totals[2] > budgetMax).length;
  return { plan, towns, minDaily, daysOver };
}

// ============ HANDLER ============
export default async function handler(req, res) {
  try {
    const warnings = [];
    const rawTown = req.query.town || "Knysna";
    const townKey = resolveTown(rawTown) || "knysna";
    const query = req.query.query || req.query.q || "family";
    const days = Math.min(parseInt(req.query.days || "2") || 2, 30);
    const style = (req.query.style || query || "family").toLowerCase();
    const validStyles = ["adventure", "backpacker", "family", "chill", "foodie"];
    const styleClean = validStyles.includes(style) ? style : "family";
    const budgetMax = req.query.budget ? parseInt(req.query.budget) : null;
    const diet = req.query.diet || null;
    const monthRaw = req.query.month || "";
    let month = null;
    if (monthRaw) {
      const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
      if (/^\d+$/.test(String(monthRaw))) month = parseInt(monthRaw);
      else month = MONTHS[String(monthRaw).toLowerCase().slice(0, 3)];
      if (!month || month < 1 || month > 12) month = null;
    }
    const rainyDays = new Set((req.query.rainy_days ? String(req.query.rainy_days).split(",").map(x => parseInt(x)) : []).filter(n => !isNaN(n)));
    const shuffle = req.query.shuffle === "1" || req.query.shuffle === "true";
    const seed = parseInt(req.query.seed || "42") || 42;
    // Support multi-town: ?towns=knysna,plettenberg_bay or single town
    let keys = [townKey];
    if (req.query.towns) {
      const parsed = String(req.query.towns).split(",").map(resolveTown).filter(Boolean);
      if (parsed.length) keys = parsed;
    }

    const { events, restaurants } = await loadData();
    const { plan, towns, minDaily, daysOver } = generateSmartItinerary(events, restaurants, keys, days, {
      style: styleClean, budgetMax, diet, familyMode: styleClean === "family", shuffle, seed, month, rainyDays, query
    }, warnings);

    const season = month ? SEASON_OF[month] : null;
    res.status(200).json({
      query, town: display(townKey), towns: towns.map(display), days, plan,
      style: styleClean, month: month ? MONTH_NAMES[month] : null, season,
      season_notes: season ? SEASON_NOTES[season] : null,
      whale_season: month ? WHALE_MONTHS.has(month) : false,
      warnings,
      min_daily: minDaily, days_over_budget: daysOver,
      summary: `A ${days}-day ${styleClean} plan for ${towns.map(display).join(", ")} - ${plan.length} days, ${warnings.length} warnings.`
    });
  } catch (e) {
    res.status(500).json({ error: "Itinerary failed", detail: String(e) });
  }
}