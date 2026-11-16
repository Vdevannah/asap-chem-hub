"""
One MySQL connection helper for the API, the ingestion jobs and the scripts.

Local (default)  DB_AUTH=password - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME from .env.
AWS              DB_AUTH=iam      - RDS IAM authentication: the password is a 15-minute token that
                                    boto3 signs locally from the Lambda / ECS task role. Signing makes
                                    no network call, so it works in a VPC without NAT or endpoints.
                                    IAM auth needs TLS: DB_SSL_CA is the RDS CA bundle shipped with
                                    the code (global-bundle.pem, downloaded at build time).
                 DB_SSL_CA alone  - TLS with a password (the one-off admin task on RDS).
"""

import os

import pymysql
from dotenv import load_dotenv

load_dotenv()          # no-op when there is no .env (Lambda, ECS)

_rds_client = None


def _iam_token(host, port, user):
    global _rds_client
    import boto3                                       # only needed on AWS
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if _rds_client is None:
        _rds_client = boto3.client("rds", region_name=region)
    return _rds_client.generate_db_auth_token(DBHostname=host, Port=port, DBUsername=user, Region=region)


def connect(**kwargs):
    """A new pymysql connection. Extra keyword arguments go to pymysql.connect (cursorclass, autocommit ...)."""
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = int(os.environ.get("DB_PORT", "3306"))
    user = os.environ.get("DB_USER", "root")
    params = dict(host=host, port=port, user=user, database=os.environ.get("DB_NAME", "asap_chem_hub"),
                  charset="utf8mb4", connect_timeout=10)
    ca = os.environ.get("DB_SSL_CA")
    if ca:
        params["ssl"] = {"ca": ca}
    if os.environ.get("DB_AUTH", "password").lower() == "iam":
        if not ca:
            raise RuntimeError("DB_AUTH=iam needs DB_SSL_CA: RDS IAM authentication only works over TLS")
        params["password"] = _iam_token(host, port, user)
    else:
        params["password"] = os.environ.get("DB_PASSWORD", "")
    params.update(kwargs)
    return pymysql.connect(**params)
