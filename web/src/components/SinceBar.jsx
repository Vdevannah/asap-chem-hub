import { formatVisit } from "../visits";

// "18 new since your last visit on Nov 12, 6:40 pm", plus optional tools (the view switch) at the right.
// Without a baseline or new items, only the tools are shown.
export default function SinceBar({ count, baseline, children }) {
  const show = baseline && count > 0;
  if (!show && !children) return null;
  return (
    <div className={show ? "since-bar" : "feed-tools"}>
      {show && (
        <p className="since-text">
          <strong>{count.toLocaleString()}</strong> new since your last visit on {formatVisit(baseline)}
        </p>
      )}
      {children && <div className="since-tools">{children}</div>}
    </div>
  );
}

export function ViewSwitch({ value, onChange }) {
  return (
    <div className="segmented view-switch" role="group" aria-label="Layout">
      {[["grid", "Grid"], ["list", "List"]].map(([v, label]) => (
        <button key={v} type="button" aria-pressed={value === v} className={value === v ? "on" : ""} onClick={() => onChange(v)}>
          {label}
        </button>
      ))}
    </div>
  );
}
