"""
ASAP Chem Hub - Proof of Concept
===================================
Question this script answers:
    "How many new articles can we show WITH a graphical abstract,
     using only the publishers' own RSS feeds?"

What it does
    1. Downloads the RSS feed for each journal in JOURNALS.
    2. For every article, extracts title, authors, date, DOI, abstract
       and the graphical-abstract image URL (if the feed provides one).
    3. Optionally fills missing authors/dates from the Crossref API.
    4. Tags each article with research topics (PROTAC, covalent, ...)
       using simple keyword/synonym rules - no LLM.
    5. Prints a coverage report per journal and writes:
         - poc_results.csv  (one row per article)
         - preview.html     (open in a browser to eyeball the figures)

Images are NOT downloaded or stored - the preview page links to the
publisher's own image URL, exactly as the feed provides it.

Usage
    pip install -r requirements.txt
    python poc_feeds.py                 # feeds only
    python poc_feeds.py --crossref      # also fill gaps from Crossref

Optional: set CROSSREF_MAILTO=you@example.com so Crossref puts you in
its "polite" pool (faster, more reliable).
"""

import argparse
import csv
import html
import os
import re
import sys
import time
from urllib.parse import urljoin

import feedparser
import requests

# ---------------------------------------------------------------------------
# 1. Journals to test.  Feed URLs should be double-checked on each
#    publisher's "RSS" page - the script reports any feed that fails.
# ---------------------------------------------------------------------------
ACS = "https://pubs.acs.org/rss/{code}/asap.xml"
WILEY = "https://onlinelibrary.wiley.com/action/showFeed?jc={code}&type=etoc&feed=rss"
NATURE = "https://www.nature.com/{code}.rss"
# ChemRxiv blocks scripts on its own API, so preprints come from Crossref
# (every ChemRxiv DOI starts with 10.26434).
CHEMRXIV = "https://api.crossref.org/works"

JOURNALS = [
    # (display name,                    publisher,         feed URL)
    # --- ACS ---
    ("JACS",                            "ACS",             ACS.format(code="jacsat")),
    ("ACS Central Science",             "ACS",             ACS.format(code="acscii")),
    ("JACS Au",                         "ACS",             ACS.format(code="jaaucr")),
    ("Org. Lett.",                      "ACS",             ACS.format(code="orlef7")),
    ("J. Org. Chem.",                   "ACS",             ACS.format(code="joceah")),
    ("Org. Process Res. Dev.",          "ACS",             ACS.format(code="oprdfk")),
    ("J. Med. Chem.",                   "ACS",             ACS.format(code="jmcmar")),
    ("ACS Med. Chem. Lett.",            "ACS",             ACS.format(code="amclct")),
    ("J. Nat. Prod.",                   "ACS",             ACS.format(code="jnprdf")),
    ("ACS Catalysis",                   "ACS",             ACS.format(code="accacs")),
    ("Organometallics",                 "ACS",             ACS.format(code="orgnd7")),
    ("Chem. Rev.",                      "ACS",             ACS.format(code="chreay")),
    ("Acc. Chem. Res.",                 "ACS",             ACS.format(code="achre4")),
    # --- Wiley ---
    ("Angew. Chem. Int. Ed.",           "Wiley",           WILEY.format(code="15213773")),
    ("Chem. Eur. J.",                   "Wiley",           WILEY.format(code="15213765")),
    ("Eur. J. Org. Chem.",              "Wiley",           WILEY.format(code="10990690")),
    ("Adv. Synth. Catal.",              "Wiley",           WILEY.format(code="16154169")),
    ("ChemMedChem",                     "Wiley",           WILEY.format(code="18607187")),
    ("ChemBioChem",                     "Wiley",           WILEY.format(code="14397633")),
    ("ChemCatChem",                     "Wiley",           WILEY.format(code="18673899")),
    # --- RSC --- feeds.rsc.org froze in June 2026 and the new RSS lists only ~5 items,
    #             so RSC comes from Crossref by journal ISSN (no figures, full coverage)
    ("Chemical Science",                "RSC",             "crossref:issn:2041-6539"),
    ("Chem. Commun.",                   "RSC",             "crossref:issn:1364-548X"),
    ("Org. Biomol. Chem.",              "RSC",             "crossref:issn:1477-0539"),
    ("Org. Chem. Front.",               "RSC",             "crossref:issn:2052-4129"),
    ("RSC Med. Chem.",                  "RSC",             "crossref:issn:2632-8682"),
    ("RSC Chem. Biol.",                 "RSC",             "crossref:issn:2633-0679"),
    ("Chem. Soc. Rev.",                 "RSC",             "crossref:issn:1460-4744"),
    ("Nat. Prod. Rep.",                 "RSC",             "crossref:issn:1460-4752"),
    # --- Springer Nature (to test) ---
    ("Nature",                          "Springer Nature", "https://www.nature.com/nature.rss"),
    ("Nat. Commun. (chemistry)",        "Springer Nature", "https://www.nature.com/subjects/chemistry/ncomms.rss"),
    ("Nature Chemistry",                "Springer Nature", NATURE.format(code="nchem")),
    ("Nature Synthesis",                "Springer Nature", NATURE.format(code="natsynth")),
    ("Nature Catalysis",                "Springer Nature", NATURE.format(code="natcatal")),
    ("Nature Reviews Chemistry",        "Springer Nature", NATURE.format(code="natrevchem")),
    # --- AAAS (to test) ---
    ("Science (First Release)",         "AAAS",            "https://feeds.science.org/rss/science-aop.xml"),
    ("Science (latest issue)",          "AAAS",            "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science"),
    # --- Preprints (to test) - JSON API, not RSS ---
    ("ChemRxiv",                        "ChemRxiv",        CHEMRXIV),
]

# ACS RSS feeds list only the last few days (JACS: sometimes 2 items), so ACS also gets a
# Crossref backup by ISSN (print, electronic) - see ingest.job_crossref_backup. Checked against
# api.crossref.org/journals. Wiley stays RSS-only: Crossref dates Wiley papers by their earlier
# "Accepted Article" version, which would shift them.
ACS_ISSNS = {
    "JACS":                   ("0002-7863", "1520-5126"),
    "ACS Central Science":    ("2374-7943", "2374-7951"),
    "JACS Au":                ("2691-3704",),
    "Org. Lett.":             ("1523-7060", "1523-7052"),
    "J. Org. Chem.":          ("0022-3263", "1520-6904"),
    "Org. Process Res. Dev.": ("1083-6160", "1520-586X"),
    "J. Med. Chem.":          ("0022-2623", "1520-4804"),
    "ACS Med. Chem. Lett.":   ("1948-5875",),
    "J. Nat. Prod.":          ("0163-3864", "1520-6025"),
    "ACS Catalysis":          ("2155-5435",),
    "Organometallics":        ("0276-7333", "1520-6041"),
    "Chem. Rev.":             ("0009-2665", "1520-6890"),
    "Acc. Chem. Res.":        ("0001-4842", "1520-4898"),
}

# 2. Topic rules live in topics.py (shared with tune_topics.py and, later, the app)
from topics import TOPICS, tag_topics

HEADERS = {
    "User-Agent": "ASAPChemHub-PoC/0.1 (academic literature feed prototype)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>?#]+", re.IGNORECASE)
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Titles: one cleaner for RSS and Crossref. A stored title is a small HTML fragment that keeps
# only <sub>, <sup> and <i> (the website renders exactly these via RichText); every other tag
# and every attribute is dropped, and < > in the text are escaped.
# ---------------------------------------------------------------------------
TITLE_TAGS = {"sub": "sub", "sup": "sup", "i": "i", "em": "i", "italic": "i"}   # JATS: jats:sub ...
ANY_TAG_RE = re.compile(r"<(/?)\s*(?:[\w-]+:)?([A-Za-z][\w-]*)\b[^<>]*>")       # tags, any namespace
DROP_ELEMENT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
# ACS sometimes deposits subscripts in Crossref as bold: "CsPbBr\n<b>3</b>". Keep the digits joined.
# Only right after an element symbol, with no space or just a line break ("CsPbBr\n<b>3</b>"): bold numbers
# after a word are compound labels ("compound <b>2</b>", "Ni <b>2</b>") and keep their space.
BOLD_DIGITS_RE = re.compile(r"(?:(?<=[A-Z])|(?<=[A-Z][a-z])|(?<=\)))(?:[^\S\n]*\n\s*)?<b>\s*(\d+)\s*</b>",
                            re.IGNORECASE)

# Whitespace next to a tag. Crossref pretty-prints every tag on its own line ("Na\n<sub>4</sub>\nFe"),
# so a newline there says nothing about a real space. Below, "\n" marks such formatting whitespace
# and " " a real space; the rules decide which formatting gaps are real word breaks.
FUNCTION_WORDS = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "into", "is", "its", "of", "on",
                  "or", "over", "per", "than", "the", "to", "under", "via", "vs", "with"}
# text that continues a formula after a subscript: element symbols, numbers, @ / = ] } ... and no
# lowercase word ("P@C", "EtP", "Se", "O", "Gd]", "1.5", "=O", "β", "CN"; not "into", "MOFs")
ELEMENTS = ("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se "
            "Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy "
            "Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm "
            # common groups written like elements: Me Et Pr Bu Ph Ar Ac Ts Bz Bn Cy Cp Tf Ms Py
            "Me Et Bu Ph Ts Bz Bn Cy Cp Tf Ms Py").split()
_ELEMENT = "|".join(sorted(ELEMENTS, key=len, reverse=True))
FORMULA_CHUNK_RE = re.compile(rf"(?:{_ELEMENT}|[A-Z]|\d+(?:\.\d+)?|[α-ωΑ-Ω]|[@/=·+−()\[\]{{}}’′,:;.*])+")
END_OF_SUB = r"(?:(?<=</sub>)|(?<=</sup>)|(?<=</sub></i>)|(?<=</sup></i>))"


def _before_sub(m):
    """Space before <sub>/<sup>: a stray gap ("CsPbBr <sub>3") unless after a word ("by <sup>1</sup>")."""
    word = re.sub(r"<[^>]+>", "", m.group(1))
    return m.group(1) + (" " if word.lower() in FUNCTION_WORDS else "")


def _after_sub(m):
    """Line break after </sub>: join if the next chunk continues the formula ("Ni<sub>3</sub>P@C")."""
    chunk = m.group(1)
    if FORMULA_CHUNK_RE.fullmatch(chunk) and chunk.lower() not in FUNCTION_WORDS \
            and re.search(r"[A-Za-z0-9α-ωΑ-Ω]", chunk):              # not a bare "=" ("E<sup>(2)</sup> = 20")
        return chunk
    return " " + chunk


_GAP_FIXES = [
    (re.compile(r"(\S*)[ \n]+(?=(?:<i>)?<su[bp]>)"), _before_sub),  # "CsPbBr <sub>3"  -> "CsPbBr<sub>3"
    (re.compile(r"(<(?:sub|sup|i)>)[ \n]+"), r"\1"),                # "<i> N"          -> "<i>N"
    (re.compile(r"[ \n]+(</(?:sub|sup|i)>)"), r"\1"),               # "N </i>"         -> "N</i>"
    (re.compile(r"(?<=</i>)[ \n]+(?=[-‐‑)\],.;:/′])"), ""),         # "<i>N</i> -Alkyl" -> "<i>N</i>-Alkyl"
    (re.compile(r"(?<=[-‐‑(\[/′‍])[ \n]+(?=<i>)"), ""),        # "[2,1- <i>a</i>" -> "[2,1-<i>a</i>"
    (re.compile(r"(?<=[,\d])\n(?=<i>[^<]{1,3}</i>)"), ""),          # "2\n<i>H</i>", "α,\n<i>α</i>"
    (re.compile(r"(?<=[A-Z])\n(?=<i>[xyznδ]</i>)"), ""),            # "TiO\n<i>x</i>" -> "TiO<i>x</i>"
    (re.compile(r"(?<=</i>)\n(?=[^\s(\[<]{1,3}[\])])"), ""),         # "[<i>a</i>\nn]Daisy" (short chunk only)
    (re.compile(END_OF_SUB + r"[ \n]+(?=[-‐‑)\]}/,;:]|–\S)"), ""),  # "<sup>2+</sup>\n/Co", "Csp<sup>3</sup> –Csp"
    (re.compile(END_OF_SUB + r"\n([^\s<‐‑–-]+)"), _after_sub),       # "<sub>3</sub>\nP@C", "<sub>2</sub>\ninto"
]


def escape_title_text(text: str) -> str:
    """Plain text -> safe title text: < > escaped, & only where it would read as an entity."""
    text = re.sub(r"&(?=#?\w+;)", "&amp;", text)                   # a literal "&lt;" in text stays text
    return text.replace("<", "&lt;").replace(">", "&gt;")


def clean_title(raw: str) -> str:
    """RSS or Crossref title -> stored title: text with only <sub>, <sup>, <i> kept."""
    return _clean_markup(raw)


def clean_abstract_html(raw: str) -> str:
    """RSS / Crossref / Springer abstract (HTML or JATS) -> plain text, without the gaps the old
    tag-stripper left: "CO<sub>2</sub> into" -> "CO2 into", "2<i>H</i>-azirine" -> "2H-azirine".
    Same rules as titles; then the kept tags are dropped (abstracts are stored as plain text)."""
    return plain_title(_clean_markup(raw, abstract=True))


def _clean_markup(raw: str, abstract: bool = False) -> str:
    """Shared by titles and abstracts. Abstract mode: every other tag (<p>, <div>, <br>, <img> ...)
    becomes a space, as in the old stripper, and a blank line is a real break, not formatting."""
    raw = BOLD_DIGITS_RE.sub(r"\1", DROP_ELEMENT_RE.sub(" ", raw or ""))
    out, stack, pos = [], [], 0

    def text(chunk):
        chunk = html.unescape(chunk)
        if abstract:
            chunk = re.sub(r"\n\s*\n", " ", chunk)                  # paragraph break -> real space
        chunk = re.sub(r"\s*\n\s*", "\n", chunk)                   # formatting whitespace -> "\n"
        chunk = re.sub(r"[^\S\n]+", " ", chunk)                    # real whitespace -> " "
        out.append(escape_title_text(chunk))

    for m in ANY_TAG_RE.finditer(raw):
        text(raw[pos:m.start()])
        pos = m.end()
        tag = TITLE_TAGS.get(m.group(2).lower())
        if not tag:
            if abstract:
                out.append(" ")                                    # <p>, <div>, <br>: a word break
            continue                                               # dropped tag: its text stays
        if not m.group(1):
            stack.append(tag)
            out.append(f"<{tag}>")
        elif tag in stack:                                         # close it (and anything left open inside)
            while stack:
                t = stack.pop()
                out.append(f"</{t}>")
                if t == tag:
                    break
    text(raw[pos:])
    out.extend(f"</{t}>" for t in reversed(stack))                 # close anything left open

    title = "".join(out)
    title = re.sub(r"<(sub|sup|i)>([ \n]*)</\1>", r"\2", title)    # empty tags
    for pattern, repl in _GAP_FIXES:
        title = pattern.sub(repl, title)
    return re.sub(r"\s+", " ", title).strip()


def plain_title(title: str) -> str:
    """Stored title -> plain text (topic tagging, filters, duplicate checks)."""
    return html.unescape(re.sub(r"</?(?:sub|sup|i)>", "", title or ""))


KEPT_TAG_RE = re.compile(r"<(?:sub|sup|i)>")
_KEPT_SPLIT_RE = re.compile(r"(</?(?:sub|sup|i)>)")


def text_key(title):
    """Title text for 'same title?' checks: no tags, case, spaces or punctuation."""
    return re.sub(r"\W+", "", plain_title(title).lower())


def spaced_like(new, stored):
    """`new` (cleaned Crossref title) with the word spacing of `stored` (a tagless RSS title).
    Returns None when the two texts don't line up character by character."""
    items, gap = [], False                      # items: ["tag", "<sub>"] or ["ch", c, cleaner_space]
    for part in _KEPT_SPLIT_RE.split(new):
        if _KEPT_SPLIT_RE.fullmatch(part):
            items.append(["tag", part])
            continue
        for ch in html.unescape(part):
            if ch.isspace():
                gap = True
            else:
                items.append(["ch", ch, gap])
                gap = False
    chars = [it for it in items if it[0] == "ch"]

    stored = plain_title(stored)
    j = 0                                       # line the characters up with the stored title
    for it in chars:
        space = False
        while j < len(stored) and stored[j].isspace():
            space, j = True, j + 1
        if j >= len(stored) or stored[j] != it[1]:
            return None
        it.append(space)                        # it[3]: the stored title has a space before this char
        j += 1
    if stored[j:].strip():
        return None

    # a tagged span with stored spaces on BOTH sides was a gap left by the old tag stripper:
    # use the cleaner's spacing at its two edges
    untrusted = set()                           # ids of chars whose space comes from the cleaner
    for k, it in enumerate(items):
        if it[0] != "tag" or it[1].startswith("</"):
            continue
        close, depth, first, after = "</" + it[1][1:], 0, None, None
        for n in range(k, len(items)):
            m = items[n]
            if m[0] == "ch":
                first = first or m
            elif m[1] == it[1]:
                depth += 1
            elif m[1] == close:
                depth -= 1
                if depth == 0:
                    after = next((x for x in items[n + 1:] if x[0] == "ch"), None)
                    break
        if first and (first[3] or first is chars[0]) and (after is None or after[3]):
            untrusted.update(id(x) for x in (first, after) if x)

    out, tags = [], []
    for it in items:
        if it[0] == "tag":
            tags.append(it[1])
            continue
        space = it[2] if id(it) in untrusted else it[3]
        if out and space:                       # the space goes outside the tags between two chars
            closing = [t for t in tags if t.startswith("</")]
            out += closing + [" "] + [t for t in tags if not t.startswith("</")]
        else:
            out += tags
        tags = []
        out.append(escape_title_text(it[1]))
    return "".join(out + tags)


def upgrade_title(stored: str, crossref: str):
    """Formatted title for an article stored WITHOUT tags (e.g. from ACS RSS), or None.

    `crossref` is a cleaned Crossref title. It replaces `stored` only when it adds <sub>/<sup>/<i>
    and is the same text (text_key); the spacing comes from `stored` where it lines up (spaced_like).
    Same rules as scripts/refresh_titles.py."""
    if KEPT_TAG_RE.search(stored) or not KEPT_TAG_RE.search(crossref) or text_key(crossref) != text_key(stored):
        return None
    new = spaced_like(crossref, stored) or crossref
    return new if new != stored else None


def entry_html(entry) -> str:
    """All HTML-ish text the feed gave us for this entry."""
    parts = [entry.get("summary", "")]
    for c in entry.get("content", []) or []:
        parts.append(c.get("value", ""))
    return " ".join(parts)


def find_image(entry, base_url: str) -> str:
    """Graphical-abstract URL from the feed, checked in order of reliability."""
    # a) <media:content> / <media:thumbnail>
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key, []) or []:
            if m.get("url"):
                return urljoin(base_url, m["url"])
    # b) <enclosure type="image/...">
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return urljoin(base_url, enc["href"])
    # c) <img src="..."> inside the description HTML (ACS / RSC style)
    m = IMG_RE.search(entry_html(entry))
    if m:
        return urljoin(base_url, html.unescape(m.group(1)))
    return ""


NATURE_LINK_RE = re.compile(r"nature\.com/articles/([^?#/\s]+)", re.IGNORECASE)


def find_doi(entry) -> str:
    """DOI from dedicated fields first, then from the link or text."""
    m = NATURE_LINK_RE.search(str(entry.get("link", "")))
    if m:  # nature.com/articles/s41586-026-01234-5  ->  10.1038/s41586-026-01234-5
        return "10.1038/" + m.group(1)
    for key in ("prism_doi", "dc_identifier", "id", "link"):
        m = DOI_RE.search(str(entry.get(key, "")))
        if m:
            return m.group(0).rstrip(".")
    m = DOI_RE.search(entry_html(entry))
    return m.group(0).rstrip(".") if m else ""


def find_authors(entry) -> str:
    if entry.get("authors"):
        names = [a.get("name", "") for a in entry["authors"] if a.get("name")]
        if names:
            return "; ".join(names)
    return entry.get("author", "") or entry.get("dc_creator", "")


def find_date(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return time.strftime("%Y-%m-%d", t)
    return entry.get("prism_publicationdate", "") or entry.get("dc_date", "")


def crossref_fill(article: dict, session: requests.Session) -> None:
    """Fill missing authors/date from Crossref (metadata only)."""
    if not article["doi"] or (article["authors"] and article["date"] and len(article["abstract"]) > 100):
        return
    params = {}
    if os.environ.get("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]
    try:
        r = session.get(f"https://api.crossref.org/works/{article['doi']}",
                        params=params, timeout=20)
        if r.status_code != 200:
            return
        msg = r.json()["message"]
        if not article["authors"]:
            article["authors"] = "; ".join(
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in msg.get("author", [])
            )
        if not article["date"]:
            parts = (msg.get("published-online") or msg.get("issued") or {}).get("date-parts", [[]])[0]
            article["date"] = "-".join(f"{p:02d}" for p in parts)
        if len(article["abstract"]) <= 100 and msg.get("abstract"):
            article["abstract"] = clean_abstract_html(msg["abstract"])
            article["topics"] = tag_topics(article['title'], article['abstract'])
        article["source_note"] += " +crossref"
    except (requests.RequestException, ValueError, KeyError):
        pass
    time.sleep(0.2)  # be polite


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def fetch_crossref(name, publisher, crossref_filter, session, days=7, versions=False):
    """Recent works from Crossref (no images). crossref_filter e.g. 'issn:2041-6539'."""
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    params = {"filter": f"{crossref_filter},from-created-date:{since}",
              "sort": "created", "order": "desc", "rows": 200, "cursor": "*"}
    if os.environ.get("CROSSREF_MAILTO"):
        params["mailto"] = os.environ["CROSSREF_MAILTO"]
    items = []
    try:
        for _ in range(10):                       # up to 2,000 works
            r = session.get("https://api.crossref.org/works", params=params, timeout=60,
                            headers={"Accept": "application/json"})
            r.raise_for_status()
            msg = r.json()["message"]
            items.extend(msg["items"])
            if len(msg["items"]) < params["rows"] or not msg.get("next-cursor"):
                break
            params["cursor"] = msg["next-cursor"]
            time.sleep(0.5)
    except (requests.RequestException, ValueError, KeyError) as e:
        if not items:
            return None, f"FAILED to fetch from Crossref: {e}", []
    if not items:
        return None, f"Crossref returned no items for the last {days} days", []

    if versions:   # preprints: each version (v1, v2 ...) has its own DOI - keep the newest
        latest = {}
        for it in items:
            doi = it.get("DOI", "")
            m = re.match(r"(.+?)[-/]v(\d+)$", doi)   # both ...-v2 and .../v2 styles
            base, ver = (m.group(1), int(m.group(2))) if m else (doi, 1)
            if base not in latest or ver > latest[base][0]:
                latest[base] = (ver, it)
        items = [v[1] for v in latest.values()]

    articles, titles, skipped = [], set(), 0
    for it in items:
        title = clean_title(" ".join(it.get("title", [])))
        key = re.sub(r"\W+", "", plain_title(title).lower())
        if not title or key in titles:            # same work under two DOIs
            continue
        titles.add(key)
        if NOT_A_PAPER.search(plain_title(title)):   # covers, contents lists, corrections
            skipped += 1
            continue
        abstract = clean_abstract_html(it.get("abstract", ""))
        parts = (it.get("published-online") or it.get("posted") or it.get("published")
                 or it.get("created") or {}).get("date-parts", [[]])[0]
        articles.append({
            "journal": name, "publisher": publisher, "title": title,
            "authors": "; ".join(f"{x.get('given', '')} {x.get('family', '')}".strip()
                                 for x in it.get("author", [])),
            "date": "-".join(f"{p:02d}" for p in parts),
            "doi": it.get("DOI", ""),
            "link": f"https://doi.org/{it.get('DOI', '')}",
            "image_url": "", "abstract": abstract,
            "topics": tag_topics(title, abstract),
            "source_note": "crossref",
        })
    notes = sorted({it.get("subtype", "") or it.get("type", "") for it in items} - {""})
    if skipped:
        notes.append(f"[skipped {skipped} non-research items]")
    return articles, None, notes


def acs_authors(people) -> str:
    """Crossref author list in the ACS RSS style: 'A, B, and C' / 'A and B'."""
    names = [(p.get("name") or f"{p.get('given', '')} {p.get('family', '')}").strip() for p in people]
    names = [n for n in names if n]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + ", and " + names[-1]


def fetch_crossref_by_issn(issns, session, days=7, mailto=""):
    """Journal articles published in the last `days` days, by ISSN (Crossref works API).

    Returns (articles, error, crossref_count). Articles have no abstract and no figure.
    The mailto goes only in the User-Agent header, so it never appears in a URL or error message.
    """
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - days * 86400))
    params = {"filter": ",".join(f"issn:{i}" for i in issns) + f",from-pub-date:{since},type:journal-article",
              "rows": 100, "cursor": "*"}
    headers = {"Accept": "application/json",
               "User-Agent": "ASAPChemHub/1.0" + (f" (mailto:{mailto})" if mailto else "")}
    items = []
    try:
        for _ in range(20):                       # up to 2,000 works
            for attempt in range(3):              # Crossref sometimes answers 429/5xx: back off, retry
                r = session.get("https://api.crossref.org/works", params=params, headers=headers, timeout=60)
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
                time.sleep(5 * (attempt + 1))
            r.raise_for_status()
            msg = r.json()["message"]
            items.extend(msg["items"])
            if len(msg["items"]) < params["rows"] or not msg.get("next-cursor"):
                break
            params["cursor"] = msg["next-cursor"]
            time.sleep(0.5)
    except (requests.RequestException, ValueError, KeyError) as e:
        if not items:
            code = getattr(getattr(e, "response", None), "status_code", None)
            return None, f"Crossref failed: {type(e).__name__}" + (f" {code}" if code else ""), 0

    articles = []
    for it in items:
        title = clean_title(" ".join(it.get("title", [])))
        if not title or not it.get("DOI") or NOT_A_PAPER.search(plain_title(title)):
            continue
        parts = []
        for key in ("published-online", "published-print", "issued", "created"):
            parts = (it.get(key) or {}).get("date-parts", [[]])[0] or []
            if len(parts) == 3:
                break
        articles.append({
            "title": title,
            "authors": acs_authors(it.get("author", [])),
            "date": "-".join(f"{p:02d}" for p in parts),
            "doi": it["DOI"],
            "link": f"https://doi.org/{it['DOI']}",
        })
    return articles, None, len(items)


def fetch_chemrxiv(name, publisher, url, session):
    """ChemRxiv blocks scripts on its own API, so preprints come from Crossref."""
    return fetch_crossref(name, publisher, "prefix:10.26434,type:posted-content", session, versions=True)


NON_RESEARCH = re.compile(r"\b(news|editorial|career|correction|retraction|erratum|"
                          r"podcast|letters?|books?|policy forum|in brief|outlook|obituary|"
                          r"working life|in other journals|this week)\b", re.IGNORECASE)


NOT_A_PAPER = re.compile(r"^\s*(author correction|publisher correction|correction|corrigendum|"
                         r"retraction|retracted|erratum|addendum|expression of concern|"
                         r"(inside |outside )?(front|back) cover|cover picture|cover feature|"
                         r"frontispiece|table of contents|contents list|masthead|issue information|"
                         r"issue editorial masthead|issue publication information)\b",
                         re.IGNORECASE)


def is_research(name, e) -> bool:
    """Drop corrections, covers etc. everywhere; keep only research from Nature/Science."""
    if NOT_A_PAPER.search(plain_title(clean_title(e.get("title", "")))):
        return False
    if name == "Nature":
        # Nature research papers have DOIs s41586-...; news and comment are d41586-...
        return "/articles/s41586" in str(e.get("link", ""))
    if name.startswith("Science"):
        if name == "Science (First Release)":
            return True            # First Release is research papers only
        labels = " ".join([str(e.get("dc_type", "")), str(e.get("prism_section", "")),
                           str(e.get("category", ""))] +
                          [t.get("term", "") for t in e.get("tags", []) or []]).strip()
        if labels:                 # the feed says what each item is
            return bool(re.search(r"research article|report", labels, re.IGNORECASE))
        # No labels: research papers have a DOI and a full abstract; news has no DOI,
        # and letters, editorials and summaries have only a few lines.
        return bool(find_doi(e)) and len(strip_html(entry_html(e))) >= 700
    return True


def fetch_journal(name, publisher, url, session):
    """Returns (articles, error, categories seen in the feed)."""
    if publisher == "ChemRxiv":
        return fetch_chemrxiv(name, publisher, url, session)
    if url.startswith("crossref:"):
        return fetch_crossref(name, publisher, url[len("crossref:"):] + ",type:journal-article", session,
                              days=30)   # the whole 30-day window, so nothing is missed
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
    except requests.RequestException as e:
        return None, f"FAILED to fetch feed: {e}", []

    feed = feedparser.parse(r.content)
    if not feed.entries:
        return None, "Feed downloaded but has no entries (check URL/format)", []

    articles, categories, skipped = [], set(), 0
    for e in feed.entries:
        # Research articles only for Nature and Science (no news, editorials, careers)
        if not is_research(name, e):
            skipped += 1
            continue
        for t in e.get("tags", []) or []:
            if t.get("term"):
                categories.add(t["term"])
        if e.get("dc_type"):
            categories.add(e["dc_type"])
        abstract = clean_abstract_html(entry_html(e))
        title = clean_title(e.get("title", ""))
        articles.append({
            "journal": name,
            "publisher": publisher,
            "title": title,
            "authors": find_authors(e),
            "date": find_date(e),
            "doi": find_doi(e),
            "link": e.get("link", ""),
            "image_url": find_image(e, url),
            "abstract": abstract,
            "topics": tag_topics(title, abstract),
            "source_note": "feed",
        })
    if name == "Science (latest issue)" and articles:
        # The TOC feed labels article types but has no images; the other Science
        # issue feed has images but no labels. Match the two by DOI.
        try:
            r2 = session.get("https://feeds.science.org/rss/science.xml", timeout=30)
            r2.raise_for_status()
            imgs = {find_doi(e2): find_image(e2, r2.url) for e2 in feedparser.parse(r2.content).entries}
            for a in articles:
                a["image_url"] = a["image_url"] or imgs.get(a["doi"], "")
        except requests.RequestException:
            pass
    if skipped:
        categories.add(f"[skipped {skipped} non-research items]")
    if not articles:
        return None, f"All {skipped} items were non-research", sorted(categories)
    return articles, None, sorted(categories)


def pct(n, d):
    return f"{100 * n / d:5.1f}%" if d else "   - "


def write_preview(articles, path="preview.html"):
    """Simple local page that hotlinks the publisher images."""
    cards = []
    for a in articles:
        img = (f'<img src="{html.escape(a["image_url"])}" loading="lazy">'
               if a["image_url"] else '<div class="noimg">No graphical abstract in feed</div>')
        tags = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in a["topics"])
        href = html.escape(a["link"] or (f"https://doi.org/{a['doi']}" if a["doi"] else "#"))
        cards.append(f"""
        <div class="card">
          <div class="fig">{img}</div>
          <div class="meta">
            <div class="j">{html.escape(a['journal'])} · {html.escape(a['date'])}</div>
            <a href="{href}" target="_blank">{a['title']}</a>
            <div class="au">{html.escape(a['authors'])}</div>
            <div>{tags}</div>
          </div>
        </div>""")
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>ASAP Chem Hub PoC</title>
<style>
 body{{font-family:system-ui,sans-serif;background:#f4f5f7;margin:0;padding:16px}}
 .card{{display:flex;gap:16px;background:#fff;border-radius:10px;padding:14px;margin:12px auto;max-width:1000px}}
 .fig{{flex:0 0 340px;display:flex;align-items:center;justify-content:center}}
 .fig img{{max-width:340px;max-height:200px}}
 .noimg{{color:#999;font-size:13px}}
 .j{{color:#666;font-size:13px}} .au{{color:#444;font-size:13px;margin:4px 0}}
 a{{font-weight:600;color:#1a3d7c;text-decoration:none}}
 .tag{{display:inline-block;background:#e8eefc;color:#1a3d7c;border-radius:10px;padding:2px 8px;margin:2px;font-size:12px}}
 @media(max-width:700px){{.card{{flex-direction:column}} .fig{{flex:none}}}}
</style></head><body><h2 style="max-width:1000px;margin:auto">ASAP Chem Hub – feed PoC ({len(articles)} articles)</h2>
{''.join(cards)}</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crossref", action="store_true",
                    help="fill missing authors/dates/abstracts from Crossref for ALL journals "
                         "(always on for Nature and Science)")
    ap.add_argument("--only", default="",
                    help='test only some publishers, e.g. --only "Springer Nature,AAAS,ChemRxiv"')
    args = ap.parse_args()
    wanted = {p.strip().lower() for p in args.only.split(",") if p.strip()}

    session = requests.Session()
    session.headers.update(HEADERS)

    all_articles, rows, category_report = [], [], []
    for name, publisher, url in JOURNALS:
        if wanted and publisher.lower() not in wanted:
            continue
        print(f"Fetching {name} ...", flush=True)
        articles, err, cats = fetch_journal(name, publisher, url, session)
        if cats and publisher in ("Springer Nature", "AAAS", "ChemRxiv"):
            category_report.append((name, cats))
        if err:
            rows.append((name, err))
            continue
        if args.crossref or publisher in ("Springer Nature", "AAAS"):
            for a in articles:
                crossref_fill(a, session)
        seen = {a["doi"] for a in all_articles if a["doi"]}
        articles = [a for a in articles if not a["doi"] or a["doi"] not in seen]
        all_articles.extend(articles)
        n = len(articles)
        rows.append((name, (
            f"{n:4d} articles | image {pct(sum(bool(a['image_url']) for a in articles), n)}"
            f" | abstract {pct(sum(len(a['abstract']) > 100 for a in articles), n)}"
            f" | DOI {pct(sum(bool(a['doi']) for a in articles), n)}"
            f" | authors {pct(sum(bool(a['authors']) for a in articles), n)}"
            f" | date {pct(sum(bool(a['date']) for a in articles), n)}"
        )))
        time.sleep(1)  # polite gap between requests

    # ---- Report -----------------------------------------------------------
    print("\n=== Feed coverage report ===")
    for name, line in rows:
        print(f"{name:26s} {line}")

    if category_report:
        print("\n=== Categories / fields seen (to design the chemistry filter) ===")
        for name, cats in category_report:
            print(f"{name}: {', '.join(cats[:25])}")

    if all_articles:
        total = len(all_articles)
        with_img = sum(bool(a["image_url"]) for a in all_articles)
        print(f"\nOVERALL: {total} articles, graphical abstract for {with_img} ({pct(with_img, total).strip()})")

        print("\n=== Topic matches (across ALL journals) ===")
        for topic in TOPICS:
            hits = [a for a in all_articles if topic in a["topics"]]
            print(f"\n{topic}: {len(hits)}")
            for a in hits[:10]:
                print(f"   [{a['journal']}] {a['title'][:110]}")

        with open("poc_results.csv", "w", newline="", encoding="utf-8") as f:
            fields = ["journal", "publisher", "date", "title", "authors", "doi",
                      "link", "image_url", "topics", "source_note", "abstract"]
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for a in all_articles:
                w.writerow({**a, "topics": "; ".join(a["topics"])})
        write_preview(all_articles)
        print("\nWrote poc_results.csv and preview.html (open preview.html in a browser)")
    else:
        print("\nNo articles retrieved - check feed URLs / network.")
        sys.exit(1)


if __name__ == "__main__":
    main()
