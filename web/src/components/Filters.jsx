// Shared sidebar controls: search box, day range, topic chips.

export function SearchBox({ value, onChange, placeholder }) {
  return (
    <label className="field">
      <span className="field-label">Search</span>
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export function DayRange({ options, value, onChange }) {
  return (
    <fieldset className="field">
      <legend className="field-label">Published in the last</legend>
      <div className="segmented">
        {options.map((d) => (
          <button
            key={d}
            type="button"
            aria-pressed={value === d}
            className={value === d ? "on" : ""}
            onClick={() => onChange(d)}
          >
            {d} days
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function TopicChips({ topics, selected, onChange }) {
  const toggle = (id) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  return (
    <fieldset className="field">
      <legend className="field-label">
        Topics
        {selected.length > 0 && (
          <button type="button" className="text-button" onClick={() => onChange([])}>
            Clear
          </button>
        )}
      </legend>
      <div className="chips">
        {topics.map((t) => (
          <button
            key={t.topic_id}
            type="button"
            aria-pressed={selected.includes(t.topic_id)}
            className={"chip" + (selected.includes(t.topic_id) ? " on" : "")}
            onClick={() => toggle(t.topic_id)}
          >
            {t.name}
          </button>
        ))}
      </div>
      <p className="hint">{selected.length ? "Showing items in any of the chosen topics." : "All topics."}</p>
    </fieldset>
  );
}
