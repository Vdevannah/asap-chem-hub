"""
Database connection for the API.
Locally it reads the same .env as the pipeline; on AWS it uses RDS IAM authentication
(see db_connect.py).

Connections are reused across requests through a small module-level pool of idle connections. A
Lambda instance handles one request at a time, so its pool never holds more than one connection: one
per instance. (Not thread-local: Mangum runs each sync route on a worker thread that does not survive
the invocation.) Locally, uvicorn's concurrent requests each take their own. Each request pings first
and reconnects if the server dropped the connection (the reconnect signs a fresh IAM token). Autocommit is on so every request sees current data instead
of a REPEATABLE READ snapshot left over from an earlier request.

Short timeouts make a stuck connect or query fail in seconds instead of holding a Lambda slot until
its 15 s timeout.
"""

import logging
import threading
import time
from contextlib import contextmanager

import pymysql

from db_connect import connect

API_TIMEOUTS = dict(connect_timeout=5, read_timeout=8, write_timeout=8)

log = logging.getLogger("asap.db")
log.setLevel(logging.INFO)                 # Lambda's root logger is WARNING; we want the timings
if not logging.getLogger().handlers:       # locally (uvicorn) the root logger has no handler
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    log.addHandler(_h)
    log.propagate = False

_idle = []                   # idle connections, most recently used last
_lock = threading.Lock()


class _TimedCursor(pymysql.cursors.DictCursor):
    """Dict cursor that logs how long the first query on a new connection took."""

    def execute(self, query, args=None):
        conn = self.connection
        if not getattr(conn, "first_query_pending", False):
            return super().execute(query, args)
        conn.first_query_pending = False
        t = time.perf_counter()
        result = super().execute(query, args)
        log.info("db first query %.0f ms", (time.perf_counter() - t) * 1000)
        return result


def _close(conn):
    try:
        conn.close()
    except Exception:
        pass


def _acquire():
    with _lock:
        conn = _idle.pop() if _idle else None
    if conn is None:
        return connect(cursorclass=_TimedCursor, autocommit=True, **API_TIMEOUTS)
    try:
        conn.ping(reconnect=True)          # reconnects (with a fresh IAM token) if the server closed it
    except Exception:
        _close(conn)
        raise
    return conn


@contextmanager
def get_cursor():
    """Hand out a dict cursor on a reused connection. On a connection-level error (lost connection,
    timeout) the connection is closed instead of returned, so the next request starts fresh."""
    conn = _acquire()
    try:
        with conn.cursor() as cur:
            yield cur
    except (pymysql.err.OperationalError, pymysql.err.InterfaceError):
        _close(conn)
        raise
    except BaseException:
        with _lock:
            _idle.append(conn)             # e.g. an HTTPException raised inside the block: still healthy
        raise
    else:
        with _lock:
            _idle.append(conn)
