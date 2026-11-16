"""
One-time: refresh article titles from Crossref so they keep chemical formatting
(<sub>, <sup>, <i>) - stored titles were cleaned by the old tag-stripper ("CsPbBr 3").

For every article published in the last 30 days, the title Crossref has for its DOI
is cleaned with poc_feeds.clean_title (the same cleaner RSS and Crossref ingestion use).
A title is updated only when it is the SAME text as the stored one (ignoring case,
spaces, punctuation and tags), so only formatting, stray spaces and (for some RSC
papers whose Crossref record changed since) capitalisation change.

Spacing: Wiley, Science and ACS-from-RSS titles were stored from tagless RSS titles, so
their spacing is right ("Ni/Ni3P@C"), while Crossref puts every tag on its own line and
the cleaner has to guess. For those, the tags come from Crossref and the spacing from the
stored title - except around a tagged span the old stripper left gaps on both sides of
("CsPbBr 3 Nanocrystals"), where the cleaner's spacing is used. Skipped:
  - text differs        Crossref's wording differs (e.g. a corrected title) - left alone
  - formatting lost     the Crossref title has fewer <sub>/<sup>/<i> than the stored one
  - Springer Nature     its Crossref titles drop sub/sup (Nature RSS: "8<sub>5</sub> knots",
                        Crossref: "85 knots"), so they would only lose information
Only the title column changes. Topics are unaffected (same text).

Usage (from the project folder)
    python scripts/refresh_titles.py            # dry run: report + CSV, changes nothing
    python scripts/refresh_titles.py --apply    # write the updates
"""

import argparse
import csv
import os
import re
import sys
import time
from collections import Counter

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from load_poc import connect                      # noqa: E402  (also loads .env)
from poc_feeds import KEPT_TAG_RE, clean_title, plain_title, spaced_like, text_key    # noqa: E402

DAYS = 30
BATCH = 40                    # DOIs per Crossref request (filter=doi:a,doi:b,...)
PAUSE = 1.0                   # seconds between requests
SKIP_PUBLISHERS = {"Springer Nature"}
PREVIEW = "logs/refresh_titles_preview.csv"


def crossref_titles(dois, session):
    """{doi (lower case): raw Crossref title} for one batch of DOIs."""
    params = {"filter": ",".join(f"doi:{d}" for d in dois), "select": "DOI,title", "rows": len(dois)}
    for attempt in range(3):
        r = session.get("https://api.crossref.org/works", params=params, timeout=60)
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        print(f"  Crossref answered {r.status_code}; waiting {10 * (attempt + 1)} s", flush=True)
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()
    return {it["DOI"].lower(): " ".join(it.get("title", [])) for it in r.json()["message"]["items"]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the updates (default: dry run)")
    args = ap.parse_args()

    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    session = requests.Session()
    session.headers.update({"Accept": "application/json",
                            "User-Agent": "ASAPChemHub/1.0" + (f" (mailto:{mailto})" if mailto else "")})
    if not mailto:
        print("note: CROSSREF_MAILTO not set in .env - using Crossref's public pool")

    db = connect()
    cur = db.cursor()
    cur.execute("""SELECT a.article_id, a.doi, a.title, j.publisher, j.name,
                          j.publisher IN ('Wiley', 'AAAS') OR (j.publisher = 'ACS' AND a.abstract IS NOT NULL)
                     FROM articles a JOIN journals j USING (journal_id)
                    WHERE a.published_date >= CURDATE() - INTERVAL %s DAY""", (DAYS,))
    rows = cur.fetchall()
    todo = [r for r in rows if r[3] not in SKIP_PUBLISHERS]
    print(f"{len(rows)} articles in the last {DAYS} days; {len(rows) - len(todo)} Springer Nature skipped; "
          f"asking Crossref for {len(todo)} in batches of {BATCH}")

    found = {}
    for i in range(0, len(todo), BATCH):
        dois = [r[1] for r in todo[i:i + BATCH]]
        try:
            t0 = time.time()
            found.update(crossref_titles(dois, session))
            took = f"{time.time() - t0:.1f} s"
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  batch {i // BATCH + 1}: Crossref failed ({type(e).__name__}) - these stay as they are")
            took = "failed"
        print(f"  {min(i + BATCH, len(todo))}/{len(todo)}  ({took})", flush=True)
        time.sleep(PAUSE)
    print()

    outcome, by_pub, changes, differs = Counter(), Counter(), [], []
    spacing = Counter()
    for article_id, doi, old, publisher, journal, from_rss in todo:
        raw = found.get(doi.lower())
        if raw is None:
            outcome["not in Crossref"] += 1
            continue
        new = clean_title(raw)
        if from_rss and new != old:
            respaced = spaced_like(new, old)
            spacing["stored title" if respaced else "cleaner (text did not line up)"] += 1
            new = respaced or new
        if not new or new == old:
            outcome["unchanged"] += 1
        elif text_key(new) != text_key(old):
            outcome["skipped: text differs"] += 1
            differs.append((journal, old, new))
        elif len(KEPT_TAG_RE.findall(new)) < len(KEPT_TAG_RE.findall(old)):
            outcome["skipped: formatting lost"] += 1
        else:
            same_case = re.sub(r"\W+", "", plain_title(new)) == re.sub(r"\W+", "", plain_title(old))
            outcome["update" if same_case else "update (capitalisation changes too)"] += 1
            by_pub[publisher] += 1
            changes.append((article_id, doi, journal, old, new))

    print("\nOutcome:")
    for k, v in outcome.most_common():
        print(f"  {k:26s} {v:5d}")
    print("Updates by publisher: " + ", ".join(f"{p} {n}" for p, n in by_pub.most_common()))
    print("Spacing for RSS-sourced titles taken from: " + ", ".join(f"{k} {v}" for k, v in spacing.items()))

    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    with open(PREVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["action", "journal", "doi", "before", "after"])
        w.writerows(("update", j, d, o, n) for _, d, j, o, n in changes)
        w.writerows(("skip: text differs", j, "", o, n) for j, o, n in differs)
    print(f"All proposed changes and skips: {PREVIEW}")

    if differs:
        print("\nExamples skipped because the text differs:")
        for j, o, n in differs[:3]:
            print(f"  [{j}]\n    stored:   {o}\n    crossref: {n}")

    if not args.apply:
        print("\nDry run: nothing written. Run with --apply to update.")
        return
    updated = 0
    for article_id, _, _, old, new in changes:
        cur.execute("UPDATE articles SET title = %s WHERE article_id = %s AND title = %s",
                    (new[:1000], article_id, old))
        updated += cur.rowcount
    db.commit()
    print(f"\nUpdated {updated} titles.")


if __name__ == "__main__":
    sys.exit(main())
