import { useEffect, useState } from "react";
import { api, timeAgo } from "./api";
import { useStoredState } from "./hooks";
import ArticlesTab from "./components/ArticlesTab";
import PatentsTab from "./components/PatentsTab";

const TABS = [
  { id: "articles", label: "ASAP Articles", count: "total_articles", refreshed: "last_refreshed" },
  { id: "patents", label: "New Patents", count: "total_patents", refreshed: "patents_last_refreshed" },
];

export default function App() {
  const [tab, setTab] = useStoredState("asap.tab", "articles");
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  const current = TABS.find((t) => t.id === tab) || TABS[0];

  const onTabKey = (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.findIndex((t) => t.id === current.id);
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(next.id);
    document.getElementById(`tab-${next.id}`)?.focus();
  };

  return (
    <div className={`app theme-${current.id}`}>
      <header className="masthead">
        <div className="brand">
          <h1>ASAP Chem Hub</h1>
          <p>ASAP articles and new patents in one place</p>
        </div>
        <p className="refreshed">
          {status ? `Updated ${timeAgo(status[current.refreshed])}` : ""}
        </p>
      </header>

      <nav className="tabs" role="tablist" aria-label="Sections" onKeyDown={onTabKey}>
        {TABS.map((t) => (
          <button
            key={t.id}
            id={`tab-${t.id}`}
            role="tab"
            type="button"
            aria-selected={current.id === t.id}
            tabIndex={current.id === t.id ? 0 : -1}
            className={`tab tab-${t.id}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
            {status && <span className="tab-count">{Number(status[t.count] || 0).toLocaleString()}</span>}
          </button>
        ))}
      </nav>

      <main>
        <ArticlesTab active={current.id === "articles"} />
        <PatentsTab active={current.id === "patents"} />
      </main>

      <footer className="site-foot">
        <p>
          Articles come from publisher feeds, Crossref and Springer Nature; patents from the European Patent Office.
          Figures are shown from the publishers' own servers and every card links to the original.
        </p>
      </footer>
    </div>
  );
}
