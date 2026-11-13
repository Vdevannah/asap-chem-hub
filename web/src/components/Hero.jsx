import { useEffect, useRef, useState } from "react";

// Big opening: a molecular network drawn in the four topic colours, the name, and two
// rings that open the Articles and Patents sections.

// Two fused rings and a chain, loosely like a drawn molecule. Coordinates in a 520 x 420 box.
const NODES = [
  [120, 150, "ink", 9], [170, 120, "", 6], [220, 150, "", 6], [220, 210, "synthesis", 12],
  [170, 240, "", 6], [120, 210, "", 7], [270, 240, "", 5], [320, 210, "bio", 9],
  [320, 150, "", 6], [270, 120, "", 5], [370, 240, "", 6], [410, 290, "materials", 8],
  [370, 120, "computational", 7], [80, 260, "", 5], [60, 320, "bio", 6], [460, 270, "", 4],
  [170, 60, "materials", 5], [400, 80, "", 4],
];
const EDGES = [
  [0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 0], [3, 6], [6, 7], [7, 8], [8, 9], [9, 2],
  [7, 10], [10, 11], [8, 12], [5, 13], [13, 14], [11, 15], [1, 16], [12, 17],
];

function Network() {
  return (
    <svg className="network" viewBox="0 0 520 380" aria-hidden="true">
      {EDGES.map(([a, b], i) => (
        <line key={i} x1={NODES[a][0]} y1={NODES[a][1]} x2={NODES[b][0]} y2={NODES[b][1]} />
      ))}
      {NODES.map(([x, y, c, r], i) => (
        <circle key={i} cx={x} cy={y} r={r} className={`node ${c || "plain"}`} style={{ "--i": i }} />
      ))}
    </svg>
  );
}

// First visit shows the big hero; later visits show a slim band. The variant is chosen once
// on page load and never changes during the visit, so nothing resizes while you scroll.
const SEEN_KEY = "asap.heroSeen";

function readSeen() {
  try { return localStorage.getItem(SEEN_KEY) !== null; } catch { return false; }
}
function markSeen() {
  try { localStorage.setItem(SEEN_KEY, "1"); } catch { /* storage unavailable */ }
}

export default function Hero({ status, onOpen }) {
  const [compact] = useState(readSeen);
  const ref = useRef(null);

  // Remember the big hero once it has scrolled fully out of view (affects the next visit only).
  useEffect(() => {
    if (compact || !ref.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting && e.boundingClientRect.bottom <= 0) {
        markSeen();
        io.disconnect();
      }
    });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [compact]);

  const go = (id) => { markSeen(); onOpen(id); };
  const n = (k) => (status ? Number(status[k] || 0).toLocaleString() : "…");
  return (
    <section ref={ref} className={"hero" + (compact ? " compact" : "")}>
      <Network />
      <div className="hero-text">
        <h1 className="hero-title">ASAP Chem Hub</h1>
        <div className="divider" aria-hidden="true"><span /></div>
        <p className="hero-lede">
          <span className="lede-full">
            The newest chemistry papers, with their graphical abstracts, and newly published patent
            applications. Filter by journal and research topic. Updated every day.
          </span>
          <span className="lede-short">The newest chemistry papers and patents, by topic. Updated every day.</span>
        </p>
        <div className="doors">
          <button type="button" className="door door-articles" onClick={() => go("articles")}>
            <span className="door-count">{n("total_articles")}</span>
            <span className="door-name">ASAP articles</span>
            <span className="door-sub">37 journals, last 30 days</span>
          </button>
          <button type="button" className="door door-patents" onClick={() => go("patents")}>
            <span className="door-count">{n("total_patents")}</span>
            <span className="door-name">New patents</span>
            <span className="door-sub">WO applications, last 90 days</span>
          </button>
        </div>
        {compact && (
          <button type="button" className="hero-about" onClick={() => onOpen("about")}>
            About this site
          </button>
        )}
      </div>
    </section>
  );
}
