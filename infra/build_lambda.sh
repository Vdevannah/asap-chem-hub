#!/bin/sh
# Build the Lambda API package: build/lambda/api.zip (handler api.lambda_handler.handler).
# Dependencies are the Linux arm64 wheels for Python 3.14, matching the Lambda runtime python3.14
# (pydantic-core is compiled, so wheels built for macOS would not load on Lambda).
# Run from anywhere: infra/build_lambda.sh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/lambda"
PKG="$OUT/package"
rm -rf "$OUT"
mkdir -p "$PKG/certs"

python3 -m pip install --quiet --disable-pip-version-check \
  --platform manylinux2014_aarch64 --implementation cp --python-version 3.14 --only-binary=:all: \
  --target "$PKG" -r "$ROOT/requirements-api.txt"

# app code only: the API package and the shared DB helper (nothing else from the repo)
mkdir -p "$PKG/api"
cp "$ROOT"/api/__init__.py "$ROOT"/api/main.py "$ROOT"/api/db.py "$ROOT"/api/queries.py \
   "$ROOT"/api/lambda_handler.py "$PKG/api/"
cp "$ROOT/db_connect.py" "$PKG/"
# Amazon RDS CA bundle (public) for TLS + IAM auth; Lambda env DB_SSL_CA=/var/task/certs/global-bundle.pem
curl -fsS -o "$PKG/certs/global-bundle.pem" https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem

find "$PKG" -name "__pycache__" -type d -prune -exec rm -rf {} +
(cd "$PKG" && zip -q -r -X "$OUT/api.zip" .)
echo "Built $OUT/api.zip ($(du -h "$OUT/api.zip" | cut -f1))"
