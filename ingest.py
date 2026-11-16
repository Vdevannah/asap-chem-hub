"""
ASAP Chem Hub - ingestion pipeline (Phase 5)
============================================
Keeps the database fresh. Four jobs:

  articles  fetch every active journal in the `journals` table, add only NEW DOIs,
            fill gaps from Crossref (Nature, Science) and the Springer Meta API,
            tag topics. RSS items whose DOI we already have (e.g. from the Crossref
            backup) fill that article's empty abstract/figure/authors.
            Then, at most every 6 hours, a Crossref backup for ACS: articles from the
            last 7 days (by ISSN) that RSS missed, title-only, no figure. -> hourly
  figures   re-check open-access Nature articles marked 'pending' and add
            Figure 1 when Springer has indexed the full text;
            give up after 14 days.                               -> daily
  patents   search EPO for new WO patents (5 search streams, last 14 days,
            because EPO loads each weekly batch several days late),
            add only NEW publication numbers, tag topics.       -> daily
  cleanup   delete articles older than 30 days, patents older than 90.  -> daily

Every job writes one row to `ingestion_runs`. A failing feed is recorded in
journals.last_error and the other feeds carry on.

Usage
    python ingest.py articles                 # all active journals
    python ingest.py articles --only "ACS"    # one publisher (comma-separated list)
    python ingest.py figures
    python ingest.py patents                  # last 14 days
    python ingest.py patents --days 90        # first run: fill the whole 90-day window (~20 min)
    python ingest.py cleanup
    python ingest.py all                      # articles, figures, patents, cleanup
"""

import argparse
import os
import sys
import time

from datetime import date, timedelta

import requests

import epo
import poc_feeds as feeds
import springer
from load_poc import clean_abstract, connect, to_date
from topics import tag_topics

ARTICLE_DAYS = 30           # keep articles this long (by publication date)
PATENT_DAYS = 90
FIGURE_RETRY_DAYS = 14      # stop re-checking a 'pending' figure after this
FIGURE_RETRY_HOURS = 20     # re-check each pending figure at most once a day
STALE_DAYS = 14             # warn when a feed's newest article is older than this
PATENT_LOOKBACK_DAYS = 28   # EPO loads WO batches late, so look back two weeks
PATENT_OFFICE = "WO"
CROSSREF_BACKUP_HOURS = 6   # ACS Crossref backup: at most once per this many hours
CROSSREF_BACKUP_DAYS = 7    # ... looking back this many days (by publication date)


# ---------------------------------------------------------------------------
# ingestion_runs bookkeeping
# ---------------------------------------------------------------------------
def start_run(db, job):
    cur = db.cursor()
    cur.execute("INSERT INTO ingestion_runs (job) VALUES (%s)", (job,))
    db.commit()
    return cur.lastrowid


def finish_run(db, run_id, status, seen=0, new=0, deleted=0, notes=None):
    db.cursor().execute(
        """UPDATE ingestion_runs SET finished_at = NOW(), status = %s, items_seen = %s,
                  items_new = %s, items_deleted = %s, notes = %s WHERE run_id = %s""",
        (status, seen, new, deleted, (notes or None) and notes[:5000], run_id))
    db.commit()


# ---------------------------------------------------------------------------
# Job 1: articles
# ---------------------------------------------------------------------------
def job_articles(db, session, only=None):
    cur = db.cursor()
    run_id = start_run(db, "articles")
    cur.execute("SELECT journal_id, name, publisher, feed_url FROM journals WHERE is_active")
    journals = [j for j in cur.fetchall() if not only or j[2].lower() in only]
    cur.execute("SELECT name, topic_id FROM article_topics")
    topic_ids = dict(cur.fetchall())
    cur.execute("SELECT doi FROM articles")
    known = {row[0].lower() for row in cur.fetchall()}
    # Known articles with gaps (e.g. inserted by the Crossref backup): doi -> (has abstract, has figure,
    # has authors). When RSS brings one of them, fill only the empty fields.
    cur.execute("""SELECT doi, COALESCE(abstract, '') <> '', COALESCE(image_url, '') <> '',
                          COALESCE(authors, '') <> ''
                     FROM articles
                    WHERE COALESCE(abstract, '') = '' OR COALESCE(image_url, '') = ''
                       OR COALESCE(authors, '') = ''""")
    gaps = {row[0].lower(): row[1:] for row in cur.fetchall()}
    cutoff = to_date(time.strftime("%Y-%m-%d", time.gmtime(time.time() - ARTICLE_DAYS * 86400)))

    seen = new = filled = 0
    failed, stale = [], []
    windows = []                              # per feed: "name count@oldest", to spot feeds whose window
                                              # is shorter than the polling interval
    for journal_id, name, publisher, url in journals:
        print(f"  {name:28s}", end=" ", flush=True)
        items, err, _ = feeds.fetch_journal(name, publisher, url, session)
        if err:
            failed.append(f"{name}: {err[:120]}")
            cur.execute("UPDATE journals SET last_fetched_at = NOW(), last_error = %s WHERE journal_id = %s",
                        (err[:500], journal_id))
            db.commit()
            print("FAILED")
            continue

        dated = [to_date(a["date"]) for a in items if a.get("date")]
        windows.append(f"{name} {len(items)}@{min(dated):%m-%d}" if dated else f"{name} {len(items)}@?")

        # staleness check: a feed can "work" but stop updating (RSC, June 2026)
        newest = max((to_date(a["date"]) for a in items), default=None)
        stale_cutoff = to_date(time.strftime("%Y-%m-%d", time.gmtime(time.time() - STALE_DAYS * 86400)))
        warning = None
        if newest and newest < stale_cutoff:
            warning = f"STALE: newest article is {newest}"
            stale.append(f"{name} ({newest})")

        added = 0
        for a in items:
            seen += 1
            if not a["doi"]:
                continue
            if a["doi"].lower() in known:
                if a["doi"].lower() in gaps and fill_gaps(cur, a, gaps.pop(a["doi"].lower()), topic_ids):
                    filled += 1
                continue
            published = to_date(a["date"])
            if published < cutoff:            # older than the window - cleanup would delete it
                continue

            # fill gaps only for NEW articles (keeps API calls low)
            if publisher in ("Springer Nature", "AAAS"):
                feeds.crossref_fill(a, session)
            is_oa = None
            if publisher == "Springer Nature" and springer.enabled():
                try:
                    abstract, is_oa, _ = springer.meta_lookup(a["doi"], session)
                    if abstract and len(a["abstract"]) <= 100:
                        a["abstract"] = abstract
                except (requests.RequestException, ValueError):
                    pass

            abstract = clean_abstract(a["abstract"])
            image = a["image_url"] or None
            status = "found" if image else ("pending" if is_oa else "none")
            cur.execute(
                """INSERT IGNORE INTO articles
                     (doi, journal_id, title, authors, abstract, article_url, published_date,
                      image_url, image_source, figure_status, is_open_access)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (a["doi"], journal_id, a["title"][:1000], a["authors"], abstract,
                 a["link"] or f"https://doi.org/{a['doi']}", published,
                 image, "feed" if image else None, status, is_oa))
            known.add(a["doi"].lower())
            if cur.rowcount == 0:
                continue
            article_id = cur.lastrowid
            for topic in tag_topics(a["title"], abstract):
                if topic in topic_ids:
                    cur.execute("INSERT IGNORE INTO article_topic_links (article_id, topic_id) VALUES (%s, %s)",
                                (article_id, topic_ids[topic]))
            added += 1

        new += added
        cur.execute("UPDATE journals SET last_fetched_at = NOW(), last_error = %s WHERE journal_id = %s",
                    (warning, journal_id))
        db.commit()                           # save each journal as we go
        print(f"{len(items):4d} in feed, {added:3d} new" + (f"   <- {warning}" if warning else ""))
        time.sleep(1)                         # be polite to publishers

    status = "failed" if journals and len(failed) == len(journals) else ("partial" if failed or stale else "success")
    notes = "; ".join(failed + [f"stale: {x}" for x in stale] + [f"filled: {filled}"] +
                      ["windows: " + " | ".join(windows)])
    finish_run(db, run_id, status, seen, new, notes=notes)
    print(f"articles: {new} new of {seen} seen, {filled} filled in, {len(failed)} feed(s) failed, "
          f"{len(stale)} stale -> {status}")
    if stale:
        print("  stale feeds (check their URL): " + ", ".join(stale))
    if not only or "acs" in only:
        new += job_crossref_backup(db, session, topic_ids, cutoff)
    return new


def fill_gaps(cur, a, have, topic_ids):
    """RSS item for an article we already have (e.g. from the Crossref backup): fill its empty
    abstract, figure and authors. Never overwrites a non-empty field. Returns True if it changed."""
    has_abstract, has_image, has_authors = have
    abstract = clean_abstract(a["abstract"]) if not has_abstract else ""
    image = a["image_url"] if not has_image else ""
    authors = a["authors"] if not has_authors else ""
    if not (abstract or image or authors):
        return False
    # MySQL applies SET left to right, so image_source and figure_status are set before image_url
    cur.execute(
        """UPDATE articles
              SET abstract      = IF(COALESCE(abstract, '') = '', %s, abstract),
                  authors       = IF(COALESCE(authors, '') = '', %s, authors),
                  image_source  = IF(COALESCE(image_url, '') = '' AND %s IS NOT NULL, 'feed', image_source),
                  figure_status = IF(COALESCE(image_url, '') = '' AND %s IS NOT NULL, 'found', figure_status),
                  image_url     = IF(COALESCE(image_url, '') = '', %s, image_url)
            WHERE doi = %s""",
        (abstract or None, authors or None, image or None, image or None, image or None, a["doi"]))
    if cur.rowcount == 0:
        return False
    if abstract:                              # the abstract may add topics (title tags stay valid)
        cur.execute("SELECT article_id FROM articles WHERE doi = %s", (a["doi"],))
        article_id = cur.fetchone()[0]
        for topic in tag_topics(a["title"], abstract):
            if topic in topic_ids:
                cur.execute("INSERT IGNORE INTO article_topic_links (article_id, topic_id) VALUES (%s, %s)",
                            (article_id, topic_ids[topic]))
    return True


# ---------------------------------------------------------------------------
# Job 1b: Crossref backup for ACS (runs inside the articles job, at most every 6 hours)
# ---------------------------------------------------------------------------
def job_crossref_backup(db, session, topic_ids, cutoff):
    """ACS RSS lists only the last few days, so papers can slip past between polls. Add the ones
    Crossref knows (by ISSN, last 7 days) that we don't have, without abstract or figure; RSS fills
    those in if it brings the paper later (fill_gaps).
    ACS RSS titles carry no formatting ("CO2"), Crossref's do (CO<sub>2</sub>): for ACS papers we
    already have with a tagless title, take Crossref's formatted title when it is the same text
    (poc_feeds.upgrade_title - the same rules as scripts/refresh_titles.py). title_plain follows
    automatically (generated column)."""
    cur = db.cursor()
    cur.execute("""SELECT 1 FROM ingestion_runs
                    WHERE job = 'crossref_acs' AND status IN ('success', 'partial')
                      AND started_at > NOW() - INTERVAL %s HOUR LIMIT 1""", (CROSSREF_BACKUP_HOURS,))
    if cur.fetchone():
        print(f"crossref backup: skipped (last run under {CROSSREF_BACKUP_HOURS} hours ago)")
        return 0
    run_id = start_run(db, "crossref_acs")
    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    if not mailto:
        print("crossref backup: CROSSREF_MAILTO not set in .env - using Crossref's public pool")
    cur.execute("SELECT journal_id, name FROM journals WHERE is_active AND publisher = 'ACS'")
    journals = cur.fetchall()
    cur.execute("SELECT doi FROM articles")
    known = {row[0].lower() for row in cur.fetchall()}
    # ACS titles without <sub>/<sup>/<i>: candidates for a formatted title. doi -> (article_id, title)
    cur.execute("""SELECT a.doi, a.article_id, a.title FROM articles a JOIN journals j USING (journal_id)
                    WHERE j.publisher = 'ACS' AND a.title NOT REGEXP '<(sub|sup|i)>'""")
    plain = {doi.lower(): (article_id, title) for doi, article_id, title in cur.fetchall()}

    seen = new = upgraded_total = 0
    notes, failed = [], []
    for journal_id, name in journals:
        issns = feeds.ACS_ISSNS.get(name)
        if not issns:
            failed.append(f"{name}: no ISSN in poc_feeds.ACS_ISSNS")
            continue
        print(f"  crossref {name:28s}", end=" ", flush=True)
        items, err, _ = feeds.fetch_crossref_by_issn(issns, session, CROSSREF_BACKUP_DAYS, mailto)
        if err:
            failed.append(f"{name}: {err}")
            print("FAILED")
            continue
        added = upgraded = 0
        for a in items:
            if a["doi"].lower() in plain:             # we have it with a tagless title
                article_id, stored = plain.pop(a["doi"].lower())
                title = feeds.upgrade_title(stored, a["title"])
                if title:
                    cur.execute("UPDATE articles SET title = %s WHERE article_id = %s AND title = %s",
                                (title[:1000], article_id, stored))
                    upgraded += cur.rowcount
                continue
            published = to_date(a["date"])
            # a future date is a bad deposit (seen: JACS 'published-online' 2026-12-31 in November);
            # skip it - RSS brings the paper with its real date
            if a["doi"].lower() in known or not a["date"] or not cutoff <= published <= date.today():
                continue
            cur.execute(
                """INSERT IGNORE INTO articles
                     (doi, journal_id, title, authors, abstract, article_url, published_date, figure_status)
                   VALUES (%s, %s, %s, %s, NULL, %s, %s, 'none')""",
                (a["doi"], journal_id, a["title"][:1000], a["authors"] or None, a["link"], published))
            known.add(a["doi"].lower())
            if cur.rowcount == 0:
                continue
            article_id = cur.lastrowid
            for topic in tag_topics(a["title"]):      # title only: Crossref has no ACS abstracts
                if topic in topic_ids:
                    cur.execute("INSERT IGNORE INTO article_topic_links (article_id, topic_id) VALUES (%s, %s)",
                                (article_id, topic_ids[topic]))
            added += 1
        db.commit()
        seen += len(items)
        new += added
        upgraded_total += upgraded
        notes.append(f"{name} crossref_seen={len(items)} crossref_new={added} titles_upgraded={upgraded}")
        print(f"{len(items):4d} in Crossref, {added:3d} new, {upgraded:3d} titles upgraded")
        time.sleep(0.5)

    status = "failed" if len(failed) == len(journals) else ("partial" if failed else "success")
    finish_run(db, run_id, status, seen, new,
               notes="; ".join(failed + [f"titles_upgraded={upgraded_total}"] + notes))
    print(f"crossref backup: {new} new of {seen} seen, {upgraded_total} titles upgraded, "
          f"{len(failed)} journal(s) failed -> {status}")
    return new


# ---------------------------------------------------------------------------
# Job 2: figures for open-access Nature articles
# ---------------------------------------------------------------------------
def job_figures(db, session):
    cur = db.cursor()
    run_id = start_run(db, "figures")
    if not springer.enabled():
        finish_run(db, run_id, "failed", notes="SPRINGER keys missing in .env")
        print("figures: skipped - Springer keys missing in .env")
        return 0
    # Catch-up: Nature articles that never had the open-access check (e.g. loaded by
    # load_poc.py). Each is checked once; open-access ones become 'pending'.
    cur.execute(
        """SELECT a.article_id, a.doi FROM articles a JOIN journals j USING (journal_id)
            WHERE j.publisher = 'Springer Nature' AND a.is_open_access IS NULL
              AND a.figure_status = 'none'""")
    unchecked = cur.fetchall()
    marked = 0
    for article_id, doi in unchecked:
        try:
            _, is_oa, err = springer.meta_lookup(doi, session)
        except (requests.RequestException, ValueError):
            continue
        if err:
            continue
        cur.execute("UPDATE articles SET is_open_access = %s, figure_status = %s WHERE article_id = %s",
                    (is_oa, "pending" if is_oa else "none", article_id))
        marked += bool(is_oa)
        db.commit()
        time.sleep(0.6)
    if unchecked:
        print(f"figures: open-access check on {len(unchecked)} older Nature articles, {marked} marked pending")

    cur.execute(
        """SELECT article_id, doi, first_seen_at < NOW() - INTERVAL %s DAY AS too_old
             FROM articles
            WHERE figure_status = 'pending'
              AND (figure_checked_at IS NULL OR figure_checked_at < NOW() - INTERVAL %s HOUR)""",
        (FIGURE_RETRY_DAYS, FIGURE_RETRY_HOURS))
    pending = cur.fetchall()
    found = given_up = 0
    for article_id, doi, too_old in pending:
        try:
            url, _ = springer.figure1_url(doi, session)
        except requests.RequestException:
            url = None
        if url:
            cur.execute("""UPDATE articles SET image_url = %s, image_source = 'springer_oa',
                                  figure_status = 'found', figure_checked_at = NOW()
                            WHERE article_id = %s""", (url, article_id))
            found += 1
        elif too_old:
            cur.execute("UPDATE articles SET figure_status = 'none', figure_checked_at = NOW() "
                        "WHERE article_id = %s", (article_id,))
            given_up += 1
        else:
            cur.execute("UPDATE articles SET figure_checked_at = NOW() WHERE article_id = %s", (article_id,))
        db.commit()
        time.sleep(0.6)                       # stay inside the free-tier rate limit
    finish_run(db, run_id, "success", seen=len(pending), new=found,
               notes=f"{given_up} gave up after {FIGURE_RETRY_DAYS} days" if given_up else None)
    print(f"figures: checked {len(pending)}, found {found}, gave up {given_up}")
    return found


# ---------------------------------------------------------------------------
# Job 3: patents (EPO OPS)
# ---------------------------------------------------------------------------
def job_patents(db, session, days=PATENT_LOOKBACK_DAYS):
    cur = db.cursor()
    run_id = start_run(db, "patents")
    if not epo.enabled():
        finish_run(db, run_id, "failed", notes="EPO_KEY / EPO_SECRET missing in .env")
        print("patents: skipped - EPO keys missing in .env")
        return 0
    days = min(days, PATENT_DAYS)
    cur.execute("SELECT name, topic_id FROM patent_topics")
    topic_ids = dict(cur.fetchall())
    missing = [t for t in epo.STREAM_TOPICS if t not in topic_ids]
    if missing:
        finish_run(db, run_id, "failed", notes=f"patent_topics missing: {missing}")
        print(f"patents: run add_patent_topics.sql first - missing topics {missing}")
        return 0
    cur.execute("SELECT publication_number FROM patents")
    known = {row[0] for row in cur.fetchall()}

    client = epo.Client(session)
    found, failed = {}, []                    # publication_number -> patent
    today = date.today()
    # search in 7-day windows so no single search passes EPO's 2000-result limit
    windows = [(today - timedelta(days=min(d + 6, days)), today - timedelta(days=d))
               for d in range(0, days, 7)]
    for start, end in windows:
        for stream, sq in epo.STREAMS.items():
            query = f'pn={PATENT_OFFICE} and pd within "{start:%Y%m%d} {end:%Y%m%d}" and ({sq})'
            try:
                got, err = client.fetch(query)
            except requests.RequestException as e:
                got, err = [], str(e)
            if err:
                failed.append(f"{stream} {start}: {err[:120]}")
            for p in got:
                keep = found.setdefault(p["publication_number"], p)
                if stream != epo.GENERAL and stream not in keep["topics"]:
                    keep["topics"].append(stream)
            print(f"  {start} to {end}  {stream:30s} {len(got):4d}" + ("  FAILED" if err else ""))

    new = 0
    for pn, p in found.items():
        if pn in known or not p["published"]:
            continue
        cur.execute(
            """INSERT IGNORE INTO patents
                 (publication_number, office, title, applicants, inventors, abstract,
                  cpc_codes, family_id, patent_url, published_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (pn, p["office"], (p["title"] or "(no English title)")[:1000], p["applicants"],
             p["inventors"], p["abstract"] or None, p["cpc_codes"][:1000], p["family_id"] or None,
             p["patent_url"], p["published"]))
        if cur.rowcount == 0:
            continue
        patent_id = cur.lastrowid
        for topic in p["topics"]:
            if topic in topic_ids:
                cur.execute("INSERT IGNORE INTO patent_topic_links (patent_id, topic_id) VALUES (%s, %s)",
                            (patent_id, topic_ids[topic]))
        new += 1
    db.commit()

    searches = len(windows) * len(epo.STREAMS)
    status = "failed" if len(failed) == searches else ("partial" if failed else "success")
    finish_run(db, run_id, status, seen=len(found), new=new, notes="; ".join(failed))
    print(f"patents: {new} new of {len(found)} found, {len(failed)} search(es) failed -> {status}")
    return new


# ---------------------------------------------------------------------------
# Job 4: cleanup
# ---------------------------------------------------------------------------
def job_cleanup(db):
    cur = db.cursor()
    run_id = start_run(db, "cleanup")
    cur.execute("DELETE FROM articles WHERE published_date < CURDATE() - INTERVAL %s DAY", (ARTICLE_DAYS,))
    articles = cur.rowcount
    cur.execute("DELETE FROM patents WHERE published_date < CURDATE() - INTERVAL %s DAY", (PATENT_DAYS,))
    patents = cur.rowcount
    db.commit()
    finish_run(db, run_id, "success", deleted=articles + patents,
               notes=f"{articles} articles, {patents} patents removed")
    print(f"cleanup: removed {articles} articles older than {ARTICLE_DAYS} days, "
          f"{patents} patents older than {PATENT_DAYS} days")
    return articles + patents


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", choices=["articles", "figures", "patents", "cleanup", "all"])
    ap.add_argument("--only", default="", help='publishers for the articles job, e.g. "ACS,Wiley"')
    ap.add_argument("--days", type=int, default=PATENT_LOOKBACK_DAYS,
                    help="patents job: how many days back to search (max 90)")
    args = ap.parse_args()
    only = {p.strip().lower() for p in args.only.split(",") if p.strip()}

    db = connect()
    session = requests.Session()
    session.headers.update(feeds.HEADERS)
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"=== ingest {args.job} - {started} ===")
    try:
        if args.job in ("articles", "all"):
            job_articles(db, session, only)
        if args.job in ("figures", "all"):
            job_figures(db, session)
        if args.job in ("patents", "all"):
            job_patents(db, requests.Session(), args.days)   # plain session: no feed headers
        if args.job in ("cleanup", "all"):
            job_cleanup(db)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
