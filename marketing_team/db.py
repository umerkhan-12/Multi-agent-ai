"""SQLite system of record.

Three business tables mirror the diagram (posts.db / leads.db / sales.db) but live
in one file so we can JOIN them for attribution ("which posts brought calls and
sales"). Swap the connection for Postgres when you go multi-tenant.

Operational tables:
  approvals   – human approval queue (You approve)
  escalations – "What interrupts the loop" items
  events      – append-only audit log of every agent action
  runs        – one row per agent run, with tokens + cost
  emails      – drafted / sent emails
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT NOT NULL,
    platform      TEXT NOT NULL,          -- tiktok | instagram | youtube | linkedin | blog | newsletter
    format        TEXT NOT NULL,          -- reel | carousel | short | long | article | email
    hook          TEXT,
    script        TEXT,
    caption       TEXT,
    asset_url     TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft|needs_approval|approved|scheduled|published|rejected
    scheduled_at  TEXT,
    published_at  TEXT,
    external_id   TEXT,
    views         INTEGER DEFAULT 0,
    likes         INTEGER DEFAULT 0,
    comments      INTEGER DEFAULT 0,
    shares        INTEGER DEFAULT 0,
    saves         INTEGER DEFAULT 0,
    utm           TEXT,                   -- tracking code used for attribution
    created_by    TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT,
    email           TEXT UNIQUE,
    handle          TEXT,
    source          TEXT,                 -- dm | comment | form | lead_magnet | ...
    source_post_id  INTEGER REFERENCES posts(id),
    score           INTEGER DEFAULT 0,
    segment         TEXT,
    stage           TEXT DEFAULT 'new',   -- new|nurturing|call_booked|call_done|customer|lost|unsubscribed
    call_at         TEXT,
    notes           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sales (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id       INTEGER REFERENCES leads(id),
    amount_usd    REAL NOT NULL,
    product       TEXT,
    status        TEXT DEFAULT 'paid',    -- link_sent|paid|refunded
    payment_ref   TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS emails (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT,                     -- newsletter|sequence|winback|reminder
    segment     TEXT,
    subject     TEXT,
    body        TEXT,
    status      TEXT DEFAULT 'draft',     -- draft|needs_approval|approved|sent
    sent_count  INTEGER DEFAULT 0,
    opens       INTEGER DEFAULT 0,
    clicks      INTEGER DEFAULT 0,
    created_by  TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS approvals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,            -- post|email|reply|page
    ref_id      INTEGER,
    summary     TEXT,
    requested_by TEXT,
    status      TEXT DEFAULT 'pending',   -- pending|approved|rejected
    decided_at  TEXT,
    feedback    TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escalations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger     TEXT NOT NULL,            -- see guardrails.TRIGGERS
    severity    TEXT DEFAULT 'normal',    -- low|normal|high
    ref_type    TEXT,
    ref_id      INTEGER,
    detail      TEXT,
    status      TEXT DEFAULT 'open',      -- open|resolved
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent       TEXT,
    action      TEXT,
    payload     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent         TEXT,
    department    TEXT,
    task          TEXT,
    output        TEXT,
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd      REAL DEFAULT 0,
    ok            INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _connect() -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def connect():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)


def insert(table: str, **values: Any) -> int:
    values.setdefault("created_at", now())
    cols = ", ".join(values)
    qs = ", ".join("?" for _ in values)
    with connect() as c:
        cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({qs})", tuple(values.values()))
        return int(cur.lastrowid)


def update(table: str, row_id: int, **values: Any) -> None:
    if not values:
        return
    sets = ", ".join(f"{k} = ?" for k in values)
    with connect() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", (*values.values(), row_id))


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, tuple(params)).fetchall()]


def one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def readonly_query(sql: str, limit: int = 200) -> list[dict]:
    """Agent-facing SQL. Only a single SELECT is allowed; enforced by SQLite itself."""
    stripped = sql.strip().rstrip(";")
    if ";" in stripped or not stripped.lower().startswith(("select", "with")):
        raise ValueError("Only a single SELECT/WITH statement is allowed.")
    conn = sqlite3.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(stripped).fetchmany(limit)]
    finally:
        conn.close()


def log_event(agent: str, action: str, payload: Any = None) -> None:
    insert("events", agent=agent, action=action, payload=json.dumps(payload, default=str))


# ── Analytics helpers used by the dashboard, brief and Post Analyst ──────────

ATTRIBUTION_SQL = """
SELECT p.id, p.title, p.platform, p.format, p.views,
       COUNT(DISTINCT l.id)                                         AS leads,
       COUNT(DISTINCT CASE WHEN l.call_at IS NOT NULL THEN l.id END) AS calls,
       COUNT(DISTINCT s.id)                                         AS sales,
       COALESCE(SUM(CASE WHEN s.status='paid' THEN s.amount_usd END), 0) AS revenue
FROM posts p
LEFT JOIN leads l ON l.source_post_id = p.id
LEFT JOIN sales s ON s.lead_id = l.id
WHERE p.status = 'published' AND p.published_at >= date('now', ?)
GROUP BY p.id
ORDER BY revenue DESC, calls DESC, views DESC
"""


def attribution(days: int = 30) -> list[dict]:
    return query(ATTRIBUTION_SQL, (f"-{days} days",))


def spend_today() -> float:
    row = one("SELECT COALESCE(SUM(cost_usd),0) AS s FROM runs WHERE created_at >= ?", (today(),))
    return float(row["s"]) if row else 0.0


def status_today() -> dict:
    d = today()
    q = lambda sql: (one(sql, (d,)) or {}).get("n", 0)  # noqa: E731
    return {
        "posts_written": q("SELECT COUNT(*) n FROM posts WHERE created_at >= ?"),
        "videos_posted": q("SELECT COUNT(*) n FROM posts WHERE status='published' "
                           "AND format IN ('reel','short','long') AND published_at >= ?"),
        "comments_replied": q("SELECT COUNT(*) n FROM events WHERE action='reply_sent' AND created_at >= ?"),
        "calls_booked": q("SELECT COUNT(*) n FROM events WHERE action='call_booked' AND created_at >= ?"),
        "waiting_on_you": (one("SELECT COUNT(*) n FROM approvals WHERE status='pending'") or {}).get("n", 0)
        + (one("SELECT COUNT(*) n FROM escalations WHERE status='open'") or {}).get("n", 0),
        "spend_usd": round(spend_today(), 4),
    }
