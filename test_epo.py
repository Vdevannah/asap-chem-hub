"""
ASAP Chem Hub - EPO OPS patent test (Phase 3 proof of concept)
==============================================================
Question this answers:
    "Can we get last week's chemistry/pharma patent publications from EPO OPS,
     with title, applicant, number, date, abstract and CPC codes?"

Keys come from .env (never put them in code):
    EPO_KEY=your-consumer-key
    EPO_SECRET=your-consumer-secret

Usage
    python test_epo.py                       # WO, last 14 days, all four streams
    python test_epo.py --office EP

Writes epo_results.csv and preview_patents.html.
"""

import argparse
import base64
import csv
import html
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

from topics import tag_topics


load_dotenv()
KEY = os.environ.get("EPO_KEY", "")
SECRET = os.environ.get("EPO_SECRET", "")
AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
PAGE = 100                                   # OPS returns at most 100 per request

# Patent streams: each is its own EPO search.
# 'cpc=/low X' = group X plus all its subgroups (EPO needs this for group-level codes like A61K47/68).
# Every patent gets the same keyword topics as the articles (topics.py).
# The four focused streams also add their own name as a topic, so a patent can have several.
GENERAL = "General chemistry"                # broad search; topics come from topics.py only
STREAMS = {
    GENERAL:                        'cpc=C07 or cpc=A61K or cpc=A61P',
    "Antibody-drug conjugates":     'cpc=/low A61K47/68',
    "Antibodies":                   'cpc=/low C07K16',
    "Targeted protein degradation": '(cpc=C07D or cpc=C07K or cpc=A61K31 or cpc=A61P) and '
                                    '(ta any "degrader degraders PROTAC PROTACs heterobifunctional cereblon" '
                                    'or ta="molecular glue")',
    "OLED materials and devices":   'cpc=/low H10K50 or cpc=/low H10K85 or cpc=/low C09K11/06',
}


def get_token(session):
    basic = base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    r = session.post(AUTH_URL, data={"grant_type": "client_credentials"},
                     headers={"Authorization": f"Basic {basic}",
                              "Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"Could not get an EPO token (HTTP {r.status_code}): {r.text[:300]}\n"
                 "Check EPO_KEY and EPO_SECRET in .env.")
    return r.json()["access_token"]


def _text(el):
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_documents(xml_text):
    """Turn an OPS biblio search response into a list of patent dicts."""
    root = ET.fromstring(xml_text)
    total = int(root.find(".//{*}biblio-search").get("total-result-count", "0"))
    patents = []
    for doc in root.findall(".//{*}exchange-document"):
        country, number, kind = doc.get("country", ""), doc.get("doc-number", ""), doc.get("kind", "")
        biblio = doc.find("{*}bibliographic-data")
        if biblio is None:
            continue
        pub_date = ""
        for did in biblio.findall("{*}publication-reference/{*}document-id"):
            if did.get("document-id-type") == "docdb":
                pub_date = _text(did.find("{*}date"))
        titles = biblio.findall("{*}invention-title")
        title = next((_text(t) for t in titles if t.get("lang") == "en"), _text(titles[0]) if titles else "")
        applicants = [_text(a.find("{*}applicant-name/{*}name"))
                      for a in biblio.findall("{*}parties/{*}applicants/{*}applicant")
                      if a.get("data-format") == "epodoc"]
        inventors = [_text(i.find("{*}inventor-name/{*}name"))
                     for i in biblio.findall("{*}parties/{*}inventors/{*}inventor")
                     if i.get("data-format") == "epodoc"]
        cpcs = []
        for c in biblio.findall("{*}patent-classifications/{*}patent-classification"):
            parts = [_text(c.find(f"{{*}}{p}")) for p in ("section", "class", "subclass", "main-group", "subgroup")]
            if all(parts):
                cpcs.append(f"{parts[0]}{parts[1]}{parts[2]}{parts[3]}/{parts[4]}")
        abstracts = doc.findall("{*}abstract")
        abstract = next((_text(a) for a in abstracts if a.get("lang") == "en"), "")
        pn = f"{country}{number}{kind}"
        patents.append({
            "publication_number": pn, "office": country, "title": title,
            "applicants": "; ".join(dict.fromkeys(a for a in applicants if a)),
            "inventors": "; ".join(dict.fromkeys(i for i in inventors if i)),
            "abstract": abstract, "cpc_codes": "; ".join(dict.fromkeys(cpcs)),
            "family_id": doc.get("family-id", ""),
            "published": f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:]}" if len(pub_date) == 8 else pub_date,
            "patent_url": f"https://worldwide.espacenet.com/patent/search?q=pn%3D{pn}",
            "topics": tag_topics(title, abstract),     # same keyword topics as the articles
        })
    return total, patents


def fetch_stream(session, token, query, max_n):
    out, first = [], 1
    while first <= max_n:
        last = min(first + PAGE - 1, max_n)
        r = session.get(SEARCH_URL, params={"q": query, "Range": f"{first}-{last}"},
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/xml"},
                        timeout=60)
        if r.status_code == 404:
            break
        if r.status_code != 200:
            print(f"  Search failed (HTTP {r.status_code}): {r.text[:300]}")
            break
        total, batch = parse_documents(r.text)
        out += batch
        print(f"  fetched {first}-{min(last, total)} of {total}")
        if last >= total or not batch:
            break
        first = last + 1
        time.sleep(1)
    return out


def count(session, token, query):
    """How many documents match a query (0 if none). Prints EPO's message on errors."""
    r = session.get(SEARCH_URL, params={"q": query, "Range": "1-1"},
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/xml"},
                    timeout=60)
    if r.status_code == 200:
        return int(ET.fromstring(r.text).find(".//{*}biblio-search").get("total-result-count", "0"))
    if r.status_code != 404:
        print(f"      HTTP {r.status_code}: {r.text[:200]}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--office", default="WO", help="WO, EP or US")
    ap.add_argument("--days", type=int, default=14, help="EPO data lags ~1 week, so 14 is the default")
    ap.add_argument("--max", type=int, default=300, help="most patents per stream")
    args = ap.parse_args()
    if not KEY or not SECRET:
        sys.exit("Add EPO_KEY and EPO_SECRET to .env first.")

    end, start = date.today(), date.today() - timedelta(days=args.days)
    session = requests.Session()
    token = get_token(session)
    print("EPO token: OK")

    found = {}                                   # publication_number -> patent
    for stream, sq in STREAMS.items():
        query = f'pn={args.office} and pd within "{start:%Y%m%d} {end:%Y%m%d}" and ({sq})'
        print(f"\n[{stream}]\n  {query}")
        got = fetch_stream(session, token, query, args.max)
        if not got:
            print("  0 found.")
        for p in got:
            keep = found.setdefault(p["publication_number"], p)
            if stream != GENERAL and stream not in keep["topics"]:
                keep["topics"].append(stream)
        time.sleep(1)
    patents, total = list(found.values()), len(found)

    if not patents:
        return
    n = len(patents)
    pct = lambda k: f"{100 * sum(bool(p[k]) for p in patents) / n:5.1f}%"
    print(f"\n=== {n} unique patents across all streams ===")
    for k in ("title", "applicants", "abstract", "cpc_codes", "published"):
        print(f"  {k:12s} {pct(k)}")
    counts = {}
    for p in patents:
        for t in p["topics"]:
            counts[t] = counts.get(t, 0) + 1
    print("\nPatents per topic:")
    for t, c in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {c:4d}  {t}")
    print("\nSample:")
    for p in patents[:8]:
        print(f"  {p['publication_number']:16s} {p['published']}  {p['applicants'][:30]:30s}  {p['title'][:60]}")

    with open("epo_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(patents[0].keys()))
        w.writeheader()
        for p in patents:
            w.writerow({**p, "topics": "; ".join(p["topics"])})
    cards = "".join(
        f"""<div class="card"><div class="m">{html.escape(p['office'])} · {html.escape(p['publication_number'])} · {html.escape(p['published'])}</div>
        <a href="{html.escape(p['patent_url'])}" target="_blank">{html.escape(p['title'] or '(no English title)')}</a>
        <div class="ap">{html.escape(p['applicants'])}</div><p>{html.escape(p['abstract'][:350])}</p>
        <div>{''.join(f'<span class="tag">{html.escape(t)}</span>' for t in p['topics'])}</div></div>"""
        for p in patents)
    with open("preview_patents.html", "w", encoding="utf-8") as f:
        f.write(f"""<!doctype html><meta charset="utf-8"><title>EPO patent test</title><style>
body{{font-family:system-ui,sans-serif;background:#f4f5f7;padding:16px}}
.card{{background:#fff;border-radius:10px;padding:14px;margin:12px auto;max-width:900px}}
.m,.ap{{color:#666;font-size:13px}}a{{font-weight:600;color:#1a3d7c;text-decoration:none}}
p{{font-size:14px;color:#333}}.tag{{background:#e8eefc;color:#1a3d7c;border-radius:10px;padding:2px 8px;margin:2px;font-size:12px;display:inline-block}}
</style>{cards}""")
    print("\nWrote epo_results.csv and preview_patents.html")


if __name__ == "__main__":
    main()
