import { useEffect, useRef, useState } from "react";
import { formatDate, plainText } from "../api";
import RichText from "./RichText";
import { familyOf } from "../topics";
import { splitApplicants, titleCaseName } from "../names";

// Ordinary 2-3 letter English words; any other 2-3 letter word in a title is treated as an acronym.
const SHORT_WORDS = new Set(
  ("a an and as at by for in its of on or the to use via new low two one non all any per end top kit ion " +
   "oil gas dye due are has his may can set but not few own raw dry wet hot air sea ice day way out off up " +
   "our is be it so no").split(" "),
);

// Keep one hyphen-separated part upper case? "HLA", "MET" yes; "OF", "ANTI" no.
function isAcronym(part) {
  const core = part.replace(/^[^A-Za-z]+|[^A-Za-z]+$/g, "");
  return /^[A-Z]{2,3}$/.test(core) && !SHORT_WORDS.has(core.toLowerCase());
}

// EPO titles are ALL CAPS. Show them in sentence case, but keep as they are: words with digits
// (KAT6, IL-7, GLP-1), roman numerals (I, II, IV) and 2-3 letter acronyms (APJ, ANTI-HLA, C-MET).
function sentenceCase(t) {
  if (!t || t !== t.toUpperCase()) return t;
  const word = (w) => {
    if (/\d/.test(w) || (/^[IVX]+[,;:)]?$/.test(w) && w !== "A")) return w;
    return w.split("-").map((p) => (isAcronym(p) ? p : p.toLowerCase())).join("-");
  };
  const out = t.split(" ").map(word).join(" ");
  return out.charAt(0).toUpperCase() + out.slice(1);
}

function Topics({ topics }) {
  if (!topics?.length) return null;
  return (
    <ul className="card-topics">
      {topics.map((t) => <li key={t} className={`fam-${familyOf(t)}`}>{t}</li>)}
    </ul>
  );
}

const NewBadge = () => <span className="new-badge">New</span>;

// onZoom(a): open the figure in the lightbox. The figure itself no longer links to the article
// (the title does, and the lightbox has "Open article").
export function ArticleCard({ a, isNew = false, layout = "grid", onZoom }) {
  const [broken, setBroken] = useState(false);
  const [open, setOpen] = useState(false);
  const showImage = a.image_url && !broken;
  const hasAbstract = !!plainText(a.abstract);
  const list = layout === "list";
  const toggle = hasAbstract && (
    <button type="button" className="text-button" aria-expanded={open} onClick={() => setOpen(!open)}>
      {open ? "Hide abstract" : list ? "Abstract" : "Show abstract"}
    </button>
  );
  const text = open && <p><RichText html={a.abstract} /></p>;
  return (
    <article className={list ? "article-row" : "article-card"}>
      {showImage ? (
        <button
          type="button"
          className="figure figure-zoom"
          onClick={() => onZoom?.(a)}
          aria-label={`Enlarge graphical abstract: ${plainText(a.title)}`}
          aria-haspopup="dialog"
        >
          <img src={a.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setBroken(true)} />
        </button>
      ) : (
        <div className="figure">
          <span className="no-figure">
            <span className="no-figure-journal">{a.journal}</span>
            <span className="no-figure-note">
              {a.figure_status === "pending" ? "Figure expected in a few days" : "No graphical abstract"}
            </span>
          </span>
        </div>
      )}
      <div className="card-body">
        <p className="meta">
          {isNew && <NewBadge />}
          <span className="journal">{a.journal}</span>
          <time dateTime={a.published_date}>{formatDate(a.published_date)}</time>
        </p>
        <h3 className="title">
          <a href={a.article_url} target="_blank" rel="noopener noreferrer"><RichText html={a.title} /></a>
        </h3>
        {a.authors && <p className="authors">{a.authors}</p>}
        <Topics topics={a.topics} />
        {list ? text && <div className="abstract">{text}</div> : hasAbstract && <div className="abstract">{toggle}{text}</div>}
      </div>
      {list && <div className="row-toggle">{toggle}</div>}
    </article>
  );
}

// Abstract clamped to two lines, with "Show more" only when there is more to show.
function ClampedAbstract({ html }) {
  const [open, setOpen] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (el && !open) setOverflows(el.scrollHeight > el.clientHeight + 1);
  }, [html, open]);
  if (!plainText(html)) return null;
  return (
    <div className="pc-abstract">
      <p ref={ref} className={open ? "" : "clamped"}><RichText html={html} /></p>
      {(overflows || open) && (
        <button type="button" className="text-button" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  );
}

export function PatentCard({ p, isNew = false }) {
  const applicants = splitApplicants(p.applicants);
  return (
    <article className="patent-card">
      <div className="pc-main">
        <h3 className="title">
          <a href={p.patent_url} target="_blank" rel="noopener noreferrer">
            {sentenceCase(p.title) || "Untitled"}
          </a>
        </h3>
        <ClampedAbstract html={p.abstract} />
        <Topics topics={p.topics} />
      </div>
      <aside className="pc-side">
        {applicants.length > 0 && (
          <p className="pc-applicant">{applicants.map(titleCaseName).join("; ")}</p>
        )}
        <p className="pc-pn">
          {isNew && <NewBadge />}
          <span className="pn">{p.publication_number}</span>
        </p>
        {p.patent_url && (
          <a className="pc-link" href={p.patent_url} target="_blank" rel="noopener noreferrer">
            Espacenet<span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        )}
      </aside>
    </article>
  );
}
