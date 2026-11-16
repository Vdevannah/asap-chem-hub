"""
Shared by scripts/export_db.py (local) and scripts/import_db.py (one-off admin task on AWS):
table order, how rows are read, and the per-table checksum, so both sides compute it the same way.

Export file: gzipped JSON lines
  {"type": "meta", ...}
  {"type": "table", "name", "ddl", "columns", "count", "sha256"}      (one per table, in TABLES order)
  {"type": "rows", "table", "rows": [[...], ...]}                      (batches of ROWS_PER_LINE)
Generated columns (articles.title_plain) are left out: MySQL rebuilds them on insert.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

# Parents before children (foreign keys).
TABLES = ["journals", "article_topics", "patent_topics", "articles", "article_topic_links",
          "patents", "patent_topic_links", "ingestion_runs"]
ROWS_PER_LINE = 500


def value(v):
    """A database value as JSON (the same on export and on the re-read after import)."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8")
    return v


def columns(cur, database, table):
    """Stored (not generated) columns, in table order."""
    cur.execute("""SELECT COLUMN_NAME FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND EXTRA NOT LIKE '%%GENERATED%%'
                    ORDER BY ORDINAL_POSITION""", (database, table))
    return [r[0] for r in cur.fetchall()]


def primary_key(cur, database, table):
    cur.execute("""SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
                    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
                    ORDER BY ORDINAL_POSITION""", (database, table))
    return [r[0] for r in cur.fetchall()]


def read_rows(cur, database, table, cols):
    """All rows, in primary-key order, as JSON-ready lists."""
    order = ", ".join(f"`{c}`" for c in primary_key(cur, database, table)) or "1"
    cur.execute(f"SELECT {', '.join(f'`{c}`' for c in cols)} FROM `{table}` ORDER BY {order}")
    return [[value(v) for v in row] for row in cur.fetchall()]


def checksum(rows):
    h = hashlib.sha256()
    for row in rows:
        h.update(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode())
        h.update(b"\n")
    return h.hexdigest()
