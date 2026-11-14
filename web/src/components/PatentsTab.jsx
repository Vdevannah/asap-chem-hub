import { Fragment, useEffect, useState } from "react";
import { api } from "../api";
import { useDebounced, useFeed, useStoredState } from "../hooks";
import { PatentCard } from "./Cards";
import { DayRange, SearchBox, TopicChips } from "./Filters";
import Feed from "./Feed";
import Sidebar from "./Sidebar";
import SinceBar from "./SinceBar";
import ChipStrip from "./ChipStrip";
import { dayMonthYear, titleCaseName } from "../names";
import { getBaseline, isNewSince } from "../visits";

const baseline = getBaseline();   // fixed for this page load

export default function PatentsTab({ active }) {
  const [topics, setTopics] = useState([]);
  const [setupError, setSetupError] = useState(null);
  const [topicIds, setTopicIds] = useStoredState("asap.patentTopics", []);
  const [days, setDays] = useStoredState("asap.patentDays", 30);
  const [query, setQuery] = useState("");
  const [opened, setOpened] = useState(active);
  const [topicCounts, setTopicCounts] = useState(null);
  const [applicant, setApplicant] = useState(null);     // one cleaned applicant name, or null = all
  const [applicants, setApplicants] = useState([]);
  const [allTotal, setAllTotal] = useState(null);       // patents under the filters, any applicant
  const [weeks, setWeeks] = useState({});               // { "2026-11-05": 201 } for the list headers
  const q = useDebounced(query.trim());

  useEffect(() => { if (active) setOpened(true); }, [active]);   // load on first visit to the tab
  useEffect(() => {
    if (!opened) return;
    api.patentTopics().then(setTopics).catch((e) => setSetupError(e.message));
  }, [opened]);

  // live per-topic counts for the chips (same days / search)
  useEffect(() => {
    if (!opened) return;
    let live = true;
    api.patentTopicCounts({ days, q })
      .then((rows) => { if (live) setTopicCounts(Object.fromEntries(rows.map((r) => [r.topic_id, r.n]))); })
      .catch(() => { if (live) setTopicCounts(null); });
    return () => { live = false; };
  }, [opened, days, q]);

  const known = new Set(topics.map((t) => t.topic_id));
  const chosenTopics = topics.length ? topicIds.filter((id) => known.has(id)) : topicIds;
  const base = { topics: chosenTopics, days, q };
  const baseKey = JSON.stringify(base);

  // top applicants and the "All" total (both ignore the applicant filter)
  useEffect(() => {
    if (!opened) return;
    let live = true;
    Promise.all([api.patentApplicants(base), api.patentWeeks(base)])
      .then(([a, w]) => {
        if (!live) return;
        setApplicants(a);
        setAllTotal(w.reduce((s, r) => s + r.n, 0));
      })
      .catch(() => { if (live) { setApplicants([]); setAllTotal(null); } });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, baseKey]);

  // per-week counts for the list headers (with the applicant filter, if any)
  useEffect(() => {
    if (!opened) return;
    let live = true;
    api.patentWeeks({ ...base, applicant })
      .then((w) => { if (live) setWeeks(Object.fromEntries(w.map((r) => [r.published_date, r.n]))); })
      .catch(() => { if (live) setWeeks({}); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened, baseKey, applicant]);

  const feed = useFeed(api.patents, { ...base, since: baseline, applicant }, opened);

  // keep a chosen applicant visible even if it drops out of the top 12 under new filters
  const chipItems = applicants.map((a) => ({ id: a.name, label: titleCaseName(a.name), n: a.n }));
  if (applicant && !chipItems.some((c) => c.id.toLowerCase() === applicant.toLowerCase())) {
    chipItems.unshift({ id: applicant, label: titleCaseName(applicant), n: feed.total });
  }

  const renderPatent = (p, i) => {
    const prev = feed.items[i - 1];
    const newWeek = !prev || prev.published_date !== p.published_date;
    const n = weeks[p.published_date];
    return (
      <Fragment key={p.patent_id}>
        {newWeek && (
          <h3 className="week-head">
            <span className="week-date">Published {dayMonthYear(p.published_date)}</span>
            {n !== undefined && <span className="week-n">{n.toLocaleString()} patent{n === 1 ? "" : "s"}</span>}
          </h3>
        )}
        <PatentCard p={p} isNew={isNewSince(p.first_seen_at, baseline)} />
      </Fragment>
    );
  };

  return (
    <div className="section" hidden={!active}>
      <header className="tab-head">
        <h2 className="tab-heading">New Patents</h2>
        <div className="divider" aria-hidden="true"><span /></div>
      </header>
      <div className="layout patents">
      <Sidebar label="Patent filters" active={chosenTopics.length + (q ? 1 : 0)}>
        <SearchBox value={query} onChange={setQuery} placeholder="Title, applicant or abstract" />
        <DayRange options={[7, 30, 90]} value={days} onChange={setDays} />
        <TopicChips topics={topics} selected={chosenTopics} onChange={setTopicIds} counts={topicCounts} />
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
          <>
          <SinceBar count={feed.newCount} baseline={baseline} />
          <div className="applicant-row">
            <p className="strip-label">Top applicants, last {days} days</p>
            <ChipStrip
              items={chipItems}
              all={{ n: allTotal }}
              focus={applicant}
              onFocus={setApplicant}
              ariaLabel="Show one applicant"
              noun="applicants"
            />
          </div>
          <Feed
            feed={feed}
            noun="patent"
            gridClass="patent-list"
            emptyText="No patents match these filters. Try more days, fewer topics or another search."
            render={renderPatent}
          />
          </>
        )}
      </section>
      </div>
    </div>
  );
}
