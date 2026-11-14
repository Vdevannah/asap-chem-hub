"""
ASAP Chem Hub - backend API (Phase 6)
=====================================
Run locally (database container must be running):
    uvicorn api.main:app --reload
Then open http://127.0.0.1:8000/docs to try every endpoint in the browser.

Endpoints
    GET /health                 is the API up?
    GET /status                 last refresh time, article counts
    GET /journals               journals for the picker (grouped, with defaults)
    GET /topics                 topics with article counts
    GET /articles               the feed: filters for journals, topics, days, search; paging
    GET /journal-counts         articles per journal for the current days/topics/search
    GET /topic-counts           articles per topic for the current journals/days/search
    GET /patent-topics          patent topics with patent counts
    GET /patent-topic-counts    patents per topic for the current days/search
    GET /patent-applicants      top 12 applicants for the current topics/days/search
    GET /patent-weeks           patents per publication date for the current filters
    GET /patents                new WO patents: filters for topics, days (up to 90), search; paging
"""

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import queries
from .db import get_cursor

app = FastAPI(
    title="ASAP Chem Hub API",
    description="ASAP articles and new patents in one place.",
    version="0.1.0",
)

# The React dev server runs on another port, so the browser needs permission (CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Response shapes (also documented automatically at /docs)
# ---------------------------------------------------------------------------
class Journal(BaseModel):
    journal_id: int
    name: str
    publisher: str
    picker_group: str
    default_on: bool
    article_count: int


class Topic(BaseModel):
    topic_id: int
    name: str
    article_count: int


class Article(BaseModel):
    article_id: int
    doi: str
    title: str
    authors: Optional[str] = None
    abstract: Optional[str] = None
    article_url: Optional[str] = None
    published_date: date
    image_url: Optional[str] = None
    figure_status: str
    is_open_access: Optional[bool] = None
    journal_id: int
    journal: str
    publisher: str
    first_seen_at: datetime
    topics: List[str] = []


class ArticlePage(BaseModel):
    total: int
    new_count: int = 0
    limit: int
    offset: int
    items: List[Article]


class Status(BaseModel):
    last_refreshed: Optional[datetime] = None
    total_articles: int
    with_figure: int
    patents_last_refreshed: Optional[datetime] = None
    total_patents: int


class PatentTopic(BaseModel):
    topic_id: int
    name: str
    patent_count: int


class Patent(BaseModel):
    patent_id: int
    publication_number: str
    office: str
    title: str
    applicants: Optional[str] = None
    inventors: Optional[str] = None
    abstract: Optional[str] = None
    cpc_codes: Optional[str] = None
    family_id: Optional[str] = None
    patent_url: Optional[str] = None
    published_date: date
    first_seen_at: datetime
    topics: List[str] = []


class PatentPage(BaseModel):
    total: int
    new_count: int = 0
    limit: int
    offset: int
    items: List[Patent]


# ---------------------------------------------------------------------------
def _ids(text: Optional[str]) -> List[int]:
    """'1,4,7' -> [1, 4, 7]"""
    if not text:
        return []
    try:
        return [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="IDs must be comma-separated numbers, e.g. 1,4,7")


SINCE_HELP = "ISO datetime of your last visit, e.g. 2026-11-12T18:40:00Z; adds counts of items first seen after it"


def _naive_utc(since: Optional[datetime]) -> Optional[datetime]:
    """MySQL stores UTC without a zone, so compare against a naive UTC datetime."""
    if since is None or since.tzinfo is None:
        return since
    return since.astimezone(timezone.utc).replace(tzinfo=None)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status", response_model=Status)
def status():
    with get_cursor() as cur:
        cur.execute(queries.STATUS_SQL)
        return cur.fetchone()


@app.get("/journals", response_model=List[Journal])
def journals():
    with get_cursor() as cur:
        cur.execute(queries.JOURNALS_SQL)
        return cur.fetchall()


@app.get("/topics", response_model=List[Topic])
def topics():
    with get_cursor() as cur:
        cur.execute(queries.TOPICS_SQL)
        return cur.fetchall()


class JournalCount(BaseModel):
    journal_id: int
    n: int
    new_n: int = 0


@app.get("/journal-counts", response_model=List[JournalCount])
def journal_counts(
    topics: Optional[str] = Query(None, description="topic IDs, e.g. 2,6 (any of them)"),
    days: int = Query(30, ge=1, le=30),
    q: Optional[str] = Query(None, max_length=200),
    since: Optional[datetime] = Query(None, description=SINCE_HELP),
):
    with get_cursor() as cur:
        sql, params = queries.journal_counts_query(_ids(topics), days, q, _naive_utc(since))
        cur.execute(sql, params)
        return cur.fetchall()


class TopicCount(BaseModel):
    topic_id: int
    n: int


@app.get("/topic-counts", response_model=List[TopicCount])
def topic_counts(
    journals: Optional[str] = Query(None, description="journal IDs, e.g. 1,4,7 (empty = all)"),
    days: int = Query(30, ge=1, le=30),
    q: Optional[str] = Query(None, max_length=200),
):
    with get_cursor() as cur:
        sql, params = queries.topic_counts_query(_ids(journals), days, q)
        cur.execute(sql, params)
        return cur.fetchall()


@app.get("/articles", response_model=ArticlePage)
def articles(
    journals: Optional[str] = Query(None, description="journal IDs, e.g. 1,4,7 (empty = all)"),
    topics: Optional[str] = Query(None, description="topic IDs, e.g. 2,6 (any of them)"),
    days: int = Query(30, ge=1, le=30, description="published in the last N days"),
    q: Optional[str] = Query(None, max_length=200, description="keyword search"),
    since: Optional[datetime] = Query(None, description=SINCE_HELP),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    journal_ids, topic_ids = _ids(journals), _ids(topics)
    with get_cursor() as cur:
        sql, params = queries.count_query(journal_ids, topic_ids, days, q, _naive_utc(since))
        cur.execute(sql, params)
        row = cur.fetchone()
        total, new_count = row["n"], row["new_n"]

        sql, params = queries.articles_query(journal_ids, topic_ids, days, q, limit, offset)
        cur.execute(sql, params)
        items = cur.fetchall()

        if items:   # attach topic names in one extra query, not one per article
            sql, params = queries.topics_for_articles_query([a["article_id"] for a in items])
            cur.execute(sql, params)
            by_article = {}
            for row in cur.fetchall():
                by_article.setdefault(row["article_id"], []).append(row["name"])
            for a in items:
                a["topics"] = by_article.get(a["article_id"], [])
                if a["is_open_access"] is not None:
                    a["is_open_access"] = bool(a["is_open_access"])
    return {"total": total, "new_count": new_count, "limit": limit, "offset": offset, "items": items}


@app.get("/patent-topics", response_model=List[PatentTopic])
def patent_topics():
    with get_cursor() as cur:
        cur.execute(queries.PATENT_TOPICS_SQL)
        return cur.fetchall()


@app.get("/patent-topic-counts", response_model=List[TopicCount])
def patent_topic_counts(
    days: int = Query(90, ge=1, le=90),
    q: Optional[str] = Query(None, max_length=200),
):
    with get_cursor() as cur:
        sql, params = queries.patent_topic_counts_query(days, q)
        cur.execute(sql, params)
        return cur.fetchall()


APPLICANT_HELP = "one applicant name as returned by /patent-applicants, e.g. HOFFMANN LA ROCHE"


class ApplicantCount(BaseModel):
    name: str
    n: int


@app.get("/patent-applicants", response_model=List[ApplicantCount])
def patent_applicants(
    topics: Optional[str] = Query(None, description="patent topic IDs, e.g. 12,13 (any of them)"),
    days: int = Query(90, ge=1, le=90),
    q: Optional[str] = Query(None, max_length=200),
):
    with get_cursor() as cur:
        sql, params = queries.patent_applicants_query(_ids(topics), days, q)
        cur.execute(sql, params)
        rows = [(r["applicants"],) for r in cur.fetchall()]
    return queries.top_applicants(rows)


class WeekCount(BaseModel):
    published_date: date
    n: int


@app.get("/patent-weeks", response_model=List[WeekCount])
def patent_weeks(
    topics: Optional[str] = Query(None, description="patent topic IDs, e.g. 12,13 (any of them)"),
    days: int = Query(90, ge=1, le=90),
    q: Optional[str] = Query(None, max_length=200),
    applicant: Optional[str] = Query(None, max_length=200, description=APPLICANT_HELP),
):
    with get_cursor() as cur:
        sql, params = queries.patent_weeks_query(_ids(topics), days, q, applicant)
        cur.execute(sql, params)
        return cur.fetchall()


@app.get("/patents", response_model=PatentPage)
def patents(
    topics: Optional[str] = Query(None, description="patent topic IDs, e.g. 12,13 (any of them)"),
    days: int = Query(90, ge=1, le=90, description="published in the last N days"),
    q: Optional[str] = Query(None, max_length=200, description="keyword search (title, applicant, abstract)"),
    since: Optional[datetime] = Query(None, description=SINCE_HELP),
    applicant: Optional[str] = Query(None, max_length=200, description=APPLICANT_HELP),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    topic_ids = _ids(topics)
    with get_cursor() as cur:
        sql, params = queries.patent_count_query(topic_ids, days, q, _naive_utc(since), applicant)
        cur.execute(sql, params)
        row = cur.fetchone()
        total, new_count = row["n"], row["new_n"]

        sql, params = queries.patents_query(topic_ids, days, q, limit, offset, applicant)
        cur.execute(sql, params)
        items = cur.fetchall()

        if items:
            sql, params = queries.topics_for_patents_query([p["patent_id"] for p in items])
            cur.execute(sql, params)
            by_patent = {}
            for row in cur.fetchall():
                by_patent.setdefault(row["patent_id"], []).append(row["name"])
            for p in items:
                p["topics"] = by_patent.get(p["patent_id"], [])
    return {"total": total, "new_count": new_count, "limit": limit, "offset": offset, "items": items}
