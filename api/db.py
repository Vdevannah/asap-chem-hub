"""
Database connection for the API.
Reads the same .env as the pipeline (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME).
"""

import os
from contextlib import contextmanager

import pymysql
from dotenv import load_dotenv

load_dotenv()


@contextmanager
def get_cursor():
    """Open a connection, hand out a dict cursor, always close it."""
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", ""),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "asap_chem_hub"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()
