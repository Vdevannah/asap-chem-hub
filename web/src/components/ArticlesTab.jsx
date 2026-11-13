import { useEffect, useState } from "react";
import { api } from "../api";
import { useDebounced, useFeed, useStoredState } from "../hooks";
import { ArticleCard } from "./Cards";
import { DayRange, SearchBox, TopicChips } from "./Filters";
import JournalPicker from "./JournalPicker";
import Feed from "./Feed";
import Sidebar from "./Sidebar";

export default function ArticlesTab({ active }) {
  const [journals, setJournals] = useState([]);
  const [topics, setTopics] = useState([]);
  const [setupError, setSetupError] = useState(null);
  const [chosen, setChosen] = useStoredState("asap.journals", null); // null = defaults
  const [topicIds, setTopicIds] = useStoredState("asap.articleTopics", []);
  const [days, setDays] = useStoredState("asap.articleDays", 7);
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(false);
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

  const feed = useFeed(
    api.articles,
    { journals: [...selected].sort((a, b) => a - b), topics: topicIds, days, q },
    ready && selected.length > 0,
  );

  return (
    <div className="layout" hidden={!active}>
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
        <TopicChips topics={topics} selected={topicIds} onChange={setTopicIds} />
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
          <Feed
            feed={feed}
            noun="article"
            gridClass="article-grid"
            emptyText="No articles match these filters. Try more days, fewer topics or another search."
            render={(a) => <ArticleCard key={a.article_id} a={a} />}
          />
        )}
      </section>

      {picking && (
        <JournalPicker
          journals={journals}
          selected={selected}
          onChange={setChosen}
          onClose={() => setPicking(false)}
        />
      )}
    </div>
  );
}
