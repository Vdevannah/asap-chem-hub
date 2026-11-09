"""
ASAP Chem Hub - load proof-of-concept results into MySQL
========================================================
Reads poc_results.csv (made by poc_feeds.py) and loads it into the
asap_chem_hub database created by schema.sql:
  * one row per article (DOI is unique - running this twice adds nothing twice)
  * topics re-tagged with topics.py and stored in article_topic_links
  * figure_status set from the feed's image
  * one row in ingestion_runs describing this load

Database login comes from .env:
    DB_HOST=localhost
    DB_PORT=3306
    DB_USER=root
    DB_PASSWORD=your-mysql-password
    DB_NAME=asap_chem_hub

Usage
    pip install -r requirements.txt
    python load_poc.py
"""

import csv
import os
import re
import sys
from datetime import date

import pymysql
from dotenv import load_dotenv

from topics import tag_topics

load_dotenv()

CITATION_RE = re.compile(r"\s*\^\s*\d+(?:\s*[,–-]\s*\d+)*")   # "^1,2" or "^ 1 – 4" left in abstracts


def clean_abstract(text: str) -> str:
    text = CITATION_RE.sub("", text or "")
    text = re.sub(r"\s+([,.;:)])", r"\1", text)      # "word ," -> "word,"
    return re.sub(r"\s+", " ", text).strip()


def to_date(value: str):
    """'2026-11-08' -> date; '2026-11' -> first of month; anything else -> today."""
    parts = re.findall(r"\d+", value or "")
    try:
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return date(int(parts[0]), int(parts[1]), 1)
    except ValueError:
        pass
    return date.today()


def connect():
    try:
        return pymysql.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ.get("DB_USER", "root"),
            password=os.environ.get("DB_PASSWORD", ""),
            database=os.environ.get("DB_NAME", "asap_chem_hub"),
            charset="utf8mb4",
            autocommit=False,
        )
    except pymysql.MySQLError as e:
        sys.exit(f"Could not connect to MySQL: {e}\nCheck DB_* settings in .env and that MySQL is running.")


def main():
    try:
        rows = list(csv.DictReader(open("poc_results.csv", encoding="utf-8")))
    except FileNotFoundError:
        sys.exit("poc_results.csv not found - run: python poc_feeds.py")

    db = connect()
    cur = db.cursor()

    cur.execute("SELECT name, journal_id FROM journals")
    journal_ids = dict(cur.fetchall())
    cur.execute("SELECT name, topic_id FROM article_topics")
    topic_ids = dict(cur.fetchall())

    cur.execute("INSERT INTO ingestion_runs (job) VALUES ('articles')")
    run_id = cur.lastrowid

    seen = new = links = 0
    skipped = {"no DOI": 0, "unknown journal": 0}
    for r in rows:
        seen += 1
        if not r["doi"]:
            skipped["no DOI"] += 1
            continue
        jid = journal_ids.get(r["journal"])
        if jid is None:
            skipped["unknown journal"] += 1
            continue
        abstract = clean_abstract(r["abstract"])
        image = r["image_url"] or None
        cur.execute(
            """INSERT IGNORE INTO articles
                 (doi, journal_id, title, authors, abstract, article_url, published_date,
                  image_url, image_source, figure_status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (r["doi"], jid, r["title"][:1000], r["authors"], abstract,
             r["link"] or f"https://doi.org/{r['doi']}", to_date(r["date"]),
             image, "feed" if image else None, "found" if image else "none"),
        )
        if cur.rowcount == 0:          # DOI already in the table
            continue
        new += 1
        article_id = cur.lastrowid
        for topic in tag_topics(r["title"], abstract):
            if topic in topic_ids:
                cur.execute("INSERT IGNORE INTO article_topic_links (article_id, topic_id) VALUES (%s, %s)",
                            (article_id, topic_ids[topic]))
                links += cur.rowcount

    notes = "; ".join(f"{k}: {v}" for k, v in skipped.items() if v) or None
    cur.execute(
        """UPDATE ingestion_runs
              SET finished_at = NOW(), status = %s, items_seen = %s, items_new = %s, notes = %s
            WHERE run_id = %s""",
        ("partial" if notes else "success", seen, new, notes, run_id),
    )
    db.commit()

    # ---- quick report ------------------------------------------------------
    print(f"Rows in CSV      : {seen}")
    print(f"New articles     : {new}")
    print(f"Topic links      : {links}")
    if notes:
        print(f"Skipped          : {notes}")
    cur.execute("SELECT COUNT(*) FROM articles")
    print(f"Articles in DB   : {cur.fetchone()[0]}")
    cur.execute("SELECT figure_status, COUNT(*) FROM articles GROUP BY figure_status")
    print("Figure status    : " + ", ".join(f"{s} {n}" for s, n in cur.fetchall()))
    cur.execute("""SELECT t.name, COUNT(l.article_id) FROM article_topics t
                   LEFT JOIN article_topic_links l ON l.topic_id = t.topic_id
                   GROUP BY t.topic_id ORDER BY COUNT(l.article_id) DESC""")
    print("\nArticles per topic:")
    for name, n in cur.fetchall():
        print(f"  {n:5d}  {name}")
    db.close()


if __name__ == "__main__":
    main()
