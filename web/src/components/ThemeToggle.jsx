import { useEffect, useState } from "react";
import { MODES, applyMode, onSystemChange, readMode, saveMode } from "../theme";

const LABELS = {
  auto: "Theme: Auto (follows your device)",
  light: "Theme: Light",
  dark: "Theme: Dark",
};

function Icon({ mode }) {
  const common = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", "aria-hidden": true };
  if (mode === "light") {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4.2" />
        {[0, 45, 90, 135, 180, 225, 270, 315].map((a) => (
          <line key={a} x1="12" y1="2.8" x2="12" y2="5.2" transform={`rotate(${a} 12 12)`} />
        ))}
      </svg>
    );
  }
  if (mode === "dark") {
    return (
      <svg {...common}>
        <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4a8 8 0 0 0 0 16z" fill="currentColor" stroke="none" />
    </svg>
  );
}

// Small icon button in the top bar: Auto -> Light -> Dark -> Auto.
export default function ThemeToggle() {
  const [mode, setMode] = useState(readMode);

  useEffect(() => {
    applyMode(mode);
    if (mode !== "auto") return undefined;
    return onSystemChange(() => applyMode("auto"));   // follow the device live
  }, [mode]);

  const next = () => {
    const m = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    saveMode(m);
    setMode(m);
  };

  return (
    <button type="button" className="theme-toggle" onClick={next} aria-label={LABELS[mode]} title={LABELS[mode]}>
      <Icon mode={mode} />
    </button>
  );
}
