import ChipStrip from "./ChipStrip";

// The chosen journals with live counts. Clicking one shows only that journal.
// counts: { journal_id: n }, newCounts (optional): { journal_id: new since last visit }
export default function JournalStrip({ journals, counts, newCounts = {}, focus, onFocus }) {
  const items = journals.map((j) => ({
    id: j.journal_id, label: j.name, n: counts[j.journal_id] || 0, plus: newCounts[j.journal_id] || 0,
  }));
  const all = {
    n: items.reduce((s, it) => s + it.n, 0),
    plus: items.reduce((s, it) => s + it.plus, 0),
  };
  return <ChipStrip items={items} all={all} focus={focus} onFocus={onFocus} ariaLabel="Show one journal" noun="journals" />;
}
