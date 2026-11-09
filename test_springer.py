"""
ASAP Chem Hub - Springer Nature API test
========================================
Checks whether the Springer Nature APIs fill the gaps found in the feed PoC:
  * Meta API         -> abstract + open-access flag for each Nature article
  * Open Access API  -> Figure 1 for open-access articles (e.g. all of Nat. Commun.)

Reads the Nature DOIs from poc_results.csv (run poc_feeds.py first) and the
API keys from .env:
    SPRINGER_META_KEY=...
    SPRINGER_OA_KEY=...

Usage
    pip install python-dotenv
    python test_springer.py            # first 15 Nature DOIs
    python test_springer.py --max 40

Writes preview_springer.html - open it to check the figures look right.
Images are shown from Springer Nature's own URL, not downloaded.
"""

import argparse
import csv
import html
import os
import re
import sys
import time
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()
META_KEY = os.environ.get("SPRINGER_META_KEY", "")
OA_KEY = os.environ.get("SPRINGER_OA_KEY", "")

META_URL = "https://api.springernature.com/meta/v2/json"
OA_URL = "https://api.springernature.com/openaccess/jats"
TAG_RE = re.compile(r"<[^>]+>")


def clean(text) -> str:
    """Abstracts come as a string or as nested dicts/lists - flatten to text."""
    if isinstance(text, dict):
        text = " ".join(clean(v) for v in text.values())
    elif isinstance(text, list):
        text = " ".join(clean(v) for v in text)
    text = html.unescape(TAG_RE.sub(" ", str(text or "")))
    return re.sub(r"\s+", " ", text).strip()


def meta_lookup(doi, session):
    """Abstract and open-access flag from the Meta API."""
    r = session.get(META_URL, params={"q": f"doi:{doi}", "api_key": META_KEY}, timeout=30)
    if r.status_code != 200:
        return None, None, f"Meta API HTTP {r.status_code}"
    records = r.json().get("records", [])
    if not records:
        return None, None, "Meta API: no record"
    rec = records[0]
    is_oa = str(rec.get("openaccess", "")).lower() == "true"
    return clean(rec.get("abstract", "")), is_oa, None


def figure1_url(doi, session):
    """URL of Figure 1 from the article's open-access JATS XML."""
    r = session.get(OA_URL, params={"q": f"doi:{doi}", "api_key": OA_KEY}, timeout=60)
    if r.status_code != 200:
        return None, f"OA API HTTP {r.status_code}"
    xml = r.text
    if "<article" not in xml:
        return None, "OA API: article not found (not indexed yet?)"
    if "<body" not in xml:
        return None, "OA API: metadata only, no full text yet"
    fig = re.search(r"<fig\b.*?</fig>", xml, re.DOTALL)
    if not fig:
        return None, "OA API: full text but no figure"
    href = re.search(r'<graphic[^>]*?(?:xlink:)?href="([^"]+)"', fig.group(0))
    if not href:
        return None, "OA API: figure has no image reference"
    name = href.group(1).split("/")[-1]
    if not re.search(r"\.(png|jpe?g|gif)$", name, re.IGNORECASE):
        name += ".png"
    # Springer Nature's public image server; 'lw685' = 685 px wide
    url = ("https://media.springernature.com/lw685/springer-static/image/"
           f"art%3A{quote(doi, safe='')}/MediaObjects/{name}")
    return url, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=15, help="how many Nature DOIs to test")
    args = ap.parse_args()

    if not META_KEY or not OA_KEY:
        sys.exit("Missing SPRINGER_META_KEY or SPRINGER_OA_KEY in .env")
    try:
        rows = [r for r in csv.DictReader(open("poc_results.csv", encoding="utf-8"))
                if r["publisher"] == "Springer Nature" and r["doi"]]
    except FileNotFoundError:
        sys.exit("poc_results.csv not found - run: python poc_feeds.py --only \"Springer Nature\"")
    rows = rows[: args.max]
    print(f"Testing {len(rows)} Nature articles ...\n")

    session = requests.Session()
    session.headers["User-Agent"] = "ASAPChemHub-PoC/0.1 (academic literature feed prototype)"

    results = []
    for r in rows:
        abstract, is_oa, err = meta_lookup(r["doi"], session)
        fig, fig_err = (None, "not open access")
        if is_oa:
            fig, fig_err = figure1_url(r["doi"], session)
        results.append({**r, "api_abstract": abstract or "", "is_oa": is_oa,
                        "figure": fig or "", "note": err or fig_err or ""})
        status = "OA " if is_oa else ("   " if is_oa is False else "?? ")
        print(f"{status}{r['journal'][:24]:24s} abstract:{'yes' if abstract else 'no ':3s} "
              f"figure:{'yes' if fig else 'no ':3s} {(err or fig_err or '')[:40]}")
        time.sleep(0.6)   # stay well inside the free-tier rate limit

    n = len(results)
    if not n:
        sys.exit("No Nature DOIs in poc_results.csv")
    oa = sum(1 for x in results if x["is_oa"])
    print(f"\n=== Summary ===")
    print(f"Abstract from Meta API : {sum(bool(x['api_abstract']) for x in results)}/{n}")
    print(f"Open access            : {oa}/{n}")
    print(f"Figure 1 found         : {sum(bool(x['figure']) for x in results)}/{oa} open-access articles")

    cards = []
    for x in results:
        img = (f'<img src="{html.escape(x["figure"])}" loading="lazy">' if x["figure"]
               else f'<div class="noimg">{html.escape(x["journal"])}<br><small>no figure</small></div>')
        cards.append(f"""<div class="card"><div class="fig">{img}</div><div>
          <div class="j">{html.escape(x['journal'])} · {'Open access' if x['is_oa'] else 'Subscription'}</div>
          <a href="https://doi.org/{html.escape(x['doi'])}" target="_blank">{html.escape(x['title'])}</a>
          <p>{html.escape(x['api_abstract'][:400])}</p></div></div>""")
    with open("preview_springer.html", "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>Springer API test</title>
<style>body{{font-family:system-ui,sans-serif;background:#f4f5f7;padding:16px}}
.card{{display:flex;gap:16px;background:#fff;border-radius:10px;padding:14px;margin:12px auto;max-width:1000px}}
.fig{{flex:0 0 320px;display:flex;align-items:center;justify-content:center}}
.fig img{{max-width:320px;max-height:220px}}.noimg{{color:#999;text-align:center}}
.j{{color:#666;font-size:13px}}a{{font-weight:600;color:#1a3d7c;text-decoration:none}}
p{{font-size:14px;color:#333}}</style>{''.join(cards)}""")
    print("\nWrote preview_springer.html (open it to check the figures)")


if __name__ == "__main__":
    main()
