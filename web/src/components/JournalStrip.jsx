import { useEffect, useRef, useState } from "react";

// A scrollable row of the chosen journals with live counts. Clicking one shows only that journal.
export default function JournalStrip({ journals, counts, focus, onFocus }) {
  const row = useRef(null);
  const [edges, setEdges] = useState({ start: true, end: true });

  const total = journals.reduce((sum, j) => sum + (counts[j.journal_id] || 0), 0);

  const measure = () => {
    const el = row.current;
    if (!el) return;
    setEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 });
  };
  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [journals, counts]);

  // keep the chosen chip in view when it changes
  useEffect(() => {
    row.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [focus]);

  const scroll = (dir) => row.current?.scrollBy({ left: dir * row.current.clientWidth * 0.7, behavior: "smooth" });

  return (
    <div className="strip" role="group" aria-label="Show one journal">
      <button type="button" className="strip-arrow" onClick={() => scroll(-1)} disabled={edges.start} aria-label="Scroll journals left">
        ‹
      </button>
      <div className="strip-row" ref={row} onScroll={measure}>
        <button type="button" className="jchip" aria-pressed={focus === null} onClick={() => onFocus(null)}>
          All <span className="jchip-n">{total.toLocaleString()}</span>
        </button>
        {journals.map((j) => {
          const n = counts[j.journal_id] || 0;
          return (
            <button
              key={j.journal_id}
              type="button"
              className={"jchip" + (n === 0 ? " empty" : "")}
              aria-pressed={focus === j.journal_id}
              onClick={() => onFocus(focus === j.journal_id ? null : j.journal_id)}
            >
              {j.name} <span className="jchip-n">{n.toLocaleString()}</span>
            </button>
          );
        })}
      </div>
      <button type="button" className="strip-arrow" onClick={() => scroll(1)} disabled={edges.end} aria-label="Scroll journals right">
        ›
      </button>
    </div>
  );
}
