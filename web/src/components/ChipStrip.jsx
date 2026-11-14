import { useEffect, useRef, useState } from "react";

// A horizontally scrollable row of filter chips with ‹ › arrows: "All" first, then one chip per item.
// items: [{ id, label, n, plus }]   (plus = optional "+N new" count)
export default function ChipStrip({ items, all, focus, onFocus, ariaLabel, noun = "items" }) {
  const row = useRef(null);
  const [edges, setEdges] = useState({ start: true, end: true });

  const measure = () => {
    const el = row.current;
    if (!el) return;
    setEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 });
  };
  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [items, all]);

  // keep the chosen chip in view when it changes. Scroll only the row, sideways: scrollIntoView would
  // also scroll the whole page down to the strip (on load, on phones, the top of the page got cut off).
  useEffect(() => {
    const el = row.current;
    const chip = el?.querySelector('[aria-pressed="true"]');
    if (!el || !chip) return;
    const r = el.getBoundingClientRect();
    const c = chip.getBoundingClientRect();
    if (c.left < r.left) el.scrollLeft -= r.left - c.left + 8;
    else if (c.right > r.right) el.scrollLeft += c.right - r.right + 8;
  }, [focus]);

  const scroll = (dir) => row.current?.scrollBy({ left: dir * row.current.clientWidth * 0.7, behavior: "smooth" });
  const plus = (k) =>
    k > 0 ? <span className="jchip-new" title={`${k} new since your last visit`}>+{k.toLocaleString()}</span> : null;
  const count = (n) => (n === null || n === undefined ? null : <span className="jchip-n">{n.toLocaleString()}</span>);

  return (
    <div className="strip" role="group" aria-label={ariaLabel}>
      <button type="button" className="strip-arrow" onClick={() => scroll(-1)} disabled={edges.start} aria-label={`Scroll ${noun} left`}>
        ‹
      </button>
      <div className="strip-row" ref={row} onScroll={measure}>
        <button type="button" className="jchip" aria-pressed={focus === null} onClick={() => onFocus(null)}>
          All {count(all?.n)}{plus(all?.plus)}
        </button>
        {items.map((it) => (
          <button
            key={it.id}
            type="button"
            className={"jchip" + (it.n === 0 ? " empty" : "")}
            aria-pressed={focus === it.id}
            onClick={() => onFocus(focus === it.id ? null : it.id)}
          >
            {it.label} {count(it.n)}{plus(it.plus)}
          </button>
        ))}
      </div>
      <button type="button" className="strip-arrow" onClick={() => scroll(1)} disabled={edges.end} aria-label={`Scroll ${noun} right`}>
        ›
      </button>
    </div>
  );
}
