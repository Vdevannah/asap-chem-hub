"""
Load an export from scripts/export_db.py into a MySQL server - on AWS the one-off "admin" ECS
task inside the VPC, so RDS never has to be public (see infra/PLAN.md, section 7).

  1. reads the export from s3://bucket/key (boto3, task role) or a local path
  2. creates the database (utf8mb4 / utf8mb4_unicode_ci) and every table from its CREATE TABLE
  3. inserts all rows with their original IDs (generated columns are rebuilt by MySQL)
  4. re-reads every table and compares row count and checksum with the export: any mismatch -> exit 1
  5. with --create-users: creates the IAM-authenticated users asap_api (SELECT) and asap_jobs
     (SELECT, INSERT, UPDATE, DELETE) - RDS only (AWSAuthenticationPlugin)

Refuses to touch a database that already has rows, unless --replace (drops and reloads the tables).
Connects with the DB_* settings (on AWS: the RDS master user, password injected from Secrets Manager).

Usage
    python scripts/import_db.py s3://<artifacts-bucket>/migration/asap_chem_hub-....jsonl.gz --create-users
    python scripts/import_db.py ~/asap-export/asap_chem_hub-....jsonl.gz      # local test
"""

import argparse
import gzip
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_transfer as t                    # noqa: E402
from db_connect import connect             # noqa: E402

USERS = {
    "asap_api": "SELECT",
    "asap_jobs": "SELECT, INSERT, UPDATE, DELETE",
}


def open_export(source):
    if source.startswith("s3://"):
        import boto3
        bucket, key = source[5:].split("/", 1)
        tmp = tempfile.NamedTemporaryFile(suffix=".jsonl.gz", delete=False)
        tmp.close()
        boto3.client("s3").download_file(bucket, key, tmp.name)
        print(f"Downloaded {source}")
        return tmp.name
    return os.path.expanduser(source)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="s3://bucket/key or a local path")
    ap.add_argument("--replace", action="store_true", help="drop and reload tables that already have rows")
    ap.add_argument("--create-users", action="store_true", help="create the IAM-authenticated app users (RDS)")
    args = ap.parse_args()

    path = open_export(args.source)
    with gzip.open(path, "rt", encoding="utf-8") as f:
        lines = [json.loads(line) for line in f]
    meta = lines[0]
    tables = {x["name"]: x for x in lines if x["type"] == "table"}
    database = meta["database"]
    if list(tables) != t.TABLES:
        sys.exit(f"Export tables {list(tables)} differ from {t.TABLES}")

    db = connect(database=None, autocommit=False)
    cur = db.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{database}`")
    cur.execute("SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s", (database,))
    existing = {r[0] for r in cur.fetchall()}
    with_rows = []
    for name in existing & set(t.TABLES):
        cur.execute(f"SELECT COUNT(*) FROM `{name}`")
        if cur.fetchone()[0]:
            with_rows.append(name)
    if with_rows and not args.replace:
        sys.exit(f"Tables already have rows: {sorted(with_rows)}. Nothing changed. Use --replace to reload.")

    cur.execute("SET FOREIGN_KEY_CHECKS = 0")
    for name in reversed(t.TABLES):
        if name in existing:
            cur.execute(f"DROP TABLE `{name}`")
    for name in t.TABLES:
        cur.execute(tables[name]["ddl"])
    for line in lines:
        if line["type"] != "rows":
            continue
        cols = tables[line["table"]]["columns"]
        sql = (f"INSERT INTO `{line['table']}` ({', '.join(f'`{c}`' for c in cols)}) "
               f"VALUES ({', '.join(['%s'] * len(cols))})")
        cur.executemany(sql, line["rows"])
    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    db.commit()

    print("Verifying ...")
    failed = []
    for name in t.TABLES:
        rows = t.read_rows(cur, database, name, tables[name]["columns"])
        ok = len(rows) == tables[name]["count"] and t.checksum(rows) == tables[name]["sha256"]
        print(f"  {name:22s} {len(rows):7d} rows  {'ok' if ok else 'MISMATCH'}")
        if not ok:
            failed.append(name)
    cur.execute(f"SELECT COUNT(*) FROM `{database}`.articles WHERE title_plain IS NULL")
    if cur.fetchone()[0]:
        failed.append("articles.title_plain")
    if failed:
        sys.exit(f"Import FAILED verification: {failed}")

    if args.create_users:
        for user, grants in USERS.items():
            cur.execute(f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED WITH AWSAuthenticationPlugin AS 'RDS'")
            cur.execute(f"ALTER USER '{user}'@'%' REQUIRE SSL")
            cur.execute(f"GRANT {grants} ON `{database}`.* TO '{user}'@'%'")
            print(f"  user {user}: {grants} (IAM auth, TLS required)")
        db.commit()

    if args.source.startswith("s3://"):
        os.remove(path)
    print("Import complete and verified.")


if __name__ == "__main__":
    main()
