"""Scrape -> de-duplicate -> store -> extract skills, with one row per run in
``scrape_runs`` so failures and volumes are auditable."""
from __future__ import annotations

import logging

from sqlalchemy import delete, select, update

from . import db
from .skills import classify_role, extract_skills
from .sources.base import Posting, Source

log = logging.getLogger(__name__)


def store(conn, p: Posting) -> bool:
    pid = db.insert_ignore(conn, db.postings, dict(
        source=p.source, external_id=p.external_id, url=p.url, title=p.title,
        company=p.company, location=p.location, remote=p.remote, salary=p.salary,
        role=classify_role(p.title), text=p.text, posted_at=p.posted_at, scraped_at=db.now(),
        content_hash=p.content_hash(), extra=p.extra))
    if pid is None:
        return False
    for skill, n in extract_skills(f"{p.title}\n{p.text}").items():
        conn.execute(db.posting_skills.insert().values(posting_id=pid, skill=skill, mentions=n))
    return True


def run(source: Source, engine, commit_every: int = 50) -> dict:
    with engine.begin() as conn:
        run_id = conn.execute(db.scrape_runs.insert().values(
            source=source.name, started_at=db.now())).inserted_primary_key[0]
        known = db.known_ids(conn, source.name)
    stats = {"n_seen": 0, "n_new": 0, "n_duplicate": 0}
    status, error = "ok", None
    conn = engine.connect()
    tx = conn.begin()
    try:
        for p in source.fetch(known):
            stats["n_seen"] += 1
            if store(conn, p):
                stats["n_new"] += 1
            else:
                stats["n_duplicate"] += 1
            if stats["n_seen"] % commit_every == 0:  # checkpoint progress
                tx.commit(); tx = conn.begin()
                log.info("%s: %s", source.name, stats)
        tx.commit()
    except Exception as e:  # keep what was stored, record the failure
        tx.commit()
        status, error = "error", repr(e)
        log.exception("scrape failed")
    finally:
        conn.close()
    with engine.begin() as c:
        c.execute(update(db.scrape_runs).where(db.scrape_runs.c.id == run_id).values(
            finished_at=db.now(), status=status, error=error, **stats))
    return {"status": status, **stats}


def reextract(engine) -> int:
    """Recompute skills for every posting (run after editing skills.yaml)."""
    with engine.begin() as conn:
        conn.execute(delete(db.posting_skills))
        rows = conn.execute(select(db.postings.c.id, db.postings.c.title, db.postings.c.text)).all()
        for pid, title, text in rows:
            conn.execute(update(db.postings).where(db.postings.c.id == pid).values(role=classify_role(title or "")))
            for skill, n in extract_skills(f"{title}\n{text}").items():
                conn.execute(db.posting_skills.insert().values(posting_id=pid, skill=skill, mentions=n))
    return len(rows)
