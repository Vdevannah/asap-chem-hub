"""
ASAP Chem Hub - topic tuning helper
===================================
Re-tags every article in poc_results.csv with the rules in topics.py and
shows, for each topic, which articles match and which words caused it.
No internet needed - run it as often as you like while editing topics.py.

Usage
    python tune_topics.py                 # summary + top matches per topic
    python tune_topics.py --topic "Total synthesis" --all
    python tune_topics.py --near          # also show near misses (score 1)

Writes topics_review.csv with every match, to scan in Excel.
"""

import argparse
import csv
import sys

from topics import TOPICS, explain, qualifies


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="show only this topic")
    ap.add_argument("--all", action="store_true", help="list every match, not just 15")
    ap.add_argument("--near", action="store_true", help="show near misses (below the threshold)")
    args = ap.parse_args()

    try:
        rows = list(csv.DictReader(open("poc_results.csv", encoding="utf-8")))
    except FileNotFoundError:
        sys.exit("poc_results.csv not found - run: python poc_feeds.py")
    print(f"{len(rows)} articles in poc_results.csv\n")

    matched, near = {t: [] for t in TOPICS}, {t: [] for t in TOPICS}
    for r in rows:
        for topic, (score, hits) in explain(r["title"], r["abstract"]).items():
            (matched if qualifies(topic, score, hits) else near)[topic].append((score, hits, r))

    topics = [args.topic] if args.topic else list(TOPICS)
    for t in topics:
        if t not in TOPICS:
            sys.exit(f"Unknown topic '{t}'. Topics: {', '.join(TOPICS)}")
        items = sorted(matched[t], key=lambda x: -x[0])
        print(f"=== {t}: {len(items)} articles ({100*len(items)/max(len(rows),1):.0f}%) ===")
        for score, hits, r in (items if args.all else items[:15]):
            print(f"  [{score}] [{r['journal'][:16]}] {r['title'][:85]}")
            print(f"        matched: {', '.join(hits)}")
        if args.near and near[t]:
            print(f"  -- near misses (below threshold, not tagged): {len(near[t])}")
            for score, hits, r in near[t][:8]:
                print(f"     [{r['journal'][:16]}] {r['title'][:80]}  <- {', '.join(hits)}")
        print()

    with open("topics_review.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["topic", "score", "matched", "journal", "title", "doi"])
        for t in TOPICS:
            for score, hits, r in sorted(matched[t], key=lambda x: -x[0]):
                w.writerow([t, score, "; ".join(hits), r["journal"], r["title"], r["doi"]])
    tagged = sum(1 for r in rows if any(qualifies(tp, s, h) for tp, (s, h) in explain(r["title"], r["abstract"]).items()))
    print(f"{tagged}/{len(rows)} articles have at least one topic.")
    print("Wrote topics_review.csv")


if __name__ == "__main__":
    main()
