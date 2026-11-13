import { useState } from "react";

// Filter column. On phones it folds behind a "Filters" button so results show first.
export default function Sidebar({ label, active, children }) {
  const [open, setOpen] = useState(false);
  return (
    <aside className={"sidebar" + (open ? " open" : "")} aria-label={label}>
      <button type="button" className="filters-toggle" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide filters" : "Filters"}
        {active > 0 && <span className="filters-count">{active} on</span>}
      </button>
      <div className="sidebar-body">{children}</div>
    </aside>
  );
}
