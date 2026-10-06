"""Trend analysis over the stored postings."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import select

from . import db
from .skills import category_of


def load_frames(engine, source: str | None = None):
    q = select(db.postings.c.id, db.postings.c.source, db.postings.c.posted_at,
               db.postings.c.role, db.postings.c.remote, db.postings.c.company)
    if source:
        q = q.where(db.postings.c.source == source)
    posts = pd.read_sql(q, engine)
    skills = pd.read_sql(select(db.posting_skills), engine)
    skills = skills[skills.posting_id.isin(posts.id)]
    posts["month"] = pd.to_datetime(posts["posted_at"], utc=True).dt.tz_convert(None).dt.to_period("M").astype(str)
    return posts, skills


def monthly_share(posts, skills, min_postings: int = 20) -> pd.DataFrame:
    """Share of postings per month that mention each skill (months x skills)."""
    totals = posts.groupby("month").size()
    totals = totals[totals >= min_postings]
    m = skills.merge(posts[["id", "month"]], left_on="posting_id", right_on="id")
    counts = m.groupby(["month", "skill"]).size().unstack(fill_value=0)
    return counts.loc[counts.index.isin(totals.index)].div(totals, axis=0).sort_index()


def top_skills(posts, skills, n: int = 25) -> pd.DataFrame:
    c = skills.groupby("skill").posting_id.nunique().sort_values(ascending=False)
    df = pd.DataFrame({"postings": c, "share": c / len(posts)}).head(n)
    df["category"] = [category_of(s) for s in df.index]
    return df


def movers(share: pd.DataFrame, window: int = 6, n: int = 10) -> pd.DataFrame:
    """Change in mean share between the last ``window`` months and the
    ``window`` months before that (percentage points)."""
    if len(share) < 2 * window:
        window = max(1, len(share) // 2)
    recent, before = share.iloc[-window:].mean(), share.iloc[-2 * window:-window].mean()
    d = pd.DataFrame({"before": before, "recent": recent, "change_pp": (recent - before) * 100})
    d = d[(d.before > 0.01) | (d.recent > 0.01)].sort_values("change_pp")
    return pd.concat([d.head(n), d.tail(n)]).drop_duplicates()


def cooccurrence(skills, focus: str, n: int = 10) -> pd.Series:
    ids = set(skills.loc[skills.skill == focus, "posting_id"])
    if not ids:
        return pd.Series(dtype=float)
    other = skills[skills.posting_id.isin(ids) & (skills.skill != focus)]
    return (other.groupby("skill").posting_id.nunique() / len(ids)).sort_values(ascending=False).head(n)


def report(engine, out_dir: str = "reports", source: str | None = None, top: int = 20) -> dict:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    posts, skills = load_frames(engine, source)
    if posts.empty:
        raise SystemExit("no postings in the database yet - run a scrape first")
    ts = top_skills(posts, skills, top)
    share = monthly_share(posts, skills)
    ts.to_csv(out / "top_skills.csv")
    share.to_csv(out / "monthly_skill_share.csv")
    roles = posts.role.value_counts(normalize=True)
    roles.to_csv(out / "roles.csv")

    fig, ax = plt.subplots(figsize=(8, 7))
    ts["share"].iloc[::-1].mul(100).plot.barh(ax=ax, color="#2f5d62")
    ax.set_xlabel("% of postings mentioning skill"); ax.set_title(f"Top skills ({len(posts):,} postings)")
    fig.tight_layout(); fig.savefig(out / "top_skills.png", dpi=140); plt.close(fig)

    result = {"postings": len(posts), "months": len(share)}
    if len(share) >= 2:
        cols = [c for c in ts.index[:8] if c in share]
        ax = share[cols].mul(100).plot(figsize=(10, 5), marker=".")
        ax.set_ylabel("% of postings"); ax.set_title("Skill demand over time")
        ax.figure.tight_layout(); ax.figure.savefig(out / "skill_trends.png", dpi=140); plt.close(ax.figure)
        mv = movers(share)
        mv.to_csv(out / "movers.csv")
        result["movers"] = mv
    result["top"] = ts
    result["roles"] = roles
    return result
