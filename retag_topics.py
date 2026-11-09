"""
ASAP Chem Hub - re-tag all articles after changing topics.py
============================================================
Use this whenever you add a topic or change topic rules:
  1. adds any new topic names from topics.py to article_topics and patent_topics
  2. rebuilds article_topic_links for every article already in the database
  3. prints articles per topic

Usage
    python retag_topics.py
"""

from load_poc import connect          # same .env login as the loader
from topics import TOPICS, tag_topics


def main():
    db = connect()
    cur = db.cursor()

    # 1. topic names: same list in both sections
    for name in TOPICS:
        cur.execute("INSERT IGNORE INTO article_topics (name) VALUES (%s)", (name,))
        cur.execute("INSERT IGNORE INTO patent_topics (name) VALUES (%s)", (name,))
    cur.execute("SELECT name, topic_id FROM article_topics")
    topic_ids = dict(cur.fetchall())
    unused = [n for n in topic_ids if n not in TOPICS]

    # 2. rebuild links from title + abstract
    cur.execute("SELECT article_id, title, abstract FROM articles")
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

    # 3. report
    print(f"Articles re-tagged : {len(articles)}")
    print(f"Topic links        : {len(links)}\n")
    cur.execute("""SELECT t.name, COUNT(l.article_id) FROM article_topics t
                   LEFT JOIN article_topic_links l ON l.topic_id = t.topic_id
                   GROUP BY t.topic_id ORDER BY COUNT(l.article_id) DESC""")
    for name, n in cur.fetchall():
        flag = "   (not in topics.py - no longer used)" if name in unused else ""
        print(f"  {n:5d}  {name}{flag}")
    db.close()


if __name__ == "__main__":
    main()
