// Colour theme: "auto" (follow the device), "light" or "dark", saved in localStorage "asap.theme".
// index.html applies the saved choice before React loads (no flash); this module keeps it in sync after that.
const KEY = "asap.theme";
export const MODES = ["auto", "light", "dark"];
const media = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

export function readMode() {
  try {
    const m = localStorage.getItem(KEY);
    return MODES.includes(m) ? m : "auto";
  } catch {
    return "auto";
  }
}

export function saveMode(mode) {
  try {
    localStorage.setItem(KEY, mode);
  } catch { /* storage unavailable: the choice lasts for this page only */ }
}

// Set <html data-theme> and the browser UI colour (<meta name="theme-color">) for a mode.
export function applyMode(mode) {
  const dark = mode === "dark" || (mode === "auto" && !!media?.matches);
  const root = document.documentElement;
  root.dataset.theme = dark ? "dark" : "light";
  const page = getComputedStyle(root).getPropertyValue("--page").trim();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && page) meta.setAttribute("content", page);
}

// Call fn when the device switches between light and dark. Returns an unsubscribe function.
export function onSystemChange(fn) {
  if (!media) return () => {};
  media.addEventListener("change", fn);
  return () => media.removeEventListener("change", fn);
}
