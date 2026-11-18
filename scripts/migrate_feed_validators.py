"""
Migration: conditional feed requests + ACS 'pending' graphical abstracts.

1. Adds journals.feed_etag, journals.feed_last_modified and journals.feed_fetched_at (see schema.sql),
   used by ingest.py to send If-None-Match / If-Modified-Since.
2. Marks ACS articles that have no figure and were published within ingest.ACS_PENDING_DAYS as
   'pending' (they came from the Crossref backup before this change, as 'none'). The articles job
   turns them back into 'none' if the ACS RSS feed has not filled them in by then.

Safe to run more than once: each column is added only if it is missing.
Needs ALTER on journals, so run it as the master user:
  local    python scripts/migrate_feed_validators.py
  AWS      the one-off admin task:  command ["python", "scripts/migrate_feed_validators.py"]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db_connect import connect          # noqa: E402

ACS_PENDING_DAYS = 2                     # same as ingest.ACS_PENDING_DAYS (not imported: ingest pulls in
                                         # the whole pipeline)
COLUMNS = [
    ("feed_etag", "VARCHAR(255) NULL AFTER last_error"),
    ("feed_last_modified", "VARCHAR(64) NULL AFTER feed_etag"),
    ("feed_fetched_at", "DATETIME NULL AFTER feed_last_modified"),
]


def main():
    db = connect(autocommit=False)
    cur = db.cursor()
    cur.execute("SELECT DATABASE()")
    print(f"database: {cur.fetchone()[0]}")
    for name, ddl in COLUMNS:
        cur.execute("""SELECT COUNT(*) FROM information_schema.COLUMNS
                        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'journals' AND COLUMN_NAME = %s""",
                    (name,))
        if cur.fetchone()[0]:
            print(f"  journals.{name}: already there")
        else:
            cur.execute(f"ALTER TABLE journals ADD COLUMN {name} {ddl}")
            print(f"  journals.{name}: added")

    cur.execute("""UPDATE articles a JOIN journals j USING (journal_id)
                      SET a.figure_status = 'pending'
                    WHERE j.publisher = 'ACS' AND a.figure_status = 'none'
                      AND COALESCE(a.image_url, '') = ''
                      AND a.published_date >= UTC_DATE() - INTERVAL %s DAY""", (ACS_PENDING_DAYS,))
    print(f"  ACS articles without a figure, published in the last {ACS_PENDING_DAYS} days: "
          f"{cur.rowcount} marked 'pending'")
    db.commit()
    print("migration complete")


if __name__ == "__main__":
    main()
