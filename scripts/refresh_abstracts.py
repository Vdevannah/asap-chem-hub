"""
One-time: remove the gaps the old tag-stripper left in stored abstracts ("CO 2", "LiCoO 2",
"2 H -azirine", "N -ylide"), for articles published in the last 30 days.

Each abstract is fixed from the best source available, and only its SPACING may change: a new
version is used only if it is the same text as the stored one once all whitespace is removed.
  1. markup     the raw abstract from Crossref (by DOI) or from a current RSS feed, cleaned with
                poc_feeds.clean_abstract_html - the same cleaner ingestion now uses
  2. text rules when no raw markup is available, only gaps that are safe to spot in plain text:
                - formulas: element symbols + space + number, e.g. "CO 2", "LiCoO 2", "H 2 O",
                  "Na 4 Fe 3 (PO 4 ) 2", "AuCl 4 −" - only when the formula has two or more
                  element symbols (CO, LiCoO) or is a chain (H 2 O, Na 4 Fe 3); never before a unit
                  ("NaOH 2 equiv", "2 h"); never for an all-caps acronym with one number ("NHC 2")
                - italic prefixes: "N -ylide" -> "N-ylide", "2 H -azirine" -> "2H-azirine",
                  "(3 H )" -> "(3H)"
Nothing else is guessed. Topics are not re-tagged (the text is the same).

Usage (from the project folder)
    python scripts/refresh_abstracts.py            # dry run: report + CSV, changes nothing
    python scripts/refresh_abstracts.py --apply    # write the updates
"""

import argparse
import csv
import difflib
import os
import re
import sys
import time
from collections import Counter

import feedparser
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import poc_feeds as feeds                          # noqa: E402
from load_poc import clean_abstract, connect       # noqa: E402  (also loads .env)

DAYS = 30
BATCH = 40
PAUSE = 1.0
PREVIEW = "logs/refresh_abstracts_preview.csv"

# --- safe plain-text rules ---------------------------------------------------------------
_GROUPS = {"Me", "Et", "Bu", "Ph", "Ts", "Bz", "Bn", "Cy", "Cp", "Tf", "Ms", "Py"}
_EL = "|".join(sorted((e for e in feeds.ELEMENTS if e not in _GROUPS), key=len, reverse=True))
FORMULA = re.compile(rf"([(\[]?)((?:{_EL})+)([)\]]?)")             # (PO  LiCoO  CO  Fe
NUMBER = re.compile(r"(\d+(?:\.\d+)?)([+−]?)([)\],.;:]*)")         # 2  0.85  3+  4)  2.
CHARGE = re.compile(r"(\d?[+−]|−)([)\],.;:]*)")                    # −  2−  3+
NOT_FORMULAS = {"In", "As", "At", "No", "Be", "He", "I", "Am", "If", "Ho", "Hf"}
UNITS = {"h", "min", "s", "d", "days", "hours", "equiv", "equiv.", "eq", "eq.", "mol", "mmol", "μmol", "M", "mM",
         "μM", "µM", "nM", "pM", "%", "mol%", "wt%", "g", "mg", "kg", "mL", "L", "μL", "K", "°C", "bar", "atm", "V",
         "mV", "eV", "kDa", "Da", "nm", "μm", "µm", "mm", "cm", "Hz", "kHz", "MHz", "ppm", "cycles", "times", "fold",
         "W", "mW", "A", "mA", "Å", "GPa", "MPa", "kPa", "Pa", "ns", "ps", "fs", "ms", "μs", "J", "kJ", "kcal"}
BLOCK_BEFORE = {"Figure", "Fig.", "Table", "Scheme", "entry", "Entry", "compound", "complex", "ligand", "pH",
                "step", "type", "Type", "Section", "run", "Eq.", "eq.", "Equation", "route", "Route"}


def _elements(fragment):
    return re.findall(rf"{_EL}", fragment)


def _formula(token):
    """Element-symbol fragment of a token ("(PO" -> "PO"), or None."""
    m = FORMULA.fullmatch(token)
    return m.group(2) if m and token not in NOT_FORMULAS else None


def _run(tok, i):
    """Longest formula run starting at tok[i]: F N (F N | ")" N)* [F]. Returns (end, fragments)."""
    if not _formula(tok[i]):
        return None
    frags, j, end = [_formula(tok[i])], i + 1, None
    while j < len(tok):
        n = NUMBER.fullmatch(tok[j])
        if not n:
            break
        j += 1
        end = j                                        # a run may end after any number
        if n.group(3):                                 # "4)" "2," "2." : punctuation ends the formula
            break
        if j < len(tok) and _formula(tok[j]):          # ... Fe 3 (PO ...  or a closing "H 2 O"
            frags.append(_formula(tok[j]))
            j += 1
            end = j
        elif j + 1 < len(tok) and tok[j] == ")" and NUMBER.fullmatch(tok[j + 1]):
            j += 1                                     # ... (PO 4 ) 2
        else:
            break
    if end is None:
        return None
    return end, frags[: sum(1 for t in tok[i:end] if _formula(t))]


def formula_gaps(text):
    """Join "CO 2" -> "CO2", "Na 4 Fe 3 (PO 4 ) 2" -> "Na4Fe3(PO4)2"; see the module docstring."""
    tok = text.split(" ")
    out, i = [], 0
    while i < len(tok):
        run = _run(tok, i) if not (i and tok[i - 1] in BLOCK_BEFORE) else None
        if run:
            end, frags = run
            nxt = tok[end] if end < len(tok) else ""
            nums = sum(1 for t in tok[i:end] if NUMBER.fullmatch(t))
            multi = any(len(_elements(x)) >= 2 for x in frags)
            chain = nums >= 2 or len(frags) >= 2
            charged = any(NUMBER.fullmatch(t) and NUMBER.fullmatch(t).group(2) for t in tok[i:end])  # Fe 3+
            acronym = len(frags) == 1 and nums == 1 and re.fullmatch(r"[A-Z]{3,}", frags[0])
            if (multi or chain or charged) and not acronym and nxt not in UNITS:
                joined = "".join(tok[i:end])
                if nxt and CHARGE.fullmatch(nxt):      # "AuCl 4 −" -> "AuCl4−"
                    joined, end = joined + nxt, end + 1
                elif len(nxt) > 1 and nxt[0] in "-‐" and nxt[1].isalpha():
                    joined, end = joined + nxt, end + 1    # "CO 2 -to-ethanol" -> "CO2-to-ethanol"
                out.append(joined)
                i = end
                continue
        out.append(tok[i])
        i += 1
    return " ".join(out)


ITALIC_RULES = [
    (re.compile(r"\((\d+) H \)"), r"(\1H)"),                       # "(3 H )-one" -> "(3H)-one"
    (re.compile(r"\b(\d+) H -(?=[A-Za-z])"), r"\1H-"),             # "2 H -azirine" -> "2H-azirine"
    (re.compile(r"(?<![\w-])([NOSPEZR]) -(?=[A-Za-z(])"), r"\1-"),  # "N -ylide" -> "N-ylide"
]


def text_rules(text):
    new = formula_gaps(text)
    for pattern, repl in ITALIC_RULES:
        new = pattern.sub(repl, new)
    return new


# --- helpers ------------------------------------------------------------------------------
CROSSREF_SOURCED = {"RSC", "ChemRxiv"}               # stored abstracts that came from Crossref


def nows(text):
    return re.sub(r"\s+", "", text or "")


def glues_words(old, new):
    """True if new removes a space between two lowercase words ("Bacillus paranthracis" ->
    "Bacillusparanthracis": a typo in a deposit); such a version is not used."""
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete" and old[i1:i2].isspace() and re.search(r"[a-z]{2}$", old[:i1]) \
                and re.match(r"[a-z]{2}", old[i2:]):
            return True
    return False


def snippets(old, new, width=35):
    """The changed parts of old -> new, with a few words around each."""
    out = []
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        a0, a1 = max(0, i1 - width), min(len(old), i2 + width)
        b0, b1 = max(0, j1 - width), min(len(new), j2 + width)
        out.append(("…" + old[a0:a1] + "…", "…" + new[b0:b1] + "…"))
    return out


RISKY_RE = re.compile(r"(\d)(?:\s?)(h|min|equiv|eq|mol|mmol|mg|mL|nm|K|°C|bar|V|eV|%)\b|"
                      r"\b(Figure|Fig\.|Table|Scheme|entry|compound|pH|step|type)\s?\d", re.IGNORECASE)


def risky(old, new):
    """Changes that touch a unit, a figure/table/entry number or pH, or glue two words together."""
    reasons = []
    for a, b in snippets(old, new, width=12):
        if RISKY_RE.search(b) and not RISKY_RE.search(a):
            reasons.append(f"number/unit: {a} -> {b}")
        if re.search(r"[a-z]{3,}[A-Z]?[a-z]{2,}", b.replace(" ", "")) and \
                len(re.findall(r"[A-Za-z]{4,}", b)) < len(re.findall(r"[A-Za-z]{4,}", a)):
            reasons.append(f"words joined: {a} -> {b}")
    return reasons


def crossref_abstracts(dois, session):
    params = {"filter": ",".join(f"doi:{d}" for d in dois), "select": "DOI,abstract", "rows": len(dois)}
    for attempt in range(3):
        r = session.get("https://api.crossref.org/works", params=params, timeout=60)
        if r.status_code not in (429, 500, 502, 503, 504):
            break
        time.sleep(10 * (attempt + 1))
    r.raise_for_status()
    return {it["DOI"].lower(): it["abstract"] for it in r.json()["message"]["items"] if it.get("abstract")}


def rss_abstracts(session):
    """{doi: raw description HTML} for every item in the current RSS feeds."""
    out = {}
    for name, publisher, url in feeds.JOURNALS:
        if url.startswith("crossref") or publisher == "ChemRxiv":
            continue
        try:
            r = session.get(url, timeout=30, headers=feeds.HEADERS)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f"  {name}: feed failed ({type(e).__name__})")
            continue
        for e in feedparser.parse(r.content).entries:
            doi = feeds.find_doi(e)
            if doi:
                out[doi.lower()] = feeds.entry_html(e)
        time.sleep(PAUSE)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the updates (default: dry run)")
    args = ap.parse_args()

    mailto = os.environ.get("CROSSREF_MAILTO", "").strip()
    session = requests.Session()
    session.headers.update({"Accept": "application/json",
                            "User-Agent": "ASAPChemHub/1.0" + (f" (mailto:{mailto})" if mailto else "")})

    db = connect()
    cur = db.cursor()
    cur.execute("""SELECT a.article_id, a.doi, a.abstract, j.publisher, j.name FROM articles a
                     JOIN journals j USING (journal_id)
                    WHERE a.published_date >= CURDATE() - INTERVAL %s DAY AND COALESCE(a.abstract, '') <> ''""",
                (DAYS,))
    rows = cur.fetchall()
    print(f"{len(rows)} abstracts in the last {DAYS} days")

    print("Fetching raw abstracts from Crossref ...")
    raw = {}
    for i in range(0, len(rows), BATCH):
        try:
            raw.update(crossref_abstracts([r[1] for r in rows[i:i + BATCH]], session))
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  batch {i // BATCH + 1}: Crossref failed ({type(e).__name__})")
        time.sleep(PAUSE)
    print(f"  {len(raw)} have an abstract in Crossref")
    print("Fetching current RSS feeds ...")
    rss = rss_abstracts(session)
    print(f"  {len(rss)} items in the feeds")

    outcome, by_pub, changes, flagged = Counter(), Counter(), [], []
    for article_id, doi, old, publisher, journal in rows:
        new, how = None, None
        sources = [("Crossref markup", raw.get(doi.lower())), ("RSS markup", rss.get(doi.lower()))]
        if publisher not in CROSSREF_SOURCED:          # stored from RSS: its own markup first
            sources.reverse()
        for source, markup in sources:
            if markup:
                candidate = clean_abstract(feeds.clean_abstract_html(markup))
                if nows(candidate) != nows(old):
                    outcome[f"{source}: text differs, not used"] += 1
                elif glues_words(old, candidate):
                    outcome[f"{source}: would glue two words, not used"] += 1
                else:
                    new, how = candidate, source
                    break
        if new is None:
            new, how = text_rules(old), "text rules"
        if new == old:
            outcome["unchanged"] += 1
            continue
        assert nows(new) == nows(old)                  # only spacing ever changes
        outcome[f"update ({how})"] += 1
        by_pub[publisher] += 1
        changes.append((article_id, doi, journal, how, old, new))
        reasons = risky(old, new)
        if reasons:
            flagged.append((journal, doi, how, reasons))

    print("\nOutcome:")
    for k, v in outcome.most_common():
        print(f"  {k:42s} {v:5d}")
    print("Updates by publisher: " + ", ".join(f"{p} {n}" for p, n in by_pub.most_common()))

    os.makedirs(os.path.dirname(PREVIEW), exist_ok=True)
    with open(PREVIEW, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["journal", "doi", "source", "before", "after"])
        for _, doi, journal, how, old, new in changes:
            for a, b in snippets(old, new):
                w.writerow([journal, doi, how, a, b])
    print(f"Every changed snippet: {PREVIEW}")
    print(f"\nFlagged for review ({len(flagged)}):")
    for journal, doi, how, reasons in flagged[:40]:
        for r in reasons[:3]:
            print(f"  [{journal}] {doi} ({how}): {r}")

    if not args.apply:
        print("\nDry run: nothing written. Run with --apply to update.")
        return
    updated = 0
    for article_id, _, _, _, old, new in changes:
        cur.execute("UPDATE articles SET abstract = %s WHERE article_id = %s AND abstract = %s",
                    (new, article_id, old))
        updated += cur.rowcount
    db.commit()
    print(f"\nUpdated {updated} abstracts.")


if __name__ == "__main__":
    sys.exit(main())
