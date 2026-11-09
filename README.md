# ASAP Chem Hub

**ASAP articles and new patents in one place.**

ASAP Chem Hub is a free website (in development) where chemists can scan the newest journal articles and newly published patents in one place, with graphical abstracts and research-topic filters.

> **Status:** proof of concept complete. Feed ingestion across 37 sources works; the database, API and website are next.

---

## Why

New chemistry is scattered across dozens of publisher websites, preprint servers and patent databases. Checking them all every day takes time. ASAP Chem Hub brings them together in one figure-first feed that researchers can filter by journal and topic.

## What it will do

| | ASAP Articles | New Patents |
| --- | --- | --- |
| Content | Latest ASAP / Early View articles and ChemRxiv preprints | Newly published chemistry and pharma patent applications |
| Sources | Publisher RSS feeds (ACS, Wiley, RSC, Springer Nature, AAAS), Crossref | EPO Open Patent Services |
| Each card | Graphical abstract, title, authors, journal, date, DOI link | Title, applicant, publication number, office, date, abstract, link |
| Filters | Journal picker, topic, date range, keyword search | Office, topic, applicant, date range, keyword search |

The two sections are independent but use the same topic names, such as *PROTAC / degraders*, *C–H functionalization* and *photoredox catalysis*.

## Proof-of-concept results

One run of `poc_feeds.py` across all sources (November 2026):

| Source | Feeds | Articles | Graphical abstract / figure |
| --- | --- | --- | --- |
| ACS | 13 | 42 | 98% |
| Wiley | 7 | 475 | 99% |
| RSC | 8 | 575 | 89% |
| Science (First Release + latest issue) | 2 | 24 | 50% (First Release 100%; issue papers not yet) |
| Nature journals | 6 | 86 | planned for open-access articles |
| ChemRxiv (via Crossref) | 1 | 362 | none (placeholder card) |

**1,564 articles in a single run; 93% have a figure wherever the publisher provides one.**

Other findings:
- *Science* and *Nature* are filtered to research articles only (news, editorials and letters are skipped).
- ChemRxiv preprints are de-duplicated so only the newest version of each appears.
- ACS feeds hold only the newest few articles, so the app must poll every few hours and store results — hence a database and scheduled ingestion jobs.

## Principles

- Free, official data sources only: publisher RSS feeds, Crossref, EPO OPS.
- No scraping of publisher pages and no disguising the client as a browser.
- Images are displayed from the publisher's own URL, never copied.
- Every card links back to the original article or patent.
- No LLM or paid AI service.
- The patent section is for awareness only, not for freedom-to-operate or patentability searches.

## Run the proof of concept

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python poc_feeds.py                                   # all 37 feeds
python poc_feeds.py --only "Springer Nature,AAAS"     # selected publishers
```

Outputs:
- a coverage report in the terminal (articles, % with figure, abstract, DOI, authors, date)
- `poc_results.csv` — one row per article
- `preview.html` — article cards with figures, open in a browser

Optional: `export CROSSREF_MAILTO=you@example.com` for faster Crossref responses.

## Roadmap

- [x] Feed proof of concept: 37 sources, figure coverage, topic tagging
- [ ] Springer Nature Open Access API for figures and abstracts of open-access Nature articles
- [ ] EPO OPS proof of concept for new patents
- [ ] MySQL schema and scheduled ingestion jobs
- [ ] FastAPI backend (`/articles`, `/patents`)
- [ ] React website with journal picker and topic filters
- [ ] Docker and public deployment

## Tech stack

Python · feedparser · requests · MySQL · FastAPI · React · Docker

## Author

**Vijayarajan Devannah** — PhD chemist (medicinal chemistry and OLED materials) working at the interface of chemistry and data engineering.
GitHub: [@Vdevannah](https://github.com/Vdevannah)

---

*Inspired by the idea of a single ASAP feed for chemists. ASAP Chem Hub is an independent project and is not affiliated with any publisher or with other literature-feed services.*
