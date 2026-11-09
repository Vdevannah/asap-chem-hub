"""
ASAP Chem Hub - ingestion pipeline (Phase 5)
============================================
Keeps the database fresh. Three jobs:

  articles  fetch every active journal in the `journals` table, add only NEW DOIs,
            fill gaps from Crossref (Nature, Science) and the Springer Meta API,
            tag topics.                                          -> every 4 hours
  figures   re-check open-access Nature articles marked 'pending' and add
            Figure 1 when Springer has indexed the full text;
            give up after 14 days.                               -> daily
  cleanup   delete articles older than 30 days, patents older than 90.  -> daily

Every job writes one row to `ingestion_runs`. A failing feed is recorded in
journals.last_error and the other feeds carry on.

Usage
    python ingest.py articles                 # all active journals
    python ingest.py articles --only "ACS"    # one publisher (comma-separated list)
    python ingest.py figures
    python ingest.py cleanup
    python ingest.py all                      # articles, then figures, then cleanup
"""

import argparse
import sys
import time

import requests

import poc_feeds as feeds
import springer
from load_poc import clean_abstract, connect, to_date
from topics import tag_topics

ARTICLE_DAYS = 30           # keep articles this long (by publication date)
PATENT_DAYS = 90
FIGURE_RETRY_DAYS = 14      # stop re-checking a 'pending' figure after this
FIGURE_RETRY_HOURS = 20     # re-check each pending figure at most once a day
STALE_DAYS = 14             # warn when a feed's newest article is older than this


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
    known = {row[0] for row in cur.fetchall()}
    cutoff = to_date(time.strftime("%Y-%m-%d", time.gmtime(time.time() - ARTICLE_DAYS * 86400)))

    seen = new = 0
    failed, stale = [], []
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
            if not a["doi"] or a["doi"] in known:
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
            known.add(a["doi"])
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
    notes = "; ".join(failed + [f"stale: {x}" for x in stale])
    finish_run(db, run_id, status, seen, new, notes=notes)
    print(f"articles: {new} new of {seen} seen, {len(failed)} feed(s) failed, {len(stale)} stale -> {status}")
    if stale:
        print("  stale feeds (check their URL): " + ", ".join(stale))
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
# Job 3: cleanup
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
    ap.add_argument("job", choices=["articles", "figures", "cleanup", "all"])
    ap.add_argument("--only", default="", help='publishers for the articles job, e.g. "ACS,Wiley"')
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
        if args.job in ("cleanup", "all"):
            job_cleanup(db)
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
