import { useState } from "react";
import { formatDate, plainText } from "../api";
import RichText from "./RichText";
import { familyOf } from "../topics";

// EPO titles are ALL CAPS. Show them in sentence case, but keep words with
// digits (KAT6, IL-7, GLP-1) and roman numerals (I, II, IV) as they are.
function sentenceCase(t) {
  if (!t || t !== t.toUpperCase()) return t;
  const keep = (w) => /\d/.test(w) || /^[IVX]+[,;:)]?$/.test(w) && w !== "A";
  const words = t.split(" ").map((w) => (keep(w) ? w : w.toLowerCase()));
  const out = words.join(" ");
  return out.charAt(0).toUpperCase() + out.slice(1);
}

function Abstract({ text, label }) {
  const [open, setOpen] = useState(false);
  if (!plainText(text)) return null;
  return (
    <div className="abstract">
      <button type="button" className="text-button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide abstract" : label}
      </button>
      {open && <p><RichText html={text} /></p>}
    </div>
  );
}

function Topics({ topics }) {
  if (!topics?.length) return null;
  return (
    <ul className="card-topics">
      {topics.map((t) => <li key={t} className={`fam-${familyOf(t)}`}>{t}</li>)}
    </ul>
  );
}

export function ArticleCard({ a }) {
  const [broken, setBroken] = useState(false);
  const showImage = a.image_url && !broken;
  return (
    <article className="article-card">
      <a className="figure" href={a.article_url} target="_blank" rel="noopener noreferrer" tabIndex={-1} aria-hidden="true">
        {showImage ? (
          <img src={a.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
        ) : (
          <span className="no-figure">
            <span className="no-figure-journal">{a.journal}</span>
            <span className="no-figure-note">
              {a.figure_status === "pending" ? "Figure expected in a few days" : "No graphical abstract"}
            </span>
          </span>
        )}
      </a>
      <div className="card-body">
        <p className="meta">
          <span className="journal">{a.journal}</span>
          <time dateTime={a.published_date}>{formatDate(a.published_date)}</time>
        </p>
        <h3 className="title">
          <a href={a.article_url} target="_blank" rel="noopener noreferrer"><RichText html={a.title} /></a>
        </h3>
        {a.authors && <p className="authors">{a.authors}</p>}
        <Topics topics={a.topics} />
        <Abstract text={a.abstract} label="Show abstract" />
      </div>
    </article>
  );
}

export function PatentCard({ p }) {
  return (
    <article className="patent-card">
      <p className="meta">
        <span className="pn">{p.publication_number}</span>
        <time dateTime={p.published_date}>Published {formatDate(p.published_date)}</time>
      </p>
      <h3 className="title">
        <a href={p.patent_url} target="_blank" rel="noopener noreferrer">
          {sentenceCase(p.title) || "Untitled"}
        </a>
      </h3>
      {p.applicants && <p className="applicants">{p.applicants.replace(/\s*\[[A-Z]{2}\]/g, "")}</p>}
      <Topics topics={p.topics} />
      <Abstract text={p.abstract} label="Show abstract" />
    </article>
  );
}
