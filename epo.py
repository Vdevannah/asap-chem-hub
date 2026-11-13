"""
ASAP Chem Hub - EPO Open Patent Services (OPS) client
=====================================================
Used by ingest.py (patents job). test_epo.py is the Phase 3 proof of concept.

Keys come from .env:  EPO_KEY=...  EPO_SECRET=...

EPO allows only a few search requests per minute (the X-Throttling-Control
header says e.g. "search=green:5"), so every search waits accordingly.
"""

import base64
import os
import re
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv

from topics import tag_topics

load_dotenv()
AUTH_URL = "https://ops.epo.org/3.2/auth/accesstoken"
SEARCH_URL = "https://ops.epo.org/3.2/rest-services/published-data/search/biblio"
PAGE = 100                      # OPS returns at most 100 documents per request
MAX_PER_QUERY = 2000            # OPS will not page past 2000 results

# Each stream is its own EPO search.
# Every patent gets the same keyword topics as the articles (topics.py);
# the focused streams also add their own name as a topic.
# 'cpc=/low X' = group X plus all its subgroups.
GENERAL = "General chemistry"   # broad search; topics come from topics.py only
STREAMS = {
    GENERAL:                        'cpc=C07 or cpc=A61K or cpc=A61P',
    "Antibody-drug conjugates":     'cpc=/low A61K47/68',
    "Antibodies":                   'cpc=/low C07K16',
    "Targeted protein degradation": '(cpc=C07D or cpc=C07K or cpc=A61K31 or cpc=A61P) and '
                                    '(ta any "degrader degraders PROTAC PROTACs heterobifunctional cereblon" '
                                    'or ta="molecular glue")',
    "OLED materials and devices":   'cpc=/low H10K50 or cpc=/low H10K85 or cpc=/low C09K11/06',
}
STREAM_TOPICS = [s for s in STREAMS if s != GENERAL]


def enabled():
    return bool(os.environ.get("EPO_KEY") and os.environ.get("EPO_SECRET"))


class Client:
    """Holds the access token (valid 20 minutes) and paces requests."""

    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.token, self.token_time, self.wait = None, 0, 12.0   # until EPO tells us its limit

    def _auth(self):
        key, secret = os.environ["EPO_KEY"], os.environ["EPO_SECRET"]
        basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
        r = self.session.post(AUTH_URL, data={"grant_type": "client_credentials"},
                              headers={"Authorization": f"Basic {basic}",
                                       "Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
        r.raise_for_status()
        self.token, self.token_time = r.json()["access_token"], time.time()

    def _pace(self, throttle_header):
        """'busy (search=green:5, ...)' -> wait 60/5 s; slow down more if not green."""
        m = re.search(r"search=(\w+):(\d+)", throttle_header or "")
        if m:
            colour, per_minute = m.group(1), max(int(m.group(2)), 1)
            self.wait = 60 / per_minute + 0.5
            if colour != "green":
                self.wait *= 3

    def search(self, query, first, last):
        """One page of results -> (status_code, xml_text). Retries once if throttled."""
        for attempt in range(2):
            if not self.token or time.time() - self.token_time > 15 * 60:
                self._auth()
            r = self.session.get(SEARCH_URL, params={"q": query, "Range": f"{first}-{last}"},
                                 headers={"Authorization": f"Bearer {self.token}",
                                          "Accept": "application/xml"}, timeout=60)
            self._pace(r.headers.get("X-Throttling-Control"))
            time.sleep(self.wait)
            if r.status_code == 403 and attempt == 0 and "throttl" in r.text.lower():
                time.sleep(60)
                continue
            if r.status_code == 400 and attempt == 0 and "invalid_access_token" in r.text.lower():
                self.token = None
                continue
            return r.status_code, r.text
        return r.status_code, r.text

    def fetch(self, query, max_n=MAX_PER_QUERY):
        """All patents for a query -> (patents, error or None)."""
        out, first = [], 1
        while first <= max_n:
            last = min(first + PAGE - 1, max_n)
            status, text = self.search(query, first, last)
            if status == 404:                        # OPS says "no results" with a 404
                break
            if status != 200:
                return out, f"HTTP {status}: {text[:200]}"
            total, batch = parse_documents(text)
            out += batch
            if last >= total or not batch:
                break
            first = last + 1
        return out, None


def _text(el):
    return " ".join("".join(el.itertext()).split()) if el is not None else ""


def parse_documents(xml_text):
    """Turn an OPS biblio search response into (total, list of patent dicts)."""
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
            "published": f"{pub_date[:4]}-{pub_date[4:6]}-{pub_date[6:]}" if len(pub_date) == 8 else "",
            "patent_url": f"https://worldwide.espacenet.com/patent/search?q=pn%3D{pn}",
            "topics": tag_topics(title, abstract),
        })
    return total, patents
