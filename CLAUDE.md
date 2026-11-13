# ASAP Chem Hub — project guide for Claude

ASAP Chem Hub ("ASAP articles and new patents in one place") is a free website for chemists.
Two independent sections:
- **ASAP Articles**: newest articles from 37 chemistry journals, figure-first (graphical abstracts), last 30 days.
- **New Patents**: new WO (PCT) patent applications from EPO, text only, last 90 days.
Both are filtered by research topic. Owner: Vijayarajan Devannah (GitHub: Vdevannah).

## Rules (always follow)
- Never read aloud, print, log or commit `.env`. API keys and DB passwords live only there.
- Official data sources only: publisher RSS, Crossref, Springer Nature APIs, EPO OPS. No scraping publisher
  pages, no fake browser User-Agent to get past blocks.
- Images are hotlinked from the publisher's URL, never downloaded or stored.
- No LLM or paid AI service inside the app.
- The patent section is for awareness only, not freedom-to-operate.
- Keep articles and patents independent: separate tables, jobs and endpoints; they share only topic names.
- Make small, focused changes. Explain what you changed. Don't commit or push unless asked.

## Layout
```
poc_feeds.py        journal list + feed fetching (RSS, Crossref for RSC/ChemRxiv)
topics.py           11 shared topic keyword rules (title match = 2, abstract = 1, per-topic thresholds)
springer.py         Springer Nature Meta + Open Access API (Nature abstracts, Figure 1)
epo.py              EPO OPS client: token, rate-limit pacing, 5 WO search streams
ingest.py           jobs: articles | figures | patents | cleanup | all
schema.sql          MySQL schema + seed data (journals, topics)
docker-compose.yml  MySQL 8.4 in Docker, host port 3307 (container asap-chem-hub-db)
api/                FastAPI: /health /status /journals /journal-counts /topics /articles /patent-topics /patents
web/                React + Vite site (src/components/*, src/styles.css, src/topics.js)
```

## Data model (MySQL `asap_chem_hub`)
- journals, articles (doi UNIQUE, figure_status found/pending/none), article_topics, article_topic_links
- patents (publication_number UNIQUE), patent_topics (14 = 11 shared + ADCs, Antibodies, OLED), patent_topic_links
- ingestion_runs (log of every job run)
- Retention: articles 30 days, patents 90 days. Daily patent lookback 28 days (EPO loads WO batches late).

## Running locally (three terminals)
1. API: `source .venv/bin/activate && uvicorn api.main:app --reload`  → http://127.0.0.1:8000/docs
2. Website: `cd web && npm run dev`  → http://localhost:5173
3. Other commands, e.g. `python ingest.py all` (refresh data), git.
Database: `docker compose up -d` (must be running).

## Website design (keep consistent)
- Page `#f3f2f7`, headings deep indigo `#23267a` in Jost capitals, reading text in Source Serif 4
  (fonts self-hosted via @fontsource).
- Topic families and colours (src/topics.js): orange = synthesis and catalysis, teal = medicinal and
  biological (incl. degraders, ADCs, antibodies), violet = materials and physical (incl. OLED),
  graphite = computational.
- Articles accent teal, Patents accent orange.
- Big hero on the first visit, slim band on later visits (localStorage "asap.heroSeen"; never animate its
  height while scrolling); sidebar filters (search, days, journals, grouped topic chips);
  journal chip row with live counts above the article grid; About page.
- Must stay responsive (phone layout folds filters behind a button), keyboard accessible, and respect
  prefers-reduced-motion.

## Roadmap
Done: phases 1–7 (feeds, topics, patents, database, ingestion, API, website).
Next: design polish, RSC graphical abstracts from RSC's own RSS (match by DOI), patent topic tuning,
then Phase 8: deploy to AWS (RDS MySQL, ECS Fargate scheduled ingestion via EventBridge, FastAPI on
Lambda + API Gateway, React on S3 + CloudFront, budget alerts).
