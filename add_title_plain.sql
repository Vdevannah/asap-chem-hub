-- Plain-text title for keyword search.
-- Titles keep chemical formatting (CO<sub>2</sub>, <i>N</i>-Alkyl, &lt; for a literal "<"), which
-- full-text search splits into "CO", "sub", "2" - so a search for "CO2" would miss them.
-- title_plain is the title with the three kept tags removed and the three entities decoded
-- (the same as poc_feeds.plain_title). It is a STORED generated column: MySQL fills it for all
-- existing rows here and keeps it in step on every INSERT and every UPDATE of title, so no code
-- has to remember it. Keyword search (api/queries.py) uses it instead of title.
--
-- Run once:  docker exec -i asap-chem-hub-db sh -c 'mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD"' < add_title_plain.sql
USE asap_chem_hub;

ALTER TABLE articles
  ADD COLUMN title_plain VARCHAR(1000)
      GENERATED ALWAYS AS (
        REPLACE(REPLACE(REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(title,
          '<sub>', ''), '</sub>', ''), '<sup>', ''), '</sup>', ''), '<i>', ''), '</i>', ''),
          '&lt;', '<'), '&gt;', '>'), '&amp;', '&')
      ) STORED AFTER title,
  DROP INDEX ft_articles,
  ADD FULLTEXT INDEX ft_articles (title_plain, authors, abstract);

SELECT COUNT(*) AS articles, SUM(title_plain <> title) AS titles_with_markup FROM articles;
