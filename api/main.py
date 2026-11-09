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
    GET /patents                placeholder until the patents section is built
"""

from datetime import date, datetime
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
    topics: List[str] = []


class ArticlePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[Article]


class Status(BaseModel):
    last_refreshed: Optional[datetime] = None
    total_articles: int
    with_figure: int


# ---------------------------------------------------------------------------
def _ids(text: Optional[str]) -> List[int]:
    """'1,4,7' -> [1, 4, 7]"""
    if not text:
        return []
    try:
        return [int(x) for x in text.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=422, detail="IDs must be comma-separated numbers, e.g. 1,4,7")


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


@app.get("/articles", response_model=ArticlePage)
def articles(
    journals: Optional[str] = Query(None, description="journal IDs, e.g. 1,4,7 (empty = all)"),
    topics: Optional[str] = Query(None, description="topic IDs, e.g. 2,6 (any of them)"),
    days: int = Query(30, ge=1, le=30, description="published in the last N days"),
    q: Optional[str] = Query(None, max_length=200, description="keyword search"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    journal_ids, topic_ids = _ids(journals), _ids(topics)
    with get_cursor() as cur:
        sql, params = queries.count_query(journal_ids, topic_ids, days, q)
        cur.execute(sql, params)
        total = cur.fetchone()["n"]

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
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/patents")
def patents():
    return {"status": "coming_soon",
            "message": "New Patents is coming soon. Patent data from the EPO is being set up."}
