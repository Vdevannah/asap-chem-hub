"""
Export the local ASAP Chem Hub database for the one-off move to RDS (see infra/PLAN.md, section 7).

Writes one gzipped JSON-lines file OUTSIDE the repo (default ~/asap-export/, file mode 600):
every table's CREATE TABLE, every row (generated columns left out), and a count + checksum per
table that scripts/import_db.py checks after loading. No passwords or keys are in the database.

Usage (from the project folder, local Docker MySQL running)
    python scripts/export_db.py                       # -> ~/asap-export/asap_chem_hub-<UTC time>.jsonl.gz
    python scripts/export_db.py --out /path/file.jsonl.gz
"""

import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db_transfer as t                    # noqa: E402  (same folder)
from db_connect import connect             # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    ap.add_argument("--out", default=os.path.expanduser(f"~/asap-export/asap_chem_hub-{stamp}.jsonl.gz"))
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    if out.startswith(REPO + os.sep):
        sys.exit("Refusing to write the export inside the repository - choose a path outside it.")

    db = connect()
    cur = db.cursor()
    database = os.environ.get("DB_NAME", "asap_chem_hub")
    cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
                (database,))
    present = {r[0] for r in cur.fetchall()}
    if present != set(t.TABLES):
        sys.exit(f"Tables differ from the expected list. Unexpected: {sorted(present - set(t.TABLES))}, "
                 f"missing: {sorted(set(t.TABLES) - present)}. Update scripts/db_transfer.py TABLES first.")

    os.makedirs(os.path.dirname(out), mode=0o700, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    cur.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")          # one consistent view of all tables
    with gzip.open(os.fdopen(fd, "wb"), "wt", encoding="utf-8") as f:
        f.write(json.dumps({"type": "meta", "database": database, "exported_at": stamp, "tables": t.TABLES}) + "\n")
        for table in t.TABLES:
            cur.execute(f"SHOW CREATE TABLE `{table}`")
            ddl = cur.fetchone()[1]
            cols = t.columns(cur, database, table)
            rows = t.read_rows(cur, database, table, cols)
            f.write(json.dumps({"type": "table", "name": table, "ddl": ddl, "columns": cols,
                                "count": len(rows), "sha256": t.checksum(rows)}) + "\n")
            for i in range(0, len(rows), t.ROWS_PER_LINE):
                f.write(json.dumps({"type": "rows", "table": table, "rows": rows[i:i + t.ROWS_PER_LINE]},
                                   ensure_ascii=False) + "\n")
            print(f"  {table:22s} {len(rows):7d} rows")
    db.rollback()
    print(f"Wrote {out} ({os.path.getsize(out) / 1e6:.1f} MB, mode 600)")


if __name__ == "__main__":
    main()
