"""
Database connection for the API.
Locally it reads the same .env as the pipeline; on AWS it uses RDS IAM authentication
(see db_connect.py).
"""

from contextlib import contextmanager

import pymysql

from db_connect import connect


@contextmanager
def get_cursor():
    """Open a connection, hand out a dict cursor, always close it."""
    conn = connect(cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()
