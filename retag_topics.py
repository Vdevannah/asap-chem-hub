"""
ASAP Chem Hub - re-tag articles after changing topics.py
========================================================
Full rebuild (default), whenever you change topic rules:
  1. adds any new topic names from topics.py to article_topics, and to patent_topics
     unless the topic is marked articles_only
  2. rebuilds article_topic_links for every article already in the database
  3. prints articles per topic

Add-only (--add), for newly added topics: tags articles with the named topics and never
removes or changes any other tag.
  --add new           every topic in topics.py that is not yet in article_topics
  --add "A,B"         these topics by name
  --days 30           only articles published in the last 30 days
  --dry-run           show what would be added, write nothing

Usage
    python retag_topics.py                                   # full rebuild
    python retag_topics.py --add new --days 30 --dry-run     # preview new topics
    python retag_topics.py --add new --days 30               # apply
"""

import argparse

from load_poc import connect          # same .env login as the loader
from topics import TOPICS, tag_topics


def report(cur, unused=()):
    cur.execute("""SELECT t.name, COUNT(l.article_id) FROM article_topics t
                   LEFT JOIN article_topic_links l ON l.topic_id = t.topic_id
                   GROUP BY t.topic_id ORDER BY COUNT(l.article_id) DESC""")
    for name, n in cur.fetchall():
        flag = "   (not in topics.py - no longer used)" if name in unused else ""
        print(f"  {n:5d}  {name}{flag}")


def full_rebuild(db, cur):
    # 1. topic names (article-only topics stay out of the patent section)
    for name, cfg in TOPICS.items():
        cur.execute("INSERT IGNORE INTO article_topics (name) VALUES (%s)", (name,))
        if not cfg.get("articles_only"):
            cur.execute("INSERT IGNORE INTO patent_topics (name) VALUES (%s)", (name,))
    cur.execute("SELECT name, topic_id FROM article_topics")
    topic_ids = dict(cur.fetchall())
    unused = [n for n in topic_ids if n not in TOPICS]

    # 2. rebuild links from title (plain text) + abstract
    cur.execute("SELECT article_id, title_plain, abstract FROM articles")
    articles = cur.fetchall()
    cur.execute("DELETE FROM article_topic_links")
    links = []
    for article_id, title, abstract in articles:
        for topic in tag_topics(title, abstract or ""):
            links.append((article_id, topic_ids[topic]))
    cur.executemany("INSERT INTO article_topic_links (article_id, topic_id) VALUES (%s, %s)", links)

    cur.execute("INSERT INTO ingestion_runs (job, finished_at, status, items_seen, notes) "
                "VALUES ('retag', NOW(), 'success', %s, %s)",
                (len(articles), f"{len(links)} topic links rebuilt"))
    db.commit()

    print(f"Articles re-tagged : {len(articles)}")
    print(f"Topic links        : {len(links)}\n")
    report(cur, unused)


def add_only(db, cur, names, days, dry_run):
    cur.execute("SELECT name, topic_id FROM article_topics")
    topic_ids = dict(cur.fetchall())
    if names == ["new"]:
        names = [t for t in TOPICS if t not in topic_ids]
    unknown = [n for n in names if n not in TOPICS]
    if unknown:
        raise SystemExit(f"Not in topics.py: {unknown}")
    if not names:
        raise SystemExit("No new topics: every topic in topics.py is already in article_topics.")

    where, params = "", []
    if days:
        where, params = "WHERE published_date >= CURDATE() - INTERVAL %s DAY", [days]
    cur.execute(f"SELECT article_id, title_plain, abstract FROM articles {where}", params)
    articles = cur.fetchall()
    wanted = set(names)
    matches = {n: [] for n in names}
    for article_id, title, abstract in articles:
        for topic in set(tag_topics(title, abstract or "")) & wanted:
            matches[topic].append((article_id, title))

    scope = f"the last {days} days" if days else "all dates"
    print(f"{'DRY RUN - ' if dry_run else ''}add-only: {len(names)} topic(s), "
          f"{len(articles)} articles ({scope}); existing tags are not touched\n")
    for n in names:
        print(f"  {len(matches[n]):5d}  {n}" + ("" if n in topic_ids else "   (new topic)"))
    if dry_run:
        print("\nDry run: nothing written.")
        return

    for n in names:                             # article-only topics stay out of patent_topics
        cur.execute("INSERT IGNORE INTO article_topics (name) VALUES (%s)", (n,))
        if not TOPICS[n].get("articles_only"):
            cur.execute("INSERT IGNORE INTO patent_topics (name) VALUES (%s)", (n,))
    cur.execute("SELECT name, topic_id FROM article_topics")
    topic_ids = dict(cur.fetchall())
    links = [(article_id, topic_ids[n]) for n in names for article_id, _ in matches[n]]
    cur.executemany("INSERT IGNORE INTO article_topic_links (article_id, topic_id) VALUES (%s, %s)", links)
    added = cur.rowcount
    cur.execute("INSERT INTO ingestion_runs (job, finished_at, status, items_seen, items_new, notes) "
                "VALUES ('retag', NOW(), 'success', %s, %s, %s)",
                (len(articles), added, f"add-only ({scope}): " +
                 "; ".join(f"{n}={len(matches[n])}" for n in names)))
    db.commit()
    print(f"\nAdded {added} topic links.\n")
    report(cur)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", help='add-only: "new" or comma-separated topic names')
    ap.add_argument("--days", type=int, default=0, help="add-only: articles from the last N days (default all)")
    ap.add_argument("--dry-run", action="store_true", help="add-only: show counts, write nothing")
    args = ap.parse_args()

    db = connect()
    cur = db.cursor()
    try:
        if args.add:
            add_only(db, cur, [n.strip() for n in args.add.split(",") if n.strip()], args.days, args.dry_run)
        else:
            if args.days or args.dry_run:
                raise SystemExit("--days and --dry-run work with --add only")
            full_rebuild(db, cur)
    finally:
        db.close()


if __name__ == "__main__":
    main()
