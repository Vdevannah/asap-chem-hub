import { useRef, useState } from "react";

// Filter column. On phones it folds behind a "Filters" button so results show first.
export default function Sidebar({ label, active, children }) {
  const [open, setOpen] = useState(false);
  const timer = useRef(0);
  // show the scrollbar thumb while the column scrolls (keyboard / touch scrolling has no hover)
  const onScroll = (e) => {
    const el = e.currentTarget;
    el.classList.add("is-scrolling");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => el.classList.remove("is-scrolling"), 700);
  };
  return (
    <aside className={"sidebar" + (open ? " open" : "")} aria-label={label} onScroll={onScroll}>
      <button type="button" className="filters-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide filters" : "Filters"}
        {active > 0 && <span className="filters-count">{active} on</span>}
      </button>
      <div className="sidebar-body">{children}</div>
    </aside>
  );
}
