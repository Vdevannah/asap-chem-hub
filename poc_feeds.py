"""
ASAP Chem Hub - Proof of Concept
===================================
Question this script answers:
    "How many new articles can we show WITH a graphical abstract,
     using only the publishers' own RSS feeds?"

What it does
    1. Downloads the RSS feed for each journal in JOURNALS.
    2. For every article, extracts title, authors, date, DOI, abstract
       and the graphical-abstract image URL (if the feed provides one).
    3. Optionally fills missing authors/dates from the Crossref API.
    4. Tags each article with research topics (PROTAC, covalent, ...)
       using simple keyword/synonym rules - no LLM.
    5. Prints a coverage report per journal and writes:
         - poc_results.csv  (one row per article)
         - preview.html     (open in a browser to eyeball the figures)

Images are NOT downloaded or stored - the preview page links to the
publisher's own image URL, exactly as the feed provides it.

Usage
    pip install -r requirements.txt
    python poc_feeds.py                 # feeds only
    python poc_feeds.py --crossref      # also fill gaps from Crossref

Optional: set CROSSREF_MAILTO=you@example.com so Crossref puts you in
its "polite" pool (faster, more reliable).
"""

import argparse
import csv
import html
import os
import re
import sys
import time
from urllib.parse import urljoin

import feedparser
import requests

# ---------------------------------------------------------------------------
# 1. Journals to test.  Feed URLs should be double-checked on each
#    publisher's "RSS" page - the script reports any feed that fails.
# ---------------------------------------------------------------------------
ACS = "https://pubs.acs.org/rss/{code}/asap.xml"
WILEY = "https://onlinelibrary.wiley.com/action/showFeed?jc={code}&type=etoc&feed=rss"
RSC = "http://feeds.rsc.org/rss/{code}"
NATURE = "https://www.nature.com/{code}.rss"
# ChemRxiv blocks scripts on its own API, so preprints come from Crossref
# (every ChemRxiv DOI starts with 10.26434).
CHEMRXIV = "https://api.crossref.org/works"

JOURNALS = [
    # (display name,                    publisher,         feed URL)
    # --- ACS ---
    ("JACS",                            "ACS",             ACS.format(code="jacsat")),
    ("ACS Central Science",             "ACS",             ACS.format(code="acscii")),
    ("JACS Au",                         "ACS",             ACS.format(code="jaaucr")),
    ("Org. Lett.",                      "ACS",             ACS.format(code="orlef7")),
    ("J. Org. Chem.",                   "ACS",             ACS.format(code="joceah")),
    ("Org. Process Res. Dev.",          "ACS",             ACS.format(code="oprdfk")),
    ("J. Med. Chem.",                   "ACS",             ACS.format(code="jmcmar")),
    ("ACS Med. Chem. Lett.",            "ACS",             ACS.format(code="amclct")),
    ("J. Nat. Prod.",                   "ACS",             ACS.format(code="jnprdf")),
    ("ACS Catalysis",                   "ACS",             ACS.format(code="accacs")),
    ("Organometallics",                 "ACS",             ACS.format(code="orgnd7")),
    ("Chem. Rev.",                      "ACS",             ACS.format(code="chreay")),
    ("Acc. Chem. Res.",                 "ACS",             ACS.format(code="achre4")),
    # --- Wiley ---
    ("Angew. Chem. Int. Ed.",           "Wiley",           WILEY.format(code="15213773")),
    ("Chem. Eur. J.",                   "Wiley",           WILEY.format(code="15213765")),
    ("Eur. J. Org. Chem.",              "Wiley",           WILEY.format(code="10990690")),
    ("Adv. Synth. Catal.",              "Wiley",           WILEY.format(code="16154169")),
    ("ChemMedChem",                     "Wiley",           WILEY.format(code="18607187")),
    ("ChemBioChem",                     "Wiley",           WILEY.format(code="14397633")),
    ("ChemCatChem",                     "Wiley",           WILEY.format(code="18673899")),
    # --- RSC ---
    ("Chemical Science",                "RSC",             RSC.format(code="sc")),
    ("Chem. Commun.",                   "RSC",             RSC.format(code="cc")),
    ("Org. Biomol. Chem.",              "RSC",             RSC.format(code="ob")),
    ("Org. Chem. Front.",               "RSC",             RSC.format(code="qo")),
    ("RSC Med. Chem.",                  "RSC",             RSC.format(code="md")),
    ("RSC Chem. Biol.",                 "RSC",             RSC.format(code="cb")),
    ("Chem. Soc. Rev.",                 "RSC",             RSC.format(code="cs")),
    ("Nat. Prod. Rep.",                 "RSC",             RSC.format(code="np")),
    # --- Springer Nature (to test) ---
    ("Nature",                          "Springer Nature", "https://www.nature.com/nature.rss"),
    ("Nat. Commun. (chemistry)",        "Springer Nature", "https://www.nature.com/subjects/chemistry/ncomms.rss"),
    ("Nature Chemistry",                "Springer Nature", NATURE.format(code="nchem")),
    ("Nature Synthesis",                "Springer Nature", NATURE.format(code="natsynth")),
    ("Nature Catalysis",                "Springer Nature", NATURE.format(code="natcatal")),
    ("Nature Reviews Chemistry",        "Springer Nature", NATURE.format(code="natrevchem")),
    # --- AAAS (to test) ---
    ("Science (First Release)",         "AAAS",            "https://feeds.science.org/rss/science-aop.xml"),
    ("Science (latest issue)",          "AAAS",            "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science"),
    # --- Preprints (to test) - JSON API, not RSS ---
    ("ChemRxiv",                        "ChemRxiv",        CHEMRXIV),
]

# 2. Topic rules live in topics.py (shared with tune_topics.py and, later, the app)
from topics import TOPICS, tag_topics

HEADERS = {
    "User-Agent": "ASAPChemHub-PoC/0.1 (academic literature feed prototype)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#]+", re.IGNORECASE)
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def entry_html(entry) -> str:
    """All HTML-ish text the feed gave us for this entry."""
    parts = [entry.get("summary", "")]
    for c in entry.get("content", []) or []:
        parts.append(c.get("value", ""))
    return " ".join(parts)


def find_image(entry, base_url: str) -> str:
    """Graphical-abstract URL from the feed, checked in order of reliability."""
    # a) <media:content> / <media:thumbnail>
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return urljoin(base_url, m["url"])
    # b) <enclosure type="image/...">
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return urljoin(base_url, enc["href"])
    # c) <img src="..."> inside the description HTML (ACS / RSC style)
    m = IMG_RE.search(entry_html(entry))
    if m:
        return urljoin(base_url, html.unescape(m.group(1)))
    return ""


NATURE_LINK_RE = re.compile(r"nature\.com/articles/([^?#/\s]+)", re.IGNORECASE)


def find_doi(entry) -> str:
    """DOI from dedicated fields first, then from the link or text."""
    m = NATURE_LINK_RE.search(str(entry.get("link", "")))
    if m:  # nature.com/articles/s41586-026-01234-5  ->  10.1038/s41586-026-01234-5
        return "10.1038/" + m.group(1)
    for key in ("prism_doi", "dc_identifier", "id", "link"):
        m = DOI_RE.search(str(entry.get(key, "")))
        if m:
            return m.group(0).rstrip(".")
    m = DOI_RE.search(entry_html(entry))
    return m.group(0).rstrip(".") if m else ""


def find_authors(entry) -> str:
    if entry.get("authors"):
        names = [a.get("name", "") for a in entry["authors"] if a.get("name")]
        if names:
            return "; ".join(names)
    return entry.get("author", "") or entry.get("dc_creator", "")


def find_date(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return time.strftime("%Y-%m-%d", t)
    return entry.get("prism_publicationdate", "") or entry.get("dc_date", "")


def crossref_fill(article: dict, session: requests.Session) -> None:
    """Fill missing authors/date from Crossref (metadata only)."""
    if not article["doi"] or (article["authors"] and article["date"] and len(article["abstract"]) > 100):
        return
    params = {}
    if os.environ.get("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]
    try:
        r = session.get(f"https://api.crossref.org/works/{article['doi']}",
                        params=params, timeout=20)
        if r.status_code != 200:
            return
        msg = r.json()["message"]
        if not article["authors"]:
            article["authors"] = "; ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get("author", [])
            )
        if not article["date"]:
            parts = (msg.get("published-online") or msg.get("issued") or {}).get("date-parts", [[]])[0]
            article["date"] = "-".join(f"{p:02d}" for p in parts)
        if len(article["abstract"]) <= 100 and msg.get("abstract"):
            article["abstract"] = strip_html(msg["abstract"])
            article["topics"] = tag_topics(article['title'], article['abstract'])
        article["source_note"] += " +crossref"
    except (requests.RequestException, ValueError, KeyError):
        pass
    time.sleep(0.2)  # be polite


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def fetch_chemrxiv(name, publisher, url, session):
    """Latest ChemRxiv preprints from Crossref (no images)."""
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 7 * 86400))
    params = {"filter": f"prefix:10.26434,type:posted-content,from-created-date:{since}",
              "sort": "created", "order": "desc", "rows": 200, "cursor": "*"}
    if os.environ.get("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]
    items = []
    try:
        for _ in range(10):                       # up to 2,000 preprints
            r = session.get(url, params=params, timeout=60, headers={"Accept": "application/json"})
            r.raise_for_status()
            msg = r.json()["message"]
            items.extend(msg["items"])
            if len(msg["items"]) < params["rows"] or not msg.get("next-cursor"):
                break
            params["cursor"] = msg["next-cursor"]
            time.sleep(0.5)
    except (requests.RequestException, ValueError, KeyError) as e:
        if not items:
            return None, f"FAILED to fetch ChemRxiv via Crossref: {e}", []
    if not items:
        return None, "Crossref returned no ChemRxiv items for the last 7 days", []

    # each version (v1, v2 ...) has its own DOI - keep only the newest version
    latest = {}
    for it in items:
        doi = it.get("DOI", "")
        m = re.match(r"(.+?)[-/]v(\d+)$", doi)   # both ...-v2 and .../v2 styles
        base, ver = (m.group(1), int(m.group(2))) if m else (doi, 1)
        if base not in latest or ver > latest[base][0]:
            latest[base] = (ver, it)
    items, titles = [], set()
    for _, it in latest.values():                 # also drop the same preprint under two DOIs
        key = re.sub(r"\W+", "", " ".join(it.get("title", [])).lower())
        if key and key in titles:
            continue
        titles.add(key)
        items.append(it)

    articles = []
    for it in items:
        title = strip_html(" ".join(it.get("title", [])))
        abstract = strip_html(it.get("abstract", ""))
        parts = (it.get("posted") or it.get("created") or {}).get("date-parts", [[]])[0]
        articles.append({
            "journal": name, "publisher": publisher, "title": title,
            "authors": "; ".join(f"{x.get('given', '')} {x.get('family', '')}".strip()
                                 for x in it.get("author", [])),
            "date": "-".join(f"{p:02d}" for p in parts),
            "doi": it.get("DOI", ""),
            "link": f"https://doi.org/{it.get('DOI', '')}",
            "image_url": "", "abstract": abstract,
            "topics": tag_topics(title, abstract),
            "source_note": "crossref",
        })
    return articles, None, sorted({it.get("subtype", "") or it.get("type", "") for it in items} - {""})


NON_RESEARCH = re.compile(r"\b(news|editorial|career|correction|retraction|erratum|"
                          r"podcast|letters?|books?|policy forum|in brief|outlook|obituary|"
                          r"working life|in other journals|this week)\b", re.IGNORECASE)


NOT_A_PAPER = re.compile(r"^\s*(author correction|publisher correction|correction|corrigendum|"
                         r"retraction|retracted|erratum|addendum|expression of concern|"
                         r"(inside |outside )?(front|back) cover|cover picture|cover feature|"
                         r"frontispiece|table of contents|masthead|issue information)\b",
                         re.IGNORECASE)


def is_research(name, e) -> bool:
    """Drop corrections, covers etc. everywhere; keep only research from Nature/Science."""
    if NOT_A_PAPER.search(strip_html(e.get("title", ""))):
        return False
    if name == "Nature":
        # Nature research papers have DOIs s41586-...; news and comment are d41586-...
        return "/articles/s41586" in str(e.get("link", ""))
    if name.startswith("Science"):
        if name == "Science (First Release)":
            return True            # First Release is research papers only
        labels = " ".join([str(e.get("dc_type", "")), str(e.get("prism_section", "")),
                           str(e.get("category", ""))] +
                          [t.get("term", "") for t in e.get("tags", []) or []]).strip()
        if labels:                 # the feed says what each item is
            return bool(re.search(r"research article|report", labels, re.IGNORECASE))
        # No labels: research papers have a DOI and a full abstract; news has no DOI,
        # and letters, editorials and summaries have only a few lines.
        return bool(find_doi(e)) and len(strip_html(entry_html(e))) >= 700
    return True


def fetch_journal(name, publisher, url, session):
    """Returns (articles, error, categories seen in the feed)."""
    if publisher == "ChemRxiv":
        return fetch_chemrxiv(name, publisher, url, session)
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        return None, f"FAILED to fetch feed: {e}", []

    feed = feedparser.parse(r.content)
    if not feed.entries:
        return None, "Feed downloaded but has no entries (check URL/format)", []

    articles, categories, skipped = [], set(), 0
    for e in feed.entries:
        # Research articles only for Nature and Science (no news, editorials, careers)
        if not is_research(name, e):
            skipped += 1
            continue
        for t in e.get("tags", []) or []:
            if t.get("term"):
                categories.add(t["term"])
        if e.get("dc_type"):
            categories.add(e["dc_type"])
        abstract = strip_html(entry_html(e))
        title = strip_html(e.get("title", ""))
        articles.append({
            "journal": name,
            "publisher": publisher,
            "title": title,
            "authors": find_authors(e),
            "date": find_date(e),
            "doi": find_doi(e),
            "link": e.get("link", ""),
            "image_url": find_image(e, url),
            "abstract": abstract,
            "topics": tag_topics(title, abstract),
            "source_note": "feed",
        })
    if name == "Science (latest issue)" and articles:
        # The TOC feed labels article types but has no images; the other Science
        # issue feed has images but no labels. Match the two by DOI.
        try:
            r2 = session.get("https://feeds.science.org/rss/science.xml", timeout=30)
            r2.raise_for_status()
            imgs = {find_doi(e2): find_image(e2, r2.url) for e2 in feedparser.parse(r2.content).entries}
            for a in articles:
                a["image_url"] = a["image_url"] or imgs.get(a["doi"], "")
        except requests.RequestException:
            pass
    if skipped:
        categories.add(f"[skipped {skipped} non-research items]")
    if not articles:
        return None, f"All {skipped} items were non-research", sorted(categories)
    return articles, None, sorted(categories)


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "   - "


def write_preview(articles, path="preview.html"):
    """Simple local page that hotlinks the publisher images."""
    cards = []
    for a in articles:
        img = (f'<img src="{html.escape(a["image_url"])}" loading="lazy">'
               if a["image_url"] else '<div class="noimg">No graphical abstract in feed</div>')
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in a["topics"])
        href = html.escape(a["link"] or (f"https://doi.org/{a['doi']}" if a["doi"] else "#"))
        cards.append(f"""
        <div class="card">
          <div class="fig">{img}</div>
          <div class="meta">
            <div class="j">{html.escape(a['journal'])} · {html.escape(a['date'])}</div>
            <a href="{href}" target="_blank">{html.escape(a['title'])}</a>
            <div class="au">{html.escape(a['authors'])}</div>
            <div>{tags}</div>
          </div>
        </div>""")
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>ASAP Chem Hub PoC</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#f4f5f7;margin:0;padding:16px}}
 .card{{display:flex;gap:16px;background:#fff;border-radius:10px;padding:14px;margin:12px auto;max-width:1000px}}
 .fig{{flex:0 0 340px;display:flex;align-items:center;justify-content:center}}
 .fig img{{max-width:340px;max-height:200px}}
 .noimg{{color:#999;font-size:13px}}
 .j{{color:#666;font-size:13px}} .au{{color:#444;font-size:13px;margin:4px 0}}
 a{{font-weight:600;color:#1a3d7c;text-decoration:none}}
 .tag{{display:inline-block;background:#e8eefc;color:#1a3d7c;border-radius:10px;padding:2px 8px;margin:2px;font-size:12px}}
 @media(max-width:700px){{.card{{flex-direction:column}} .fig{{flex:none}}}}
</style></head><body><h2 style="max-width:1000px;margin:auto">ASAP Chem Hub – feed PoC ({len(articles)} articles)</h2>
{''.join(cards)}</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crossref", action="store_true",
                    help="fill missing authors/dates/abstracts from Crossref for ALL journals "
                         "(always on for Nature and Science)")
    ap.add_argument("--only", default="",
                    help='test only some publishers, e.g. --only "Springer Nature,AAAS,ChemRxiv"')
    args = ap.parse_args()
    wanted = {p.strip().lower() for p in args.only.split(",") if p.strip()}

    session = requests.Session()
    session.headers.update(HEADERS)

    all_articles, rows, category_report = [], [], []
    for name, publisher, url in JOURNALS:
        if wanted and publisher.lower() not in wanted:
            continue
        print(f"Fetching {name} ...", flush=True)
        articles, err, cats = fetch_journal(name, publisher, url, session)
        if cats and publisher in ("Springer Nature", "AAAS", "ChemRxiv"):
            category_report.append((name, cats))
        if err:
            rows.append((name, err))
            continue
        if args.crossref or publisher in ("Springer Nature", "AAAS"):
            for a in articles:
                crossref_fill(a, session)
        seen = {a["doi"] for a in all_articles if a["doi"]}
        articles = [a for a in articles if not a["doi"] or a["doi"] not in seen]
        all_articles.extend(articles)
        n = len(articles)
        rows.append((name, (
            f"{n:4d} articles | image {pct(sum(bool(a['image_url']) for a in articles), n)}"
            f" | abstract {pct(sum(len(a['abstract']) > 100 for a in articles), n)}"
            f" | DOI {pct(sum(bool(a['doi']) for a in articles), n)}"
            f" | authors {pct(sum(bool(a['authors']) for a in articles), n)}"
            f" | date {pct(sum(bool(a['date']) for a in articles), n)}"
        )))
        time.sleep(1)  # polite gap between requests

    # ---- Report -----------------------------------------------------------
    print("\n=== Feed coverage report ===")
    for name, line in rows:
        print(f"{name:26s} {line}")

    if category_report:
        print("\n=== Categories / fields seen (to design the chemistry filter) ===")
        for name, cats in category_report:
            print(f"{name}: {', '.join(cats[:25])}")

    if all_articles:
        total = len(all_articles)
        with_img = sum(bool(a["image_url"]) for a in all_articles)
        print(f"\nOVERALL: {total} articles, graphical abstract for {with_img} ({pct(with_img, total).strip()})")

        print("\n=== Topic matches (across ALL journals) ===")
        for topic in TOPICS:
            hits = [a for a in all_articles if topic in a["topics"]]
            print(f"\n{topic}: {len(hits)}")
            for a in hits[:10]:
                print(f"   [{a['journal']}] {a['title'][:110]}")

        with open("poc_results.csv", "w", newline="", encoding="utf-8") as f:
            fields = ["journal", "publisher", "date", "title", "authors", "doi",
                      "link", "image_url", "topics", "source_note", "abstract"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for a in all_articles:
                w.writerow({**a, "topics": "; ".join(a["topics"])})
        write_preview(all_articles)
        print("\nWrote poc_results.csv and preview.html (open preview.html in a browser)")
    else:
        print("\nNo articles retrieved - check feed URLs / network.")
        sys.exit(1)


if __name__ == "__main__":
    main()
