"""
ASAP Chem Hub - Springer Nature API helpers
===========================================
  * meta_lookup(doi)  -> abstract + open-access flag (Meta API)
  * figure1_url(doi)  -> Figure 1 of an open-access article (Open Access API)

Keys come from .env: SPRINGER_META_KEY, SPRINGER_OA_KEY.
Images are referenced by Springer Nature's own URL, never downloaded.
"""

import html
import os
import re
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv()
META_KEY = os.environ.get("SPRINGER_META_KEY", "")
OA_KEY = os.environ.get("SPRINGER_OA_KEY", "")
META_URL = "https://api.springernature.com/meta/v2/json"
OA_URL = "https://api.springernature.com/openaccess/jats"
_TAG = re.compile(r"<[^>]+>")


def enabled() -> bool:
    return bool(META_KEY and OA_KEY)


def _clean(text) -> str:
    if isinstance(text, dict):
        text = " ".join(_clean(v) for v in text.values())
    elif isinstance(text, list):
        text = " ".join(_clean(v) for v in text)
    text = html.unescape(_TAG.sub(" ", str(text or "")))
    return re.sub(r"\s+", " ", text).strip()


def meta_lookup(doi, session):
    """(abstract, is_open_access, error)"""
    r = session.get(META_URL, params={"q": f"doi:{doi}", "api_key": META_KEY}, timeout=30)
    if r.status_code != 200:
        return None, None, f"Meta API HTTP {r.status_code}"
    records = r.json().get("records", [])
    if not records:
        return None, None, "Meta API: no record"
    rec = records[0]
    return _clean(rec.get("abstract", "")), str(rec.get("openaccess", "")).lower() == "true", None


def figure1_url(doi, session):
    """(image_url, reason_if_missing)"""
    r = session.get(OA_URL, params={"q": f"doi:{doi}", "api_key": OA_KEY}, timeout=60)
    if r.status_code != 200:
        return None, f"OA API HTTP {r.status_code}"
    xml = r.text
    if "<article" not in xml:
        return None, "not indexed yet"
    if "<body" not in xml:
        return None, "metadata only, no full text yet"
    fig = re.search(r"<fig\b.*?</fig>", xml, re.DOTALL)
    if not fig:
        return None, "full text but no figure"
    href = re.search(r'<graphic[^>]*?(?:xlink:)?href="([^"]+)"', fig.group(0))
    if not href:
        return None, "figure has no image reference"
    name = href.group(1).split("/")[-1]
    if not re.search(r"\.(png|jpe?g|gif)$", name, re.IGNORECASE):
        name += ".png"
    return ("https://media.springernature.com/lw685/springer-static/image/"
            f"art%3A{quote(doi, safe='')}/MediaObjects/{name}"), None
