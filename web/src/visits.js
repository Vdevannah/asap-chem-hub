// "New since your last visit", with no account: two timestamps in this browser's localStorage.
//   asap.lastActive  when this browser last had the site open (refreshed every 5 minutes)
//   asap.baseline    the "last visit" that NEW badges are measured against
// A gap of more than 30 minutes since lastActive starts a new session, and the old lastActive
// becomes the baseline. Reloading within a session keeps the same baseline.
const LAST_KEY = "asap.lastActive";
const BASE_KEY = "asap.baseline";
const SESSION_GAP_MS = 30 * 60 * 1000;
const HEARTBEAT_MS = 5 * 60 * 1000;

function read(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* storage unavailable: badges simply don't show */ }
}
const valid = (s) => (s && !Number.isNaN(Date.parse(s)) ? s : null);

let baseline = null;
let started = false;

function start() {
  if (started) return;
  started = true;
  const last = valid(read(LAST_KEY));
  if (!last) baseline = null;                                          // first visit
  else if (Date.now() - Date.parse(last) > SESSION_GAP_MS) baseline = last;  // new session
  else baseline = valid(read(BASE_KEY));                              // same session
  write(BASE_KEY, baseline);
  const touch = () => write(LAST_KEY, new Date().toISOString());
  touch();
  setInterval(touch, HEARTBEAT_MS);
}

// ISO UTC string of the last visit, or null on a first visit.
export function getBaseline() {
  start();
  return baseline;
}

// Was this row (first_seen_at from the API, UTC without a zone) added after the last visit?
export function isNewSince(firstSeen, base = getBaseline()) {
  if (!base || !firstSeen) return false;
  const t = Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(firstSeen) ? firstSeen : firstSeen + "Z");
  return t > Date.parse(base);
}

// "Nov 12, 6:40 pm" in the reader's local time.
export function formatVisit(iso) {
  return new Date(iso)
    .toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    .replace(/\s?([AP])M\b/i, (_, x) => ` ${x.toLowerCase()}m`);
}
