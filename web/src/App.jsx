import { useEffect, useState } from "react";
import { api, timeAgo } from "./api";
import { useStoredState } from "./hooks";
import Banner from "./components/Banner";
import ThemeToggle from "./components/ThemeToggle";
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
        <div className="topbar-end">
          <p className="refreshed">
            {status && current.refreshed ? `Updated ${timeAgo(status[current.refreshed])}` : ""}
          </p>
          <ThemeToggle />
        </div>
      </header>

      <Banner />

      <main id="content" className="content">
        <ArticlesTab active={current.id === "articles"} />
        <PatentsTab active={current.id === "patents"} />
        <About active={current.id === "about"} />
      </main>

      <footer className="site-foot">
        <p className="site-credit">
          © {new Date().getFullYear()} ASAP Chem Hub · Designed and built by{" "}
          <span className="site-credit-name">Vijayarajan Devannah</span>
        </p>
        <p className="site-legal">
          Articles, abstracts and figures © their publishers; patent data from EPO Open Patent Services.
          Independent; not affiliated with any publisher or the EPO.
        </p>
      </footer>
    </div>
  );
}
