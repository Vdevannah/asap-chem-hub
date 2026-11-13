"""
SQL for the API, kept separate from the web layer so it is easy to read and test.
Every value from the user goes in as a query parameter (%s) - never pasted into SQL.
"""

import re

ARTICLE_FIELDS = """
    a.article_id, a.doi, a.title, a.authors, a.abstract, a.article_url,
    a.published_date, a.image_url, a.figure_status, a.is_open_access,
    j.journal_id, j.name AS journal, j.publisher
"""


def clean_search(q: str) -> str:
    """Keep letters, digits, spaces and - for MySQL full-text search."""
    return re.sub(r"[^\w\s\-]", " ", q or "").strip()


def build_article_filters(journal_ids=None, topic_ids=None, days=30, q=None):
    """WHERE clause + params shared by the list query and the count query."""
    where = ["a.published_date >= CURDATE() - INTERVAL %s DAY"]
    params = [days]
    if journal_ids:
        where.append(f"a.journal_id IN ({', '.join(['%s'] * len(journal_ids))})")
        params += list(journal_ids)
    if topic_ids:   # any of the chosen topics
        where.append(
            "EXISTS (SELECT 1 FROM article_topic_links l WHERE l.article_id = a.article_id "
            f"AND l.topic_id IN ({', '.join(['%s'] * len(topic_ids))}))")
        params += list(topic_ids)
    term = clean_search(q)
    if term:
        where.append("MATCH(a.title, a.authors, a.abstract) AGAINST (%s IN NATURAL LANGUAGE MODE)")
        params.append(term)
    return " AND ".join(where), params


def articles_query(journal_ids=None, topic_ids=None, days=30, q=None, limit=30, offset=0):
    where, params = build_article_filters(journal_ids, topic_ids, days, q)
    sql = f"""
        SELECT {ARTICLE_FIELDS}
          FROM articles a JOIN journals j ON j.journal_id = a.journal_id
         WHERE {where}
         ORDER BY a.published_date DESC, a.first_seen_at DESC, a.article_id DESC
         LIMIT %s OFFSET %s"""
    return sql, params + [limit, offset]


def count_query(journal_ids=None, topic_ids=None, days=30, q=None):
    where, params = build_article_filters(journal_ids, topic_ids, days, q)
    return f"SELECT COUNT(*) AS n FROM articles a WHERE {where}", params


def topics_for_articles_query(article_ids):
    return (f"""SELECT l.article_id, t.name FROM article_topic_links l
                  JOIN article_topics t ON t.topic_id = l.topic_id
                 WHERE l.article_id IN ({', '.join(['%s'] * len(article_ids))})
                 ORDER BY t.topic_id""", list(article_ids))


JOURNALS_SQL = """
    SELECT j.journal_id, j.name, j.publisher, j.picker_group, j.default_on,
           COUNT(a.article_id) AS article_count
      FROM journals j
      LEFT JOIN articles a ON a.journal_id = j.journal_id
     WHERE j.is_active
     GROUP BY j.journal_id
     ORDER BY FIELD(j.picker_group, 'General and flagship', 'Organic and synthesis',
                    'Medicinal and chemical biology', 'Catalysis and inorganic',
                    'Reviews', 'Preprints'), j.journal_id"""

TOPICS_SQL = """
    SELECT t.topic_id, t.name, COUNT(l.article_id) AS article_count
      FROM article_topics t
      LEFT JOIN article_topic_links l ON l.topic_id = t.topic_id
     GROUP BY t.topic_id
     ORDER BY t.topic_id"""

STATUS_SQL = """
    SELECT (SELECT MAX(finished_at) FROM ingestion_runs
             WHERE job = 'articles' AND status IN ('success', 'partial')) AS last_refreshed,
           (SELECT COUNT(*) FROM articles) AS total_articles,
           (SELECT COUNT(*) FROM articles WHERE figure_status = 'found') AS with_figure,
           (SELECT MAX(finished_at) FROM ingestion_runs
             WHERE job = 'patents' AND status IN ('success', 'partial')) AS patents_last_refreshed,
           (SELECT COUNT(*) FROM patents) AS total_patents"""


# ---------------------------------------------------------------------------
# New Patents (separate tables, same filter style as articles)
# ---------------------------------------------------------------------------
PATENT_FIELDS = """
    p.patent_id, p.publication_number, p.office, p.title, p.applicants, p.inventors,
    p.abstract, p.cpc_codes, p.family_id, p.patent_url, p.published_date
"""


def build_patent_filters(topic_ids=None, days=90, q=None):
    where = ["p.published_date >= CURDATE() - INTERVAL %s DAY"]
    params = [days]
    if topic_ids:
        where.append(
            "EXISTS (SELECT 1 FROM patent_topic_links l WHERE l.patent_id = p.patent_id "
            f"AND l.topic_id IN ({', '.join(['%s'] * len(topic_ids))}))")
        params += list(topic_ids)
    term = clean_search(q)
    if term:
        where.append("MATCH(p.title, p.applicants, p.abstract) AGAINST (%s IN NATURAL LANGUAGE MODE)")
        params.append(term)
    return " AND ".join(where), params


def patents_query(topic_ids=None, days=90, q=None, limit=30, offset=0):
    where, params = build_patent_filters(topic_ids, days, q)
    sql = f"""
        SELECT {PATENT_FIELDS} FROM patents p
         WHERE {where}
         ORDER BY p.published_date DESC, p.patent_id DESC
         LIMIT %s OFFSET %s"""
    return sql, params + [limit, offset]


def patent_count_query(topic_ids=None, days=90, q=None):
    where, params = build_patent_filters(topic_ids, days, q)
    return f"SELECT COUNT(*) AS n FROM patents p WHERE {where}", params


def topics_for_patents_query(patent_ids):
    return (f"""SELECT l.patent_id, t.name FROM patent_topic_links l
                  JOIN patent_topics t ON t.topic_id = l.topic_id
                 WHERE l.patent_id IN ({', '.join(['%s'] * len(patent_ids))})
                 ORDER BY t.topic_id""", list(patent_ids))


PATENT_TOPICS_SQL = """
    SELECT t.topic_id, t.name, COUNT(l.patent_id) AS patent_count
      FROM patent_topics t
      LEFT JOIN patent_topic_links l ON l.topic_id = t.topic_id
     GROUP BY t.topic_id
     ORDER BY t.topic_id"""


def journal_counts_query(topic_ids=None, days=30, q=None):
    """Articles per journal under the current filters (journal filter itself left out)."""
    where, params = build_article_filters(None, topic_ids, days, q)
    return (f"""SELECT a.journal_id, COUNT(*) AS n FROM articles a
                 WHERE {where} GROUP BY a.journal_id""", params)
