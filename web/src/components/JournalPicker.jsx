import { useEffect, useRef } from "react";

// Dialog with every journal grouped by field. Changes apply as they are made.
export default function JournalPicker({ journals, selected, onChange, onClose }) {
  const dialog = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const d = dialog.current;
    if (!d.open) d.showModal();
    const close = () => closeRef.current();
    d.addEventListener("close", close);
    return () => d.removeEventListener("close", close);
  }, []);

  const groups = [];
  for (const j of journals) {
    let g = groups.find((x) => x.name === j.picker_group);
    if (!g) groups.push((g = { name: j.picker_group, items: [] }));
    g.items.push(j);
  }

  const set = new Set(selected);
  const toggle = (id) => {
    set.has(id) ? set.delete(id) : set.add(id);
    onChange([...set]);
  };
  const toggleGroup = (g, on) => {
    for (const j of g.items) on ? set.add(j.journal_id) : set.delete(j.journal_id);
    onChange([...set]);
  };

  return (
    <dialog ref={dialog} className="picker" aria-labelledby="picker-title">
      <header className="picker-head">
        <h2 id="picker-title">Choose journals</h2>
        <p>{selected.length} of {journals.length} selected. Your choice is saved in this browser.</p>
        <div className="picker-actions">
          <button type="button" onClick={() => onChange(journals.map((j) => j.journal_id))}>Select all</button>
          <button type="button" onClick={() => onChange(journals.filter((j) => j.default_on).map((j) => j.journal_id))}>Defaults</button>
          <button type="button" onClick={() => onChange([])}>Clear</button>
        </div>
      </header>
      <div className="picker-body">
        {groups.map((g) => {
          const on = g.items.filter((j) => set.has(j.journal_id)).length;
          return (
            <section key={g.name} className="picker-group">
              <div className="picker-group-head">
                <h3>{g.name}</h3>
                <button type="button" className="text-button" onClick={() => toggleGroup(g, on < g.items.length)}>
                  {on < g.items.length ? "Select group" : "Clear group"}
                </button>
              </div>
              <ul>
                {g.items.map((j) => (
                  <li key={j.journal_id}>
                    <label>
                      <input type="checkbox" checked={set.has(j.journal_id)} onChange={() => toggle(j.journal_id)} />
                      <span>{j.name}</span>
                      <span className="count">{j.article_count}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      <footer className="picker-foot">
        <button type="button" className="primary" onClick={() => dialog.current.close()}>
          Done
        </button>
      </footer>
    </dialog>
  );
}
