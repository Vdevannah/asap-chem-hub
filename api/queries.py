"""
SQL for the API, kept separate from the web layer so it is easy to read and test.
Every value from the user goes in as a query parameter (%s) - never pasted into SQL.
"""

import re

ARTICLE_FIELDS = """
    a.article_id, a.doi, a.title, a.authors, a.abstract, a.article_url,
    a.published_date, a.image_url, a.figure_status, a.is_open_access,
    a.first_seen_at, j.journal_id, j.name AS journal, j.publisher
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


# How many rows first appeared after `since` (a naive UTC datetime). NULL since -> 0.
NEW_SINCE = "CAST(COALESCE(SUM({alias}.first_seen_at > %s), 0) AS SIGNED)"


def count_query(journal_ids=None, topic_ids=None, days=30, q=None, since=None):
    where, params = build_article_filters(journal_ids, topic_ids, days, q)
    return (f"SELECT COUNT(*) AS n, {NEW_SINCE.format(alias='a')} AS new_n FROM articles a WHERE {where}",
            [since] + params)


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
    p.abstract, p.cpc_codes, p.family_id, p.patent_url, p.published_date, p.first_seen_at
"""


def like_escape(text: str) -> str:
    """Make % and _ (and the escape character itself) match literally inside LIKE."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def clean_applicant(part: str) -> str:
    """'HOFFMANN LA ROCHE [CH] ' -> 'HOFFMANN LA ROCHE'"""
    return re.sub(r"\s+", " ", re.sub(r"\[[A-Za-z]{2}\]\s*$", "", part.strip())).strip()


def build_patent_filters(topic_ids=None, days=90, q=None, applicant=None):
    where = ["p.published_date >= CURDATE() - INTERVAL %s DAY"]
    params = [days]
    if applicant:   # one cleaned applicant name, matched anywhere in the applicants list
        where.append("p.applicants LIKE %s")
        params.append(f"%{like_escape(applicant)}%")
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


def patents_query(topic_ids=None, days=90, q=None, limit=30, offset=0, applicant=None):
    where, params = build_patent_filters(topic_ids, days, q, applicant)
    sql = f"""
        SELECT {PATENT_FIELDS} FROM patents p
         WHERE {where}
         ORDER BY p.published_date DESC, p.patent_id DESC
         LIMIT %s OFFSET %s"""
    return sql, params + [limit, offset]


def patent_count_query(topic_ids=None, days=90, q=None, since=None, applicant=None):
    where, params = build_patent_filters(topic_ids, days, q, applicant)
    return (f"SELECT COUNT(*) AS n, {NEW_SINCE.format(alias='p')} AS new_n FROM patents p WHERE {where}",
            [since] + params)


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


def journal_counts_query(topic_ids=None, days=30, q=None, since=None):
    """Articles (and new articles) per journal under the current filters (journal filter left out)."""
    where, params = build_article_filters(None, topic_ids, days, q)
    return (f"""SELECT a.journal_id, COUNT(*) AS n, {NEW_SINCE.format(alias='a')} AS new_n
                  FROM articles a
                 WHERE {where} GROUP BY a.journal_id""", [since] + params)


def topic_counts_query(journal_ids=None, days=30, q=None):
    """Articles per topic under the current filters (topic filter itself left out)."""
    where, params = build_article_filters(journal_ids, None, days, q)
    return (f"""SELECT l.topic_id, COUNT(*) AS n
                  FROM articles a JOIN article_topic_links l ON l.article_id = a.article_id
                 WHERE {where} GROUP BY l.topic_id""", params)


def patent_topic_counts_query(days=90, q=None):
    """Patents per topic under the current filters (topic filter itself left out)."""
    where, params = build_patent_filters(None, days, q)
    return (f"""SELECT l.topic_id, COUNT(*) AS n
                  FROM patents p JOIN patent_topic_links l ON l.patent_id = p.patent_id
                 WHERE {where} GROUP BY l.topic_id""", params)


def patent_applicants_query(topic_ids=None, days=90, q=None):
    """Raw applicant strings of the filtered patents; split and counted in Python."""
    where, params = build_patent_filters(topic_ids, days, q)
    return f"SELECT p.applicants FROM patents p WHERE {where} AND p.applicants IS NOT NULL", params


def top_applicants(rows, limit=12):
    """Count applicants across rows like 'NAME A [US]; NAME B [SE]', merging case differences.
    Each name counts once per patent. Shows the most common spelling of each name."""
    counts, spellings = {}, {}
    for (text,) in rows:
        seen = set()
        for part in (text or "").split(";"):
            name = clean_applicant(part)
            key = name.casefold()
            if not name or key in seen:
                continue
            seen.add(key)
            counts[key] = counts.get(key, 0) + 1
            spellings.setdefault(key, {})
            spellings[key][name] = spellings[key].get(name, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [{"name": max(spellings[k].items(), key=lambda s: s[1])[0], "n": n} for k, n in top]


def patent_weeks_query(topic_ids=None, days=90, q=None, applicant=None):
    """Patents per publication date (WO applications are published weekly), newest first."""
    where, params = build_patent_filters(topic_ids, days, q, applicant)
    return (f"""SELECT p.published_date, COUNT(*) AS n FROM patents p
                 WHERE {where} GROUP BY p.published_date ORDER BY p.published_date DESC""", params)
