#!/bin/sh
# Entry point of the jobs image. Same commands as scripts/run_articles.sh, without the local
# Docker / launchd parts. Output goes to stdout -> CloudWatch Logs.
#   articles   ingest.py articles, then ingest.py figures (both always run; fails if either failed)
#   patents    ingest.py patents
#   cleanup    ingest.py cleanup
#   figures    ingest.py figures
#   import ... scripts/import_db.py ... (one-off migration, admin task only)
#   anything else is run as a command (e.g. python retag_topics.py --add new --days 30)
set -u
job="${1:-articles}"
[ $# -gt 0 ] && shift
case "$job" in
  articles)
    a=0; f=0
    python -u ingest.py articles || a=$?
    python -u ingest.py figures || f=$?
    echo "=== run end (articles exit $a, figures exit $f)"
    [ "$a" -eq 0 ] && [ "$f" -eq 0 ]
    ;;
  patents|cleanup|figures)
    exec python -u ingest.py "$job" "$@"
    ;;
  import)
    exec python -u scripts/import_db.py "$@"
    ;;
  *)
    exec "$job" "$@"
    ;;
esac
