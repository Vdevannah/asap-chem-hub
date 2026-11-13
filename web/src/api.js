// Talks to the FastAPI backend. Address from VITE_API_URL, default = local API.
const BASE = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

async function get(path, params = {}) {
  const url = new URL(BASE + path);
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)) continue;
    url.searchParams.set(k, Array.isArray(v) ? v.join(",") : v);
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`The server answered ${res.status} for ${path}`);
  return res.json();
}

export const api = {
  status: () => get("/status"),
  journals: () => get("/journals"),
  topics: () => get("/topics"),
  patentTopics: () => get("/patent-topics"),
  articles: (p) => get("/articles", p),
  journalCounts: (p) => get("/journal-counts", p),
  patents: (p) => get("/patents", p),
};

// MySQL stores UTC without a zone; mark it as UTC so the browser shows local time.
export function parseUtc(s) {
  if (!s) return null;
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
}

export function timeAgo(s) {
  const d = parseUtc(s);
  if (!d) return "not yet";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs} h ago`;
  const days = Math.round(hrs / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export function formatDate(s) {
  if (!s) return "";
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

// Abstracts can carry publisher markup (<p>, <sub>, <i>): show plain text.
export function plainText(html) {
  if (!html) return "";
  const doc = new DOMParser().parseFromString(html, "text/html");
  return (doc.body.textContent || "").replace(/\s+/g, " ").trim();
}
