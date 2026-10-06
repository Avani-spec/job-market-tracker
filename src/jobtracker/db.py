"""Storage with SQLAlchemy Core. PostgreSQL in production, SQLite for local
runs and tests (set ``DATABASE_URL``)."""
from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String,
                        Table, Text, UniqueConstraint, create_engine, select)
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

DEFAULT_URL = "sqlite:///jobs.db"
meta = MetaData()

postings = Table(
    "postings", meta,
    Column("id", Integer, primary_key=True),
    Column("source", String(64), nullable=False, index=True),
    Column("external_id", String(512), nullable=False),
    Column("url", Text),
    Column("title", Text), Column("company", Text), Column("location", Text),
    Column("remote", Boolean), Column("salary", Text), Column("role", String(64)),
    Column("text", Text, nullable=False),
    Column("posted_at", DateTime(timezone=True), index=True),
    Column("scraped_at", DateTime(timezone=True), nullable=False),
    Column("content_hash", String(40), nullable=False, unique=True),
    Column("extra", JSON),
    UniqueConstraint("source", "external_id", name="uq_source_external"),
)

posting_skills = Table(
    "posting_skills", meta,
    Column("posting_id", Integer, ForeignKey("postings.id", ondelete="CASCADE"), primary_key=True),
    Column("skill", String(64), primary_key=True, index=True),
    Column("mentions", Integer, nullable=False, default=1),
)

scrape_runs = Table(
    "scrape_runs", meta,
    Column("id", Integer, primary_key=True),
    Column("source", String(64), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("n_seen", Integer, default=0), Column("n_new", Integer, default=0),
    Column("n_duplicate", Integer, default=0),
    Column("status", String(16), default="running"), Column("error", Text),
)


def get_engine(url: str | None = None):
    url = url or os.environ.get("DATABASE_URL", DEFAULT_URL)
    eng = create_engine(url, future=True)
    meta.create_all(eng)
    return eng


def now():
    return datetime.now(timezone.utc)


def insert_ignore(conn, table, values: dict):
    """INSERT ... ON CONFLICT DO NOTHING; returns the new primary key or None."""
    ins = pg_insert(table) if conn.dialect.name == "postgresql" else sqlite_insert(table)
    res = conn.execute(ins.values(**values).on_conflict_do_nothing().returning(table.c.id))
    row = res.first()
    return row[0] if row else None


def known_ids(conn, source: str) -> set[str]:
    return {r[0] for r in conn.execute(select(postings.c.external_id).where(postings.c.source == source))}
