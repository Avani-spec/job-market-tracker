from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from jobtracker import analysis, db, pipeline
from jobtracker.sources.hn import HNWhoIsHiring, parse_header

T_SEP = int(datetime(2026, 9, 2, tzinfo=timezone.utc).timestamp())
T_AUG = int(datetime(2026, 8, 3, tzinfo=timezone.utc).timestamp())

API = {
    "user/whoishiring": {"submitted": [100, 101, 200]},
    "item/100": {"id": 100, "title": "Ask HN: Who is hiring? (September 2026)", "kids": [1, 2, 3, 4]},
    "item/101": {"id": 101, "title": "Ask HN: Who wants to be hired? (September 2026)"},
    "item/200": {"id": 200, "title": "Ask HN: Who is hiring? (August 2026)", "kids": [5, 6]},
    "item/1": {"id": 1, "time": T_SEP, "text": "Acme | Senior Backend Engineer | Berlin | REMOTE (EU) | $150k<p>We use Go, Postgres and Kubernetes."},
    "item/2": {"id": 2, "time": T_SEP, "text": "Beta AI | ML Engineer | Bangalore, India | Onsite<p>PyTorch, Python, LLMs &amp; RAG."},
    "item/3": {"id": 3, "deleted": True},
    "item/4": {"id": 4, "time": T_SEP, "text": "Gamma | Frontend Developer | Remote<p>React, TypeScript."},
    "item/5": {"id": 5, "time": T_AUG, "text": "Acme | Senior Backend Engineer | Berlin | REMOTE (EU) | $150k<p>We use Go, Postgres and Kubernetes."},
    "item/6": {"id": 6, "time": T_AUG, "text": "Delta | Data Engineer | NYC<p>Python, Airflow, dbt, Snowflake."},
}


class FakeSession:
    def __init__(self):
        self.calls = []

    def get_json(self, url):
        key = url.split("/v0/")[1].removesuffix(".json")
        self.calls.append(key)
        return API.get(key)


@pytest.fixture
def engine(tmp_path):
    return db.get_engine(f"sqlite:///{tmp_path}/t.db")


def test_parse_header():
    h = parse_header("Acme | Senior Backend Engineer | Berlin | REMOTE (EU) | $150k\nbody")
    assert h["company"] == "Acme" and "Backend" in h["title"] and h["location"] == "Berlin; REMOTE (EU)"
    assert h["remote"] is True and h["salary"] == "$150k"
    assert parse_header("Foo | Engineer | Onsite in Austin")["remote"] is False


def test_scrape_store_dedup_and_incremental(engine):
    src = HNWhoIsHiring(session=FakeSession(), months=2)
    r = pipeline.run(src, engine)
    assert r == {"status": "ok", "n_seen": 5, "n_new": 5, "n_duplicate": 0}
    with engine.connect() as c:
        assert c.execute(select(func.count()).select_from(db.postings)).scalar() == 5
        skills = {s for (s,) in c.execute(select(db.posting_skills.c.skill))}
    assert {"Go", "PostgreSQL", "Kubernetes", "PyTorch", "RAG", "dbt"} <= skills

    # second run: no item already stored is fetched again
    sess = FakeSession()
    r2 = pipeline.run(HNWhoIsHiring(session=sess, months=2), engine)
    assert r2["n_seen"] == 0
    assert not any(k in sess.calls for k in ("item/1", "item/2", "item/5"))
    with engine.connect() as c:
        runs = c.execute(select(db.scrape_runs.c.status)).all()
    assert [s for (s,) in runs] == ["ok", "ok"]


def test_same_text_same_month_is_duplicate(engine):
    from jobtracker.sources.base import Posting
    p = Posting("x", "1", "u", "same text", company="A", posted_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
    q = Posting("y", "9", "u2", "same text", company="A", posted_at=datetime(2026, 9, 20, tzinfo=timezone.utc))
    with engine.begin() as c:
        assert pipeline.store(c, p) is True
        assert pipeline.store(c, q) is False


def test_report(engine, tmp_path):
    pipeline.run(HNWhoIsHiring(session=FakeSession(), months=2), engine)
    posts, skills = analysis.load_frames(engine)
    share = analysis.monthly_share(posts, skills, min_postings=1)
    assert list(share.index) == ["2026-08", "2026-09"]
    assert share.loc["2026-08", "Python"] == pytest.approx(0.5)
    res = analysis.report(engine, tmp_path / "rep")
    assert (tmp_path / "rep" / "top_skills.png").exists()
    assert res["postings"] == 5
