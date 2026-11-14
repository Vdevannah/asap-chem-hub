import { useEffect, useRef } from "react";
import { formatDate } from "../api";
import RichText from "./RichText";

// Enlarged graphical abstract in a modal <dialog>. Esc, the × button or a click on the backdrop closes it;
// the browser keeps keyboard focus inside while it is open and returns it to the figure afterwards.
export default function Lightbox({ article: a, onClose }) {
  const dialog = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const d = dialog.current;
    if (!d.open) d.showModal();
    const close = () => closeRef.current();
    d.addEventListener("close", close);
    return () => d.removeEventListener("close", close);
  }, []);

  // a click on the dialog element itself (not its content) is a click on the backdrop
  const onClick = (e) => { if (e.target === dialog.current) dialog.current.close(); };

  return (
    <dialog ref={dialog} className="lightbox" aria-labelledby="lightbox-title" onClick={onClick}>
      <div className="lightbox-inner">
        <button type="button" className="lightbox-close" aria-label="Close" onClick={() => dialog.current.close()}>
          ×
        </button>
        <div className="lightbox-tile">
          <img src={a.image_url} alt={`Graphical abstract: ${a.title.replace(/<[^>]+>/g, "")}`} referrerPolicy="no-referrer" />
        </div>
        <div className="lightbox-caption">
          <p id="lightbox-title" className="lightbox-title"><RichText html={a.title} /></p>
          <p className="meta">
            <span className="journal">{a.journal}</span>
            <time dateTime={a.published_date}>{formatDate(a.published_date)}</time>
          </p>
          <a className="lightbox-link" href={a.article_url} target="_blank" rel="noopener noreferrer">
            Open article<span className="visually-hidden"> (opens in a new tab)</span>
          </a>
        </div>
      </div>
    </dialog>
  );
}
