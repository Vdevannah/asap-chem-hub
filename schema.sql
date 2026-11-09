-- =====================================================================
-- ASAP Chem Hub - MySQL schema (v1)
-- ---------------------------------------------------------------------
-- Two independent sections that use the same topic names:
--   ASAP ARTICLES : journals, articles, article_topics, article_topic_links
--   NEW PATENTS   : patents, patent_topics, patent_topic_links
-- Plus one operations table: ingestion_runs (what each scheduled job did).
--
-- Run:  mysql -u root -p < schema.sql
-- =====================================================================

CREATE DATABASE IF NOT EXISTS asap_chem_hub
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;   -- utf8mb4: Greek letters, ‒, ₂ ...
USE asap_chem_hub;

-- =====================================================================
-- SECTION 1: ASAP ARTICLES
-- =====================================================================

-- One row per feed (37 at launch). Adding a journal = adding a row, no code change.
CREATE TABLE journals (
    journal_id       INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(100) NOT NULL UNIQUE,     -- 'J. Med. Chem.'
    publisher        VARCHAR(50)  NOT NULL,            -- 'ACS', 'Wiley', 'RSC', 'Springer Nature', 'AAAS', 'ChemRxiv'
    picker_group     VARCHAR(50)  NOT NULL,            -- group in the journal picker
    source_type      VARCHAR(30)  NOT NULL DEFAULT 'rss',  -- 'rss', 'crossref' or 'chemrxiv_crossref'
    feed_url         VARCHAR(500) NOT NULL,
    default_on       BOOLEAN      NOT NULL DEFAULT TRUE,   -- switched on for new visitors
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,   -- FALSE = stop fetching, keep history
    last_fetched_at  DATETIME     NULL,
    last_error       VARCHAR(500) NULL                    -- last fetch problem, for monitoring
);

CREATE TABLE articles (
    article_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    doi                VARCHAR(255) NOT NULL UNIQUE,   -- the dedupe key: each run inserts only new DOIs
    journal_id         INT          NOT NULL,
    title              VARCHAR(1000) NOT NULL,
    authors            TEXT,
    abstract           TEXT,                            -- cleaned (no HTML, no ^1,2 markers)
    article_url        VARCHAR(1000),
    published_date     DATE         NOT NULL,           -- drives the 30-day window
    -- figure handling --------------------------------------------------
    image_url          VARCHAR(1000) NULL,             -- publisher's own URL, never a copy
    image_source       VARCHAR(20)   NULL,             -- 'feed' or 'springer_oa'
    figure_status      ENUM('found', 'pending', 'none') NOT NULL DEFAULT 'none',
                       -- found   = image_url is set
                       -- pending = open-access Nature article, full text not indexed yet
                       -- none    = publisher gives no figure (placeholder card)
    figure_checked_at  DATETIME     NULL,              -- last re-check for 'pending'
    is_open_access     BOOLEAN      NULL,              -- from the Springer Meta API; NULL = unknown
    -- bookkeeping --------------------------------------------------------
    first_seen_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_articles_journal FOREIGN KEY (journal_id) REFERENCES journals(journal_id),
    INDEX idx_articles_date          (published_date),
    INDEX idx_articles_journal_date  (journal_id, published_date),   -- "these journals, newest first"
    INDEX idx_articles_figure        (figure_status, figure_checked_at),
    FULLTEXT INDEX ft_articles       (title, authors, abstract)       -- the keyword search box
);

CREATE TABLE article_topics (
    topic_id   INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL UNIQUE      -- same names as patent_topics
);

-- many-to-many: one article can have several topics
CREATE TABLE article_topic_links (
    article_id  BIGINT NOT NULL,
    topic_id    INT    NOT NULL,
    PRIMARY KEY (article_id, topic_id),
    INDEX idx_atl_topic (topic_id, article_id),     -- "all articles for topic X"
    CONSTRAINT fk_atl_article FOREIGN KEY (article_id) REFERENCES articles(article_id) ON DELETE CASCADE,
    CONSTRAINT fk_atl_topic   FOREIGN KEY (topic_id)   REFERENCES article_topics(topic_id)
);

-- =====================================================================
-- SECTION 2: NEW PATENTS (filled once EPO OPS access is approved)
-- =====================================================================

CREATE TABLE patents (
    patent_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    publication_number  VARCHAR(50)  NOT NULL UNIQUE,   -- 'WO2026123456A1' - the dedupe key
    office              CHAR(2)      NOT NULL,          -- 'WO', 'EP', 'US'
    title               VARCHAR(1000) NOT NULL,
    applicants          TEXT,                           -- 'Arvinas Operations, Inc.'
    inventors           TEXT,
    abstract            TEXT,
    cpc_codes           VARCHAR(1000),                  -- 'C07D401/14; A61P35/00'
    family_id           VARCHAR(50),                    -- groups WO/EP/US versions of one invention
    patent_url          VARCHAR(1000),                  -- Espacenet link
    published_date      DATE         NOT NULL,          -- drives the 90-day window
    first_seen_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_patents_date        (published_date),
    INDEX idx_patents_office_date (office, published_date),
    INDEX idx_patents_family      (family_id),
    FULLTEXT INDEX ft_patents     (title, applicants, abstract)
);

CREATE TABLE patent_topics (
    topic_id   INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE patent_topic_links (
    patent_id  BIGINT NOT NULL,
    topic_id   INT    NOT NULL,
    PRIMARY KEY (patent_id, topic_id),
    INDEX idx_ptl_topic (topic_id, patent_id),
    CONSTRAINT fk_ptl_patent FOREIGN KEY (patent_id) REFERENCES patents(patent_id) ON DELETE CASCADE,
    CONSTRAINT fk_ptl_topic  FOREIGN KEY (topic_id)  REFERENCES patent_topics(topic_id)
);

-- =====================================================================
-- OPERATIONS: one row per scheduled job run (monitoring + debugging)
-- =====================================================================

CREATE TABLE ingestion_runs (
    run_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    job            VARCHAR(30)  NOT NULL,            -- 'articles', 'figures', 'patents', 'cleanup'
    started_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at    DATETIME     NULL,
    status         ENUM('running', 'success', 'partial', 'failed') NOT NULL DEFAULT 'running',
    items_seen     INT          NOT NULL DEFAULT 0,
    items_new      INT          NOT NULL DEFAULT 0,
    items_deleted  INT          NOT NULL DEFAULT 0,
    notes          TEXT         NULL                  -- e.g. which feeds failed
);

-- =====================================================================
-- STARTER DATA
-- =====================================================================

INSERT INTO article_topics (name) VALUES
  ('Targeted protein degradation'), ('Inhibitors'), ('Medicinal chemistry'),
  ('Chemical biology'), ('Synthetic methods'), ('Catalysis'),
  ('Asymmetric synthesis and catalysis'),
  ('Total synthesis and natural products'), ('Materials and polymers'),
  ('Computational chemistry and AI'), ('Analytical and physical chemistry');

INSERT INTO patent_topics (name) SELECT name FROM article_topics;   -- same names, separate table

-- The 37 feeds tested in the proof of concept. ChemRxiv (~360 preprints a week)
-- starts switched off so it does not flood the default feed.
INSERT INTO journals (name, publisher, picker_group, source_type, feed_url, default_on) VALUES
('JACS', 'ACS', 'General and flagship', 'rss', 'https://pubs.acs.org/rss/jacsat/asap.xml', 1),
('ACS Central Science', 'ACS', 'General and flagship', 'rss', 'https://pubs.acs.org/rss/acscii/asap.xml', 1),
('JACS Au', 'ACS', 'General and flagship', 'rss', 'https://pubs.acs.org/rss/jaaucr/asap.xml', 1),
('Org. Lett.', 'ACS', 'Organic and synthesis', 'rss', 'https://pubs.acs.org/rss/orlef7/asap.xml', 1),
('J. Org. Chem.', 'ACS', 'Organic and synthesis', 'rss', 'https://pubs.acs.org/rss/joceah/asap.xml', 1),
('Org. Process Res. Dev.', 'ACS', 'Organic and synthesis', 'rss', 'https://pubs.acs.org/rss/oprdfk/asap.xml', 1),
('J. Med. Chem.', 'ACS', 'Medicinal and chemical biology', 'rss', 'https://pubs.acs.org/rss/jmcmar/asap.xml', 1),
('ACS Med. Chem. Lett.', 'ACS', 'Medicinal and chemical biology', 'rss', 'https://pubs.acs.org/rss/amclct/asap.xml', 1),
('J. Nat. Prod.', 'ACS', 'Medicinal and chemical biology', 'rss', 'https://pubs.acs.org/rss/jnprdf/asap.xml', 1),
('ACS Catalysis', 'ACS', 'Catalysis and inorganic', 'rss', 'https://pubs.acs.org/rss/accacs/asap.xml', 1),
('Organometallics', 'ACS', 'Catalysis and inorganic', 'rss', 'https://pubs.acs.org/rss/orgnd7/asap.xml', 1),
('Chem. Rev.', 'ACS', 'Reviews', 'rss', 'https://pubs.acs.org/rss/chreay/asap.xml', 1),
('Acc. Chem. Res.', 'ACS', 'Reviews', 'rss', 'https://pubs.acs.org/rss/achre4/asap.xml', 1),
('Angew. Chem. Int. Ed.', 'Wiley', 'General and flagship', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=15213773&type=etoc&feed=rss', 1),
('Chem. Eur. J.', 'Wiley', 'General and flagship', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=15213765&type=etoc&feed=rss', 1),
('Eur. J. Org. Chem.', 'Wiley', 'Organic and synthesis', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=10990690&type=etoc&feed=rss', 1),
('Adv. Synth. Catal.', 'Wiley', 'Organic and synthesis', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=16154169&type=etoc&feed=rss', 1),
('ChemMedChem', 'Wiley', 'Medicinal and chemical biology', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=18607187&type=etoc&feed=rss', 1),
('ChemBioChem', 'Wiley', 'Medicinal and chemical biology', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=14397633&type=etoc&feed=rss', 1),
('ChemCatChem', 'Wiley', 'Catalysis and inorganic', 'rss', 'https://onlinelibrary.wiley.com/action/showFeed?jc=18673899&type=etoc&feed=rss', 1),
('Chemical Science', 'RSC', 'General and flagship', 'crossref', 'crossref:issn:2041-6539', 1),
('Chem. Commun.', 'RSC', 'General and flagship', 'crossref', 'crossref:issn:1364-548X', 1),
('Org. Biomol. Chem.', 'RSC', 'Organic and synthesis', 'crossref', 'crossref:issn:1477-0539', 1),
('Org. Chem. Front.', 'RSC', 'Organic and synthesis', 'crossref', 'crossref:issn:2052-4129', 1),
('RSC Med. Chem.', 'RSC', 'Medicinal and chemical biology', 'crossref', 'crossref:issn:2632-8682', 1),
('RSC Chem. Biol.', 'RSC', 'Medicinal and chemical biology', 'crossref', 'crossref:issn:2633-0679', 1),
('Chem. Soc. Rev.', 'RSC', 'Reviews', 'crossref', 'crossref:issn:1460-4744', 1),
('Nat. Prod. Rep.', 'RSC', 'Reviews', 'crossref', 'crossref:issn:1460-4752', 1),
('Nature', 'Springer Nature', 'General and flagship', 'rss', 'https://www.nature.com/nature.rss', 1),
('Nat. Commun. (chemistry)', 'Springer Nature', 'General and flagship', 'rss', 'https://www.nature.com/subjects/chemistry/ncomms.rss', 1),
('Nature Chemistry', 'Springer Nature', 'General and flagship', 'rss', 'https://www.nature.com/nchem.rss', 1),
('Nature Synthesis', 'Springer Nature', 'Organic and synthesis', 'rss', 'https://www.nature.com/natsynth.rss', 1),
('Nature Catalysis', 'Springer Nature', 'Catalysis and inorganic', 'rss', 'https://www.nature.com/natcatal.rss', 1),
('Nature Reviews Chemistry', 'Springer Nature', 'Reviews', 'rss', 'https://www.nature.com/natrevchem.rss', 1),
('Science (First Release)', 'AAAS', 'General and flagship', 'rss', 'https://feeds.science.org/rss/science-aop.xml', 1),
('Science (latest issue)', 'AAAS', 'General and flagship', 'rss', 'https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science', 1),
('ChemRxiv', 'ChemRxiv', 'Preprints', 'chemrxiv_crossref', 'https://api.crossref.org/works', 0);

-- =====================================================================
-- RETENTION (run by the daily cleanup job)
-- =====================================================================
-- DELETE FROM articles WHERE published_date < CURDATE() - INTERVAL 30 DAY;
-- DELETE FROM patents  WHERE published_date < CURDATE() - INTERVAL 90 DAY;
-- (topic links are removed automatically by ON DELETE CASCADE)

-- =====================================================================
-- EXAMPLE QUERIES the API will use
-- =====================================================================
-- Newest articles in the user's journals, one topic, last 7 days:
-- SELECT a.*, j.name AS journal
--   FROM articles a
--   JOIN journals j             ON j.journal_id = a.journal_id
--   JOIN article_topic_links l  ON l.article_id = a.article_id
--   JOIN article_topics t       ON t.topic_id   = l.topic_id
--  WHERE j.journal_id IN (1, 4, 7)
--    AND t.name = 'Targeted protein degradation'
--    AND a.published_date >= CURDATE() - INTERVAL 7 DAY
--  ORDER BY a.published_date DESC, a.first_seen_at DESC
--  LIMIT 50;
--
-- Keyword search:
-- SELECT * FROM articles
--  WHERE MATCH(title, authors, abstract) AGAINST ('Suzuki coupling' IN NATURAL LANGUAGE MODE)
--  LIMIT 50;
--
-- Open-access Nature articles whose figure should be re-checked today:
-- SELECT article_id, doi FROM articles
--  WHERE figure_status = 'pending'
--    AND first_seen_at >= NOW() - INTERVAL 14 DAY
--    AND (figure_checked_at IS NULL OR figure_checked_at < NOW() - INTERVAL 1 DAY);
