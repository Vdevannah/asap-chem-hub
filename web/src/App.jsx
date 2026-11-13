import { useEffect, useState } from "react";
import { api, timeAgo } from "./api";
import { useStoredState } from "./hooks";
import Hero from "./components/Hero";
import About from "./components/About";
import ArticlesTab from "./components/ArticlesTab";
import PatentsTab from "./components/PatentsTab";

const TABS = [
  { id: "articles", label: "Articles", count: "total_articles", refreshed: "last_refreshed" },
  { id: "patents", label: "Patents", count: "total_patents", refreshed: "patents_last_refreshed" },
  { id: "about", label: "About" },
];

export default function App() {
  const [tab, setTab] = useStoredState("asap.tab", "articles");
  const [status, setStatus] = useState(null);

  useEffect(() => {
    api.status().then(setStatus).catch(() => setStatus(null));
  }, []);

  const current = TABS.find((t) => t.id === tab) || TABS[0];

  const open = (id) => {
    setTab(id);
    requestAnimationFrame(() =>
      document.getElementById("content")?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  const onTabKey = (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = TABS.findIndex((t) => t.id === current.id);
    const next = TABS[(i + (e.key === "ArrowRight" ? 1 : TABS.length - 1)) % TABS.length];
    setTab(next.id);
    document.getElementById(`tab-${next.id}`)?.focus();
  };

  return (
    <div className={`app theme-${current.id}`}>
      <header className="topbar">
        <a className="wordmark" href="#top" onClick={(e) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
          ASAP Chem Hub
        </a>
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
              onClick={() => open(t.id)}
            >
              {t.label}
              {status && t.count && <span className="tab-count">{Number(status[t.count] || 0).toLocaleString()}</span>}
            </button>
          ))}
        </nav>
        <p className="refreshed">
          {status && current.refreshed ? `Updated ${timeAgo(status[current.refreshed])}` : ""}
        </p>
      </header>

      <Hero status={status} onOpen={open} />

      <main id="content" className="content">
        <ArticlesTab active={current.id === "articles"} />
        <PatentsTab active={current.id === "patents"} />
        <About active={current.id === "about"} />
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
