# ASAP Chem Hub

**ASAP articles and new patents in one place.**

ASAP Chem Hub is a free website (in development) where chemists can scan the newest journal articles and newly published patents in one place, with graphical abstracts and research-topic filters.

> **Status:** backend complete. Ingestion and API work for both articles (37 journals) and patents (WO, EPO). Website (React) is next, then deployment to AWS.

---

## Why

New chemistry is scattered across dozens of publisher websites, preprint servers and patent databases. Checking them all every day takes time. ASAP Chem Hub brings them together in one figure-first feed that researchers can filter by journal and topic.

## What it does

| | ASAP Articles | New Patents |
| --- | --- | --- |
| Content | Latest ASAP / Early View articles from 37 journals, plus ChemRxiv preprints (off by default) | Newly published WO (PCT) patent applications in chemistry, pharma, biologics and OLED materials |
| Sources | Publisher RSS (ACS, Wiley, AAAS, Springer Nature), Crossref (RSC, ChemRxiv), Springer Nature APIs | EPO Open Patent Services (OPS) |
| Each card | Graphical abstract, title, authors, journal, date, abstract, DOI link | Publication number, title, applicant, date, abstract, topics, Espacenet link |
| Filters | Journal picker, topic, 7 / 14 / 30 days, keyword search | Topic, up to 90 days, keyword search |
| Kept for | 30 days | 90 days |

The two sections are independent (separate tables, separate jobs) but share topic names.

### Topics

**Shared by articles and patents (11):** Targeted protein degradation · Inhibitors · Medicinal chemistry · Chemical biology · Synthetic methods · Catalysis · Asymmetric synthesis and catalysis · Total synthesis and natural products · Materials and polymers · Computational chemistry and AI · Analytical and physical chemistry

**Patents only (3):** Antibody-drug conjugates · Antibodies · OLED materials and devices

Article topics and the shared patent topics are tagged by keyword rules on title and abstract (`topics.py`). The patent-only topics come from dedicated EPO searches by CPC class.

## How it works

```
Publisher RSS / Crossref / Springer APIs ─┐
                                          ├─► ingest.py (scheduled) ─► MySQL ─► FastAPI ─► React website
EPO Open Patent Services ─────────────────┘
```

### Ingestion jobs (`ingest.py`)

| Job | What it does | Schedule |
| --- | --- | --- |
| `articles` | Fetches every active journal, adds only new DOIs, fills gaps from Crossref / Springer, tags topics, warns on stale feeds | every 4 hours |
| `figures` | Re-checks open-access Nature articles for Figure 1 (Springer full text arrives days late), gives up after 14 days | daily |
| `patents` | Runs five EPO searches over the last 28 days, adds only new publication numbers, tags topics | daily |
| `cleanup` | Deletes articles older than 30 days and patents older than 90 | daily |

Each run is logged in the `ingestion_runs` table. A failing feed is recorded and the others carry on.

### Patent searches (WO only)

| Search | EPO query |
| --- | --- |
| General chemistry | CPC C07, A61K, A61P (topics from keyword rules) |
| Antibody-drug conjugates | CPC A61K47/68 and subgroups |
| Antibodies | CPC C07K16 and subgroups |
| Targeted protein degradation | drug CPC classes + title/abstract terms (degrader, PROTAC, heterobifunctional, cereblon, molecular glue) |
| OLED materials and devices | CPC H10K50, H10K85, C09K11/06 and subgroups |

EPO loads WO batches and their classifications several days late, so the daily job looks back 28 days and skips patents already stored.

### API (`api/`)

| Endpoint | Returns |
| --- | --- |
| `GET /health` | API is up |
| `GET /status` | Last refresh times, article and patent counts |
| `GET /journals` | Journals for the picker, grouped, with defaults |
| `GET /topics` | Article topics with counts |
| `GET /articles` | Article feed — filters: `journals`, `topics`, `days` (≤30), `q`; paging |
| `GET /patent-topics` | Patent topics with counts |
| `GET /patents` | Patent feed — filters: `topics`, `days` (≤90), `q`; paging |

Interactive docs at `http://127.0.0.1:8000/docs`.

## Results so far

**Articles** (first full run, November 2026): 1,564 articles from 37 feeds; 93% have a graphical abstract wherever the publisher provides one. Science and Nature are filtered to research articles; ChemRxiv versions are de-duplicated.

**Patents** (90-day backfill, August–November 2026): 5,841 WO patents, 100% with title, applicant, abstract and CPC codes. Roughly 275 ADC, 780 antibody, 90 degrader and 295 OLED patents.

## Run it locally

Requirements: Python 3.11+, Docker Desktop.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file (never committed):

```
DB_HOST=127.0.0.1
DB_PORT=3307
DB_NAME=asap_chem_hub
DB_USER=...
DB_PASSWORD=...
DB_ROOT_PASSWORD=...
SPRINGER_META_KEY=...      # Springer Nature Meta API
SPRINGER_OA_KEY=...        # Springer Nature Open Access API
EPO_KEY=...                # EPO OPS consumer key
EPO_SECRET=...             # EPO OPS consumer secret
```

Start the database (the schema is created automatically on first start):

```bash
docker compose up -d
```

Fill it and start the API:

```bash
python ingest.py articles
python ingest.py figures
python ingest.py patents --days 90     # first run only (~30 min, EPO rate limits); daily runs use 28 days
python ingest.py cleanup

uvicorn api.main:app --reload
```

### Project files

| File | Purpose |
| --- | --- |
| `poc_feeds.py` | Journal list and feed fetching (RSS, Crossref, ChemRxiv) |
| `topics.py` | Topic keyword rules and thresholds |
| `springer.py` | Springer Nature Meta and Open Access API helpers |
| `epo.py` | EPO OPS client: token, rate-limit pacing, the five patent searches |
| `ingest.py` | Scheduled ingestion jobs |
| `schema.sql` | Database schema and seed data (journals, topics) |
| `docker-compose.yml` | Local MySQL 8.4 |
| `api/` | FastAPI backend |
| `test_epo.py`, `test_springer.py`, `tune_topics.py` | Proof-of-concept and tuning scripts |
| `load_poc.py`, `retag_topics.py`, `*.sql` one-offs | Helpers and migrations |

## Principles

- Free, official data sources only: publisher RSS feeds, Crossref, Springer Nature APIs, EPO OPS.
- No scraping of publisher pages and no disguising the client as a browser.
- Images are displayed from the publisher's own URL, never copied.
- Every card links back to the original article or patent.
- API keys live only in `.env`, which is never committed.
- No LLM or paid AI service.
- The patent section is for awareness only, not for freedom-to-operate or patentability searches.

## Roadmap

- [x] Feed proof of concept: 37 sources, figure coverage
- [x] Topic tuning: 11 broad topics with per-topic thresholds
- [x] Springer Nature APIs for Nature abstracts and open-access figures
- [x] MySQL schema (Docker)
- [x] Scheduled ingestion jobs with run logging and stale-feed warnings
- [x] FastAPI backend for articles
- [x] EPO OPS patents: five WO searches, 14 topics, 90-day window, `/patents` API
- [ ] React website: ASAP Articles and New Patents tabs
- [ ] Deploy to AWS (RDS MySQL, ECS Fargate scheduled ingestion, Lambda + API Gateway, S3 + CloudFront)

## Tech stack

Python · feedparser · requests · MySQL 8.4 · Docker · FastAPI · React + Vite (next) · AWS (planned)

## Author

**Vijayarajan Devannah** — PhD chemist (medicinal chemistry and OLED materials) working at the interface of chemistry and data engineering.
GitHub: [@Vdevannah](https://github.com/Vdevannah)

---

*Inspired by the idea of a single ASAP feed for chemists. ASAP Chem Hub is an independent project and is not affiliated with any publisher, the EPO, or other literature-feed services.*
