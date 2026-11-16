import { useEffect, useState } from "react";
import { api } from "../api";
import { FAMILIES, topicLabel } from "../topics";
import { FEEDBACK_URL } from "../config";

const AUDIENCE = [
  { fam: "bio", title: "Industrial medicinal chemists", text: "Follow new targets, methods and competitors' molecules in papers and patents." },
  { fam: "materials", title: "Pharmaceutical research scientists", text: "Keep up with drug discovery, chemical biology, ADCs and degraders without a dozen alerts." },
  { fam: "computational", title: "Academic researchers", text: "PhD students, postdocs and faculty: a quick, free daily scan of new papers in your field." },
  { fam: "synthesis", title: "Chemists across fields", text: "Synthesis, catalysis, materials and OLED chemistry, filtered by topic." },
];

const WHY = [
  "New chemistry is scattered across many publisher sites, preprint servers and patent databases.",
  "Papers and patents are rarely seen side by side, yet both shape what chemists work on next.",
  "A graphical abstract shows the chemistry at a glance, so each article leads with its figure.",
];

const STEPS = [
  { fam: "bio", title: "Collect", text: "Every day, new articles are fetched from the publishers' own feeds, and new international (WO) patent applications from the European Patent Office." },
  { fam: "synthesis", title: "Sort", text: "Keyword rules on each title and abstract assign research topics; for patents, classification codes add antibody-drug conjugates, antibodies and OLED materials." },
  { fam: "materials", title: "Show", text: "Articles appear figure-first and patents grouped by publication week, with filters for journal, topic and date, and a link to every original." },
];

const SECTIONS = [
  { cls: "articles", title: "ASAP Articles", rows: [
    ["Sources", "Publishers' own feeds and open metadata services"],
    ["Window", "Published in the last 30 days"],
    ["Updated", "Daily, automatically"],
    ["Shows", "Graphical abstract, title, authors, abstract and topics, with a link to the article"],
  ] },
  { cls: "patents", title: "New Patents", rows: [
    ["Sources", "European Patent Office (Open Patent Services)"],
    ["Window", "WO applications published in the last 90 days"],
    ["Updated", "Daily, automatically"],
    ["Shows", "Title, applicants, abstract, publication number and topics, with a link to the full record at the EPO"],
  ] },
];

const FAQ = [
  ["Why do some articles have no figure?",
   "Some publishers' feeds don't include a graphical abstract, and some add it a few days after the article appears. Those cards say \"Figure expected in a few days\" and pick up the figure automatically once it is available."],
  ["Can I use the patent tab for freedom-to-operate?",
   "No. The patent tab is for awareness only: it lists new WO applications matched by keywords and classification codes, and it can miss relevant ones. It is not a freedom-to-operate or patentability search; for that, consult a patent professional."],
  ["Do I need an account?",
   "No. ASAP Chem Hub is free and has no sign-in. Your choices (journals, topics, layout, theme) and the \"new since your last visit\" markers are kept only in your own browser."],
  ["Is anything stored or redistributed?",
   "Figures are never stored or copied: they load straight from each publisher's own server. Titles, authors and abstracts from public feeds are kept for 30 days (patents for 90) so they can be searched and filtered, and every item links to the original."],
];

const n = (v) => (v === null || v === undefined ? "…" : Number(v).toLocaleString());
const sum = (rows) => rows.reduce((s, r) => s + r.n, 0);

export default function About({ active }) {
  const [opened, setOpened] = useState(active);
  const [stats, setStats] = useState({});
  const [articleTopics, setArticleTopics] = useState(null);
  const [patentTopics, setPatentTopics] = useState(null);

  useEffect(() => { if (active) setOpened(true); }, [active]);   // load on first visit to the tab
  useEffect(() => {
    if (!opened) return;
    Promise.allSettled([api.journals(), api.journalCounts({ days: 30 }), api.patentWeeks({ days: 90 }), api.topics(), api.patentTopics()])
      .then(([j, a, p, t, pt]) => {
        const ok = (r) => (r.status === "fulfilled" ? r.value : null);
        const at = ok(t), ptl = ok(pt);
        setArticleTopics(at); setPatentTopics(ptl);
        setStats({
          journals: ok(j)?.length,
          articles: ok(a) && sum(ok(a)),
          patents: ok(p) && sum(ok(p)),
          topics: at && ptl ? new Set([...at, ...ptl].map((x) => x.name)).size : undefined,
        });
      });
  }, [opened]);

  const patentOnly = (name) =>
    articleTopics && patentTopics && !articleTopics.some((t) => t.name === name) && patentTopics.some((t) => t.name === name);
  const articlesOnly = (name) =>
    articleTopics && patentTopics && articleTopics.some((t) => t.name === name) && !patentTopics.some((t) => t.name === name);
  const topicItems = (names, famId, inSubgroup) =>
    names.map((t) => (
      <li key={t} className={`fam-${famId}`}>
        {topicLabel(t, inSubgroup)}
        {patentOnly(t) && <span className="patent-only"> · patents only</span>}
        {articlesOnly(t) && <span className="patent-only"> · articles only</span>}
      </li>
    ));

  const TILES = [
    [n(stats.journals), "Journals"],
    [n(stats.articles), "Articles, last 30 days"],
    [n(stats.patents), "WO patents, last 90 days"],
    [n(stats.topics), "Research topics"],
    ["Daily", "Automatic updates"],
  ];

  return (
    <section className="about" hidden={!active}>
      <header className="about-head">
        <h2 className="section-title">About</h2>
        <div className="divider" aria-hidden="true"><span /></div>
        <p className="about-lede">
          The newest chemistry in one place: articles published ahead of print, with their graphical abstracts,
          and new international patent applications — sorted by research topic.
        </p>
      </header>

      <section className="about-sec" aria-labelledby="ab-who">
        <h3 id="ab-who" className="about-h">Who it's for</h3>
        <ul className="who-grid">
          {AUDIENCE.map((c) => (
            <li key={c.title} className={`who-card fam-${c.fam}`}>
              <h4>{c.title}</h4>
              <p>{c.text}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="about-sec" aria-labelledby="ab-why">
        <h3 id="ab-why" className="about-h">Why ASAP Chem Hub</h3>
        <ul className="why-list">
          {WHY.map((w) => <li key={w}>{w}</li>)}
        </ul>
        <p className="why-line">The newest papers and patents in chemistry, in one place, sorted by topic, figure-first and free.</p>
      </section>

      <section className="about-sec" aria-labelledby="ab-glance">
        <h3 id="ab-glance" className="about-h">At a glance</h3>
        <dl className="stat-grid">
          {TILES.map(([value, label]) => (
            <div key={label} className="stat">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="about-sec" aria-labelledby="ab-how">
        <h3 id="ab-how" className="about-h">How it works</h3>
        <ol className="steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className={`step fam-${s.fam}`}>
              <span className="step-n" aria-hidden="true">{i + 1}</span>
              <h4>{s.title}</h4>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="about-sec" aria-label="The two sections">
        <div className="sections-grid">
          {SECTIONS.map((s) => (
            <div key={s.title} className={`section-card section-card-${s.cls}`}>
              <h3 className="section-card-title">{s.title}</h3>
              <table>
                <tbody>
                  {s.rows.map(([k, v]) => (
                    <tr key={k}><th scope="row">{k}</th><td>{v}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </section>

      <section className="about-sec" aria-labelledby="ab-topics">
        <h3 id="ab-topics" className="about-h">Topics</h3>
        <div className="topic-cols">
          {FAMILIES.map((f) => (
            <div key={f.id} className={`topic-col fam-${f.id}`}>
              <h4>{f.name}</h4>
              {f.subgroups ? (
                f.subgroups.map((sg) => (
                  <div key={sg.name} className="topic-col-sub">
                    <h5>{sg.name}</h5>
                    <ul className="card-topics">{topicItems(sg.topics, f.id, true)}</ul>
                  </div>
                ))
              ) : (
                <ul className="card-topics">{topicItems(f.topics, f.id, false)}</ul>
              )}
            </div>
          ))}
        </div>
      </section>

      <section className="about-sec" aria-labelledby="ab-faq">
        <h3 id="ab-faq" className="about-h">Questions</h3>
        <div className="faq">
          {FAQ.map(([q, a]) => (
            <details key={q}>
              <summary>{q}</summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="about-sec help" aria-labelledby="ab-help">
        <h3 id="ab-help" className="about-h">Help shape ASAP Chem Hub</h3>
        <p>Missing a journal or a topic? Found something that could be better? Tell us.</p>
        <div className="help-actions">
          <a className="btn btn-primary" href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer">
            Suggest a journal or topic<span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          <a className="btn btn-secondary" href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer">
            Send feedback<span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        </div>
      </section>

      <section className="about-sec who-made" aria-labelledby="ab-made">
        <h3 id="ab-made" className="about-h">Who made it</h3>
        <p>
          Designed and built by Vijayarajan Devannah, a PhD synthetic organic chemist (medicinal and OLED chemistry)
          and data engineer.
        </p>
      </section>
    </section>
  );
}
