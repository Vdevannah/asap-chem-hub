// Patent applicant names from EPO arrive in capitals, e.g. "HOFFMANN LA ROCHE [CH]; BASF SE [DE]".

const SUFFIXES = new Set(["AG", "SA", "LLC", "INC", "CO", "LTD", "KK", "AB", "NV", "SE"]);

// "HOFFMANN-LA ROCHE AG" -> "Hoffmann-La Roche AG". Words with digits and company suffixes stay as they are.
export function titleCaseName(name) {
  if (!name) return "";
  return name
    .split(" ")
    .map((w) => {
      if (/\d/.test(w)) return w;
      if (SUFFIXES.has(w.replace(/[^A-Za-z]/g, "").toUpperCase())) return w.toUpperCase();
      return w.toLowerCase().replace(/(^|[-/&('.])([a-zà-ÿ])/g, (_, p, c) => p + c.toUpperCase());
    })
    .join(" ");
}

// "A [US]; B [SE]; a [US]" -> ["A", "B"]  (country codes stripped, case-insensitive duplicates removed)
export function splitApplicants(text) {
  const seen = new Set();
  return (text || "")
    .split(";")
    .map((s) => s.replace(/\[[A-Za-z]{2}\]\s*$/, "").replace(/\s+/g, " ").trim())
    .filter((name) => {
      const key = name.toLowerCase();
      if (!name || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
// "2026-11-05" -> "5 Nov 2026"
export function dayMonthYear(iso) {
  const [y, m, d] = (iso || "").split("-").map(Number);
  return y ? `${d} ${MONTHS[m - 1]} ${y}` : "";
}
