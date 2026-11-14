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
- Palette "Mineral Sage & Pine". Every colour is a CSS variable in src/styles.css; no hard-coded colours
  in rules. Headings (`--heading`) in Jost capitals, reading text in Source Serif 4 (fonts self-hosted via
  @fontsource).
- Light (default, `:root`): page `#eef1ee`, surface `#fbfcfb`, ink `#1d2a26`, muted `#5a6863`,
  rule `#d8dfdb`, heading `#1f3a33`, lede `#3a4842`, divider `#b9c4be`, stripe `#e8ece9`,
  on-accent `#ffffff`.
- Dark (`<html data-theme="dark">`): page `#111815`, surface `#18211d`, ink `#e6ece8`, muted `#9aaaa3`,
  rule `#2a3530`, heading `#a8d5c4`, lede `#c4d0ca`, divider `#3e4b45`, stripe `#1d2722`,
  on-accent `#0f1512`.
- Topic families (src/topics.js), base / ink / soft:
  - amber = synthesis and catalysis: light `#c98a12 / #8f610a / #f7ecd3`, dark `#e8a93a / #f0bd62 / #3a2e14`
  - jade = medicinal and biological (incl. degraders, ADCs, antibodies): light `#1f8a70 / #16705a / #dcf0e9`,
    dark `#3cc39d / #6fd6b8 / #123a30`
  - amethyst = materials and physical (incl. OLED): light `#7a4fa8 / #634091 / #ece4f5`,
    dark `#a98bdc / #c0a8ea / #2d2442`
  - slate = computational: light `#5a6670 / #424c55 / #e6eaec`, dark `#9aa6ae / #b8c2c8 / #252d31`
  - Use base for rings, borders and rules; -ink for text; -soft for tinted backgrounds; -fill for filled
    backgrounds (selected segmented button and chips, NEW badge, primary buttons) with `--on-accent` text.
    -fill is the ink shade in light mode and the base shade in dark mode, to keep text contrast ≥ 4.5:1.
- Articles accent jade, Patents accent amber (`--accent`, `--accent-ring`, `--accent-soft`, `--accent-fill`;
  `.theme-patents` switches them to amber).
- Dark mode rules: `color-scheme` matches the theme; graphical-abstract tiles (`.figure`) stay on white
  (`--figure-bg`) with a 1px rule border so publisher images stay readable.
- Theme choice: Auto (follows the OS) / Light / Dark, saved in localStorage "asap.theme" (default "auto"),
  icon button at the right end of the top bar (src/components/ThemeToggle.jsx, src/theme.js). An inline
  script in web/index.html sets `data-theme` and `<meta name="theme-color">` before React loads (no flash);
  keep its page colours in step with `--page`.
- Split banner under the top bar, the same on every visit (src/components/Banner.jsx; no first-visit
  logic). Left: solid pine panel (`--banner-pine`: `#1f3a33` light, `#0f1714` dark) with "ASAP Chem Hub"
  (Jost caps) and the one-line tagline (no pills: the top bar has the tabs with counts). Right: web/public/banner.jpg (2100×679, < 300 KB) / banner-small.jpg (1100px, phones),
  alt="" (decorative), AI-generated (credit on the About page), with a soft fade from the panel into it.
  Text uses the light `--banner-*` colours in both themes (all ≥ 7:1 on either pine).
  Sizes (height / panel width / fade / `--banner-focus`): desktop 200px / 40% / 80px / "30% 88%";
  ≤ 960px 200px / 45% / 80px / "20% 80%"; ≤ 700px 140px / 50% / 24px / "29% 80%".
- Top bar: `--bar-h` 72px (60px at ≤ 600px); scroll-padding and the sticky sidebar's top/max-height derive
  from it, so change the height only there. Wordmark `--step-brand` 20px, tabs `--step-nav` 18px (16px on
  phones), counts 15px (13px on phones, hidden below 360px), 4px active underline, 40px theme button.
- Page column: max 1440px with a `--gutter` side padding. Full-bleed elements (sticky top bar, banner)
  span the window (`margin-inline: calc(50% - 50vw)`) and pad with `--edge-pad` so their content lines up
  with the column. The top bar background is opaque `--page` (nothing shows through when scrolled).
- Type scale (src/styles.css `:root`): `--step--3` 12px (footer small print), `--step--2` 13px (chip counts, card topic tags), `--step--1` 14px
  (meta lines, hints, family names, small UI), `--step-0` 15px (body, field labels, chips, authors,
  strip chips), `--step-ui` 16px (search box, sidebar day buttons, journals box), `--step-title` 18px
  (article and patent card titles: the same on both tabs), `--step-1`+ for headings. Counts inside any
  chip use `--step--2`. Matching roles match across tabs: meta 14, people line 15, abstract 15, tags 13.
  Set sizes through these variables, not hard-coded values. Sidebar column 310px.
- Sidebar scrollbar only (the page scrollbar stays the browser default): 6px, transparent track, thumb
  `--muted` at 25% (45% on the thumb), shown only while hovering or scrolling the column (fades 150ms via
  the registered `--sb-alpha`); `scrollbar-gutter: stable` keeps content clear of it. Firefox gets
  `scrollbar-width/color` inside `@supports (-moz-appearance: none)`, because Chrome ignores the
  `::-webkit-scrollbar` rules on an element that sets those.
- Graphical abstracts: list view figure column 360px (≥ 1200px), 300px (961–1199), 240px (601–960),
  full width on phones; the tile follows the image's shape (min 160 / max 260px, object-fit contain on
  white, 4px padding). Grid cards are min 340px wide. Clicking a figure opens it in a lightbox
  (src/components/Lightbox.jsx, native modal `<dialog>`: Esc / × / backdrop close, focus returns to the
  figure); the figure itself does not link to the article; the title and the lightbox's "Open article" do.
- Each tab starts with a centred `<h2 class="tab-heading">` ("ASAP Articles", "New Patents") in a
  `.tab-head`: Jost caps, 0.06em spacing, 1.5rem (1.2rem on phones), `--heading` colour, with the centred
  `.divider` ornament under it (120px line in `--divider`, small tick in `--muted`); 28px above, 20px
  below the line.
- Chip strips (journals, applicants) keep the selected chip in view by scrolling the row sideways only;
  never `scrollIntoView` there (it scrolls the whole page on load).
- Sidebar filters (search, days, journals, grouped topic chips); journal chip row with live counts above
  the article grid; About page.
- Must stay responsive (phone layout folds filters behind a button), keyboard accessible, and respect
  prefers-reduced-motion.

## Roadmap
Done: phases 1–7 (feeds, topics, patents, database, ingestion, API, website).
Next: design polish, RSC graphical abstracts from RSC's own RSS (match by DOI), patent topic tuning,
then Phase 8: deploy to AWS (RDS MySQL, ECS Fargate scheduled ingestion via EventBridge, FastAPI on
Lambda + API Gateway, React on S3 + CloudFront, budget alerts).
