import { useEffect, useState } from "react";
import { api } from "../api";
import { useDebounced, useFeed, useStoredState } from "../hooks";
import { ArticleCard } from "./Cards";
import { DayRange, SearchBox, TopicChips } from "./Filters";
import JournalPicker from "./JournalPicker";
import Lightbox from "./Lightbox";
import Feed from "./Feed";
import Sidebar from "./Sidebar";
import JournalStrip from "./JournalStrip";
import SinceBar, { ViewSwitch } from "./SinceBar";
import { getBaseline, isNewSince } from "../visits";

const baseline = getBaseline();   // fixed for this page load

export default function ArticlesTab({ active }) {
  const [journals, setJournals] = useState([]);
  const [topics, setTopics] = useState([]);
  const [setupError, setSetupError] = useState(null);
  const [chosen, setChosen] = useStoredState("asap.journals", null); // null = defaults
  const [topicIds, setTopicIds] = useStoredState("asap.articleTopics", []);
  const [days, setDays] = useStoredState("asap.articleDays", 7);
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(false);
  const [zoomed, setZoomed] = useState(null);       // article whose figure is open in the lightbox
  const [focus, setFocus] = useState(null);      // one journal picked from the strip, or null = all
  const [counts, setCounts] = useState({});
  const [newCounts, setNewCounts] = useState({});
  const [view, setView] = useStoredState("asap.articleView", "grid");
  const [topicCounts, setTopicCounts] = useState(null);
  const q = useDebounced(query.trim());

  useEffect(() => {
    Promise.all([api.journals(), api.topics()])
      .then(([j, t]) => { setJournals(j); setTopics(t); })
      .catch((e) => setSetupError(e.message));
  }, []);

  // Drop saved IDs of journals that no longer exist; use defaults on the first visit.
  const known = new Set(journals.map((j) => j.journal_id));
  const selected = chosen === null
    ? journals.filter((j) => j.default_on).map((j) => j.journal_id)
    : chosen.filter((id) => known.has(id));
  const ready = journals.length > 0;
  const focused = focus !== null && selected.includes(focus) ? focus : null;

  // live per-journal counts for the strip (same days / topics / search)
  const countKey = JSON.stringify({ topicIds, days, q });
  useEffect(() => {
    api.journalCounts({ topics: topicIds, days, q, since: baseline })
      .then((rows) => {
        setCounts(Object.fromEntries(rows.map((r) => [r.journal_id, r.n])));
        setNewCounts(Object.fromEntries(rows.map((r) => [r.journal_id, r.new_n || 0])));
      })
      .catch(() => { setCounts({}); setNewCounts({}); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [countKey]);

  // live per-topic counts for the chips (current journals or focused journal, days, search)
  const countJournals = focused !== null ? [focused] : [...selected].sort((a, b) => a - b);
  const topicCountKey = JSON.stringify({ countJournals, days, q });
  useEffect(() => {
    if (!ready || countJournals.length === 0) { setTopicCounts(null); return; }
    let live = true;
    api.topicCounts({ journals: countJournals, days, q })
      .then((rows) => { if (live) setTopicCounts(Object.fromEntries(rows.map((r) => [r.topic_id, r.n]))); })
      .catch(() => { if (live) setTopicCounts(null); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topicCountKey, ready]);

  const feed = useFeed(
    api.articles,
    { journals: focused !== null ? [focused] : [...selected].sort((a, b) => a - b), topics: topicIds, days, q, since: baseline },
    ready && selected.length > 0,
  );
  const stripJournals = journals.filter((j) => selected.includes(j.journal_id));

  return (
    <div className="section" hidden={!active}>
      <header className="tab-head">
        <h2 className="tab-heading">ASAP Articles</h2>
        <div className="divider" aria-hidden="true"><span /></div>
      </header>
      <div className="layout">
      <Sidebar label="Article filters" active={topicIds.length + (q ? 1 : 0)}>
        <SearchBox value={query} onChange={setQuery} placeholder="Title, author or abstract" />
        <DayRange options={[7, 14, 30]} value={days} onChange={setDays} />
        <div className="field">
          <span className="field-label">Journals</span>
          <button type="button" className="journal-button" onClick={() => setPicking(true)} disabled={!ready}>
            {ready ? `${selected.length} of ${journals.length} journals` : "Loading journals"}
            <span className="journal-button-action">Change</span>
          </button>
        </div>
        <TopicChips topics={topics} selected={topicIds} onChange={setTopicIds} counts={topicCounts} />
      </Sidebar>

      <section className="results" aria-live="polite">
        {setupError ? (
          <div className="notice">
            <p>The article list could not load: {setupError}.</p>
            <p>Check that the API is running (uvicorn api.main:app), then reload this page.</p>
          </div>
        ) : ready && selected.length === 0 ? (
          <div className="notice">
            <p>No journals are selected.</p>
            <button type="button" className="primary" onClick={() => setPicking(true)}>Choose journals</button>
          </div>
        ) : (
          <>
          <SinceBar count={feed.newCount} baseline={baseline}>
            <ViewSwitch value={view === "list" ? "list" : "grid"} onChange={setView} />
          </SinceBar>
          <JournalStrip journals={stripJournals} counts={counts} newCounts={newCounts} focus={focused} onFocus={setFocus} />
          <Feed
            feed={feed}
            noun="article"
            gridClass={view === "list" ? "article-list" : "article-grid"}
            emptyText="No articles match these filters. Try more days, fewer topics or another search."
            render={(a) => (
              <ArticleCard key={a.article_id} a={a} layout={view} isNew={isNewSince(a.first_seen_at, baseline)} onZoom={setZoomed} />
            )}
          />
          </>
        )}
      </section>

      {zoomed && <Lightbox article={zoomed} onClose={() => setZoomed(null)} />}
      {picking && (
        <JournalPicker
          journals={journals}
          selected={selected}
          onChange={setChosen}
          onClose={() => setPicking(false)}
        />
      )}
      </div>
    </div>
  );
}
