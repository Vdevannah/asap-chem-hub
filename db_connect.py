"""
One MySQL connection helper for the API, the ingestion jobs and the scripts.

Local (default)  DB_AUTH=password - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME from .env.
AWS              DB_AUTH=iam      - RDS IAM authentication: the password is a 15-minute token that
                                    boto3 signs locally from the Lambda / ECS task role. Signing makes
                                    no network call, so it works in a VPC without NAT or endpoints.
                                    IAM auth needs TLS: DB_SSL_CA is the RDS CA bundle shipped with
                                    the code (global-bundle.pem, downloaded at build time).
                 DB_SSL_CA alone  - TLS with a password (the one-off admin task on RDS).

With IAM auth a fresh token is signed every time a socket is opened - the first connect and any
reconnect (e.g. ping(reconnect=True) in the API) - because a token is only checked at login and
expires after 15 minutes. Timings are logged; the token itself never is.
"""

import logging
import os
import time

import pymysql
from dotenv import load_dotenv

load_dotenv()          # no-op when there is no .env (Lambda, ECS)

log = logging.getLogger("asap.db")

_rds_client = None


def _iam_token(host, port, user):
    global _rds_client
    import boto3                                       # only needed on AWS
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if _rds_client is None:
        _rds_client = boto3.client("rds", region_name=region)
    return _rds_client.generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user, Region=region)


class _Connection(pymysql.connections.Connection):
    """pymysql Connection that signs a new IAM token before every (re)connect when DB_AUTH=iam."""

    def __init__(self, *args, iam=False, **kwargs):
        self._iam = iam
        self.first_query_pending = True       # read by the API to time the first query
        super().__init__(*args, **kwargs)     # calls self.connect() unless defer_connect=True

    def connect(self, sock=None):
        token_ms = None
        if self._iam:
            t = time.perf_counter()
            self.password = _iam_token(self.host, self.port, self.user.decode()
                                       if isinstance(self.user, bytes) else self.user).encode("latin1")
            token_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        try:
            super().connect(sock)
        except Exception as e:
            log.warning("db connect failed after %.0f ms (%s)", (time.perf_counter() - t) * 1000,
                        type(e).__name__)
            raise
        connect_ms = (time.perf_counter() - t) * 1000
        self.first_query_pending = True
        if token_ms is None:
            log.info("db connect %.0f ms", connect_ms)
        else:
            log.info("db iam token %.0f ms, connect %.0f ms", token_ms, connect_ms)


def connect(**kwargs):
    """A new pymysql connection. Extra keyword arguments go to pymysql.connect (cursorclass, autocommit,
    connect_timeout, read_timeout ...)."""
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.environ.get("DB_USER", "root")
    params = dict(host=host, port=port, user=user, database=os.environ.get("DB_NAME", "asap_chem_hub"),
                  charset="utf8mb4", connect_timeout=10)
    ca = os.environ.get("DB_SSL_CA")
    if ca:
        params["ssl"] = {"ca": ca}
    iam = os.environ.get("DB_AUTH", "password").lower() == "iam"
    if iam:
        if not ca:
            raise RuntimeError("DB_AUTH=iam needs DB_SSL_CA: RDS IAM authentication only works over TLS")
    else:
        params["password"] = os.environ.get("DB_PASSWORD", "")
    params.update(kwargs)
    return _Connection(iam=iam, **params)
