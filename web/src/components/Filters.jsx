import { groupTopics, topicLabel } from "../topics";

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

// counts (optional): { topic_id: n } for the current filters other than topics.
// subgroups: show a family's sub-group headings (Articles tab: "Synthesis" / "Catalysis").
export function TopicChips({ topics, selected, onChange, counts, subgroups = false }) {
  const toggle = (id) =>
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  const chips = (items, inSubgroup) => (
    <div className="chips">
      {items.map((t) => {
        const n = counts ? counts[t.topic_id] || 0 : null;
        const on = selected.includes(t.topic_id);
        return (
          <button
            key={t.topic_id}
            type="button"
            aria-pressed={on}
            className={"chip" + (on ? " on" : "") + (n === 0 ? " zero" : "")}
            onClick={() => toggle(t.topic_id)}
          >
            {topicLabel(t.name, inSubgroup)}
            {n !== null && <span className="chip-n">{n.toLocaleString()}</span>}
          </button>
        );
      })}
    </div>
  );
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
      {groupTopics(topics, subgroups).map((g) => (
        <div key={g.id} className={`topic-group fam-${g.id}`}>
          <p className="topic-group-name">{g.name}</p>
          {g.subgroups
            ? g.subgroups.map((s) => (
                <div key={s.name} className="topic-subgroup" role="group" aria-label={`${g.name}: ${s.name}`}>
                  <p className="topic-subgroup-name" aria-hidden="true">{s.name}</p>
                  {chips(s.items, true)}
                </div>
              ))
            : chips(g.items, false)}
        </div>
      ))}
      <p className="hint">{selected.length ? "Showing items in any of the chosen topics." : "All topics."}</p>
    </fieldset>
  );
}
