"""Hacker News "Ask HN: Who is hiring?" threads via the official HN API.

Each month the account ``whoishiring`` posts a thread; every top-level
comment is one job posting, usually starting with a header line such as

    Acme Corp | Senior Backend Engineer | Berlin or REMOTE (EU) | Full-time | €90-110k

API docs: https://github.com/HackerNews/API
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Iterator

from bs4 import BeautifulSoup

from ..http import PoliteSession
from .base import Posting, Source

log = logging.getLogger(__name__)
API = "https://hacker-news.firebaseio.com/v0"
THREAD_RE = re.compile(r"^Ask HN: Who is hiring\? \((\w+ \d{4})\)", re.I)

ROLE_WORDS = re.compile(r"\b(engineer|developer|scientist|analyst|designer|manager|architect|"
                        r"sre|devops|lead|researcher|intern|cto|head of|specialist|administrator)\b", re.I)
EMPLOYMENT = re.compile(r"\b(full[- ]?time|part[- ]?time|contract|contractor|freelance|internship|"
                        r"permanent|visa|equity|ft|pt)\b", re.I)
SALARY = re.compile(r"([$€£₹]\s?\d|\d+\s?k\b|\d{2,3},\d{3}|salary|compensation)", re.I)
REMOTE = re.compile(r"\bremote\b", re.I)
ONSITE = re.compile(r"\b(onsite|on-site|in[- ]office|no remote)\b", re.I)
URLISH = re.compile(r"(https?://|www\.|\.com\b|\.io\b|\.ai\b)", re.I)


def html_to_text(raw: str) -> str:
    soup = BeautifulSoup(raw or "", "html.parser")
    for p in soup.find_all("p"):
        p.insert_before("\n")
    return html.unescape(soup.get_text()).strip()


def parse_header(text: str) -> dict:
    """Best-effort parse of the 'Company | Role | Location | ...' header line."""
    first = text.split("\n", 1)[0]
    parts = [p.strip() for p in re.split(r"\s+[|•·]\s+|\s\|\s?|\|\s", first) if p.strip()]
    out = {"company": "", "title": "", "location": "", "salary": "", "remote": None}
    if len(parts) < 2:
        return out
    out["company"] = re.sub(r"\s*\(.*?\)\s*$", "", parts[0])[:200]
    roles, locs = [], []
    for p in parts[1:]:
        if URLISH.search(p) and len(p.split()) <= 3:
            continue
        if SALARY.search(p) and not ROLE_WORDS.search(p):
            out["salary"] = out["salary"] or p
        elif ROLE_WORDS.search(p):
            roles.append(p)
        elif EMPLOYMENT.fullmatch(p.strip().lower()) or (EMPLOYMENT.search(p) and len(p.split()) <= 3):
            continue
        else:
            locs.append(p)
    whole = " ".join(parts[1:])
    if REMOTE.search(whole):
        out["remote"] = not ONSITE.search(whole) or bool(re.search(r"remote\s*(ok|friendly|possible|or)", whole, re.I))
    elif ONSITE.search(whole):
        out["remote"] = False
    out["title"] = "; ".join(roles)[:300]
    out["location"] = "; ".join(locs)[:300]
    return out


class HNWhoIsHiring(Source):
    name = "hn_whoishiring"

    def __init__(self, session: PoliteSession | None = None, months: int = 3):
        # The HN API is a public JSON API without published rate limits;
        # 0.1 s between calls keeps us well-behaved.
        self.session = session or PoliteSession(min_interval=0.1, respect_robots=False)
        self.months = months

    def threads(self) -> list[dict]:
        user = self.session.get_json(f"{API}/user/whoishiring.json")
        found = []
        for item_id in user.get("submitted", [])[:60]:  # the account posts ~3 threads/month
            item = self.session.get_json(f"{API}/item/{item_id}.json") or {}
            m = THREAD_RE.match(item.get("title", ""))
            if m:
                item["month"] = datetime.strptime(m.group(1), "%B %Y").replace(tzinfo=timezone.utc)
                found.append(item)
            if len(found) >= self.months:
                break
        return found

    def fetch(self, known_ids: set[str]) -> Iterator[Posting]:
        for thread in self.threads():
            kids = thread.get("kids", [])
            new = [k for k in kids if str(k) not in known_ids]
            log.info("%s: %d comments, %d new", thread["title"], len(kids), len(new))
            for cid in new:
                c = self.session.get_json(f"{API}/item/{cid}.json")
                if not c or c.get("deleted") or c.get("dead") or not c.get("text"):
                    continue
                yield self.to_posting(c, thread)

    @staticmethod
    def to_posting(c: dict, thread: dict) -> Posting:
        text = html_to_text(c["text"])
        h = parse_header(text)
        return Posting(
            source=HNWhoIsHiring.name, external_id=str(c["id"]),
            url=f"https://news.ycombinator.com/item?id={c['id']}",
            text=text, title=h["title"], company=h["company"], location=h["location"],
            remote=h["remote"], salary=h["salary"],
            posted_at=datetime.fromtimestamp(c.get("time", 0), tz=timezone.utc),
            extra={"thread_id": thread["id"], "thread_month": thread["month"].strftime("%Y-%m")},
        )
