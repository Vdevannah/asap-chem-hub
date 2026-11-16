#!/bin/bash
# Hourly article ingestion for ASAP Chem Hub (run by launchd: ~/Library/LaunchAgents/com.asapchemhub.ingest.plist).
# Runs `ingest.py articles` then `ingest.py figures`, appending timestamped output to logs/ingest.log.
# Starts the MySQL container if needed; exits quietly if Docker Desktop is not running.
# Safe to run by hand too:  scripts/run_articles.sh

set -u
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT/logs"
LOG="$LOG_DIR/ingest.log"
CONTAINER="asap-chem-hub-db"

# launchd starts jobs with a minimal PATH; add Docker Desktop's and Homebrew's locations
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.docker/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LOG_DIR"
# keep the log from growing without limit: roll over at 5 MB (one old copy kept)
if [ -f "$LOG" ] && [ "$(stat -f %z "$LOG")" -gt 5242880 ]; then
  mv -f "$LOG" "$LOG.1"
fi

stamp() { while IFS= read -r line; do printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$line"; done; }
say() { echo "$*" | stamp >> "$LOG"; }

cd "$PROJECT" || exit 1

# 1. Docker Desktop must be running; if not, skip this run quietly
if ! docker info >/dev/null 2>&1; then
  say "skipped: Docker Desktop is not running"
  exit 0
fi

# 2. Start the database container if it is not running
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  say "database container not running: docker compose up -d"
  docker compose up -d 2>&1 | stamp >> "$LOG"
fi

# shellcheck disable=SC1091
source "$PROJECT/.venv/bin/activate" || { say "error: could not activate .venv"; exit 1; }

# 3. Wait until MySQL accepts connections (max 60 s). Uses the app's own connection settings from .env.
db_ready() {
  python - <<'PY' >/dev/null 2>&1
from api.db import get_cursor
with get_cursor() as cur:
    cur.execute("SELECT 1")
PY
}
for _ in $(seq 1 30); do
  db_ready && break
  sleep 2
done
if ! db_ready; then
  say "error: database did not accept connections within 60 s; skipping this run"
  exit 1
fi

# 4. Ingest
say "=== run start"
python -u ingest.py articles 2>&1 | stamp >> "$LOG"
articles_status=${PIPESTATUS[0]}
python -u ingest.py figures 2>&1 | stamp >> "$LOG"
figures_status=${PIPESTATUS[0]}
say "=== run end (articles exit $articles_status, figures exit $figures_status)"

[ "$articles_status" -eq 0 ] && [ "$figures_status" -eq 0 ]
