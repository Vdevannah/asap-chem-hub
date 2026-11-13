import { useEffect, useState } from "react";
import { api } from "../api";
import { useDebounced, useFeed, useStoredState } from "../hooks";
import { PatentCard } from "./Cards";
import { DayRange, SearchBox, TopicChips } from "./Filters";
import Feed from "./Feed";
import Sidebar from "./Sidebar";

export default function PatentsTab({ active }) {
  const [topics, setTopics] = useState([]);
  const [setupError, setSetupError] = useState(null);
  const [topicIds, setTopicIds] = useStoredState("asap.patentTopics", []);
  const [days, setDays] = useStoredState("asap.patentDays", 30);
  const [query, setQuery] = useState("");
  const [opened, setOpened] = useState(active);
  const q = useDebounced(query.trim());

  useEffect(() => { if (active) setOpened(true); }, [active]);   // load on first visit to the tab
  useEffect(() => {
    if (!opened) return;
    api.patentTopics().then(setTopics).catch((e) => setSetupError(e.message));
  }, [opened]);

  const known = new Set(topics.map((t) => t.topic_id));
  const chosenTopics = topics.length ? topicIds.filter((id) => known.has(id)) : topicIds;
  const feed = useFeed(api.patents, { topics: chosenTopics, days, q }, opened);

  return (
    <div className="layout patents" hidden={!active}>
      <Sidebar label="Patent filters" active={chosenTopics.length + (q ? 1 : 0)}>
        <SearchBox value={query} onChange={setQuery} placeholder="Title, applicant or abstract" />
        <DayRange options={[7, 30, 90]} value={days} onChange={setDays} />
        <TopicChips topics={topics} selected={chosenTopics} onChange={setTopicIds} />
        <p className="hint disclaimer">
          New WO (PCT) applications from the European Patent Office, for awareness only. Not a freedom-to-operate
          or patentability search.
        </p>
      </Sidebar>

      <section className="results" aria-live="polite">
        {setupError ? (
          <div className="notice">
            <p>The patent list could not load: {setupError}.</p>
            <p>Check that the API is running, then reload this page.</p>
          </div>
        ) : (
          <Feed
            feed={feed}
            noun="patent"
            gridClass="patent-list"
            emptyText="No patents match these filters. Try more days, fewer topics or another search."
            render={(p) => <PatentCard key={p.patent_id} p={p} />}
          />
        )}
      </section>
    </div>
  );
}
