"""Config-driven scraper for server-rendered HTML job boards (BeautifulSoup).

Boards change their markup over time, so selectors live in a YAML file rather
than in code (see ``boards/*.yaml``). Always check a site's terms and
robots.txt before adding it; ``PoliteSession`` enforces robots.txt.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterator
from urllib.parse import urljoin

import yaml
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from ..http import PoliteSession
from .base import Posting, Source

log = logging.getLogger(__name__)


def _text(node, selector):
    if not selector:
        return ""
    el = node.select_one(selector)
    return el.get_text(" ", strip=True) if el else ""


class HTMLBoard(Source):
    def __init__(self, config: dict, session: PoliteSession | None = None):
        self.cfg = config
        self.name = config["name"]
        self.session = session or PoliteSession(min_interval=config.get("min_interval", 2.0))

    @classmethod
    def from_yaml(cls, path, session=None):
        with open(path) as f:
            return cls(yaml.safe_load(f), session)

    def parse_listing(self, html: str, page_url: str) -> list[dict]:
        c = self.cfg["listing"]
        soup = BeautifulSoup(html, "html.parser")
        rows = []
        for item in soup.select(c["item"]):
            link = item.select_one(c["link"])
            if not link or not link.get("href"):
                continue
            posted = None
            if c.get("posted"):
                el = item.select_one(c["posted"])
                raw = (el.get(c.get("posted_attr", "datetime")) or el.get_text(strip=True)) if el else None
                if raw:
                    try:
                        posted = dateparser.parse(raw)
                    except (ValueError, OverflowError):
                        posted = None
            title = link.get_text(" ", strip=True)
            company = _text(item, c.get("company"))
            if company.startswith(title):  # company span also wraps the title link
                company = company[len(title):].strip()
            rows.append({
                "url": urljoin(page_url, link["href"]),
                "title": title,
                "company": company,
                "location": _text(item, c.get("location")),
                "posted_at": posted,
            })
        nxt = soup.select_one(c["next_page"]) if c.get("next_page") else None
        next_url = urljoin(page_url, nxt["href"]) if nxt and nxt.get("href") else None
        return rows, next_url

    def parse_detail(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        el = soup.select_one(self.cfg["detail"]["body"])
        return el.get_text("\n", strip=True) if el else ""

    def fetch(self, known_ids: set[str]) -> Iterator[Posting]:
        url, pages = self.cfg["start_url"], 0
        while url and pages < self.cfg.get("max_pages", 5):
            rows, url = self.parse_listing(self.session.get(url).text, url)
            pages += 1
            fresh = [r for r in rows if r["url"] not in known_ids]
            if rows and not fresh:  # incremental: everything on this page is known
                log.info("%s: reached already-scraped postings, stopping", self.name)
                return
            for r in fresh:
                text = self.parse_detail(self.session.get(r["url"]).text)
                yield Posting(source=self.name, external_id=r["url"], url=r["url"], text=text,
                              title=r["title"], company=r["company"], location=r["location"],
                              remote=("remote" in f"{r['location']} {text[:300]}".lower()) or None,
                              posted_at=r["posted_at"] or datetime.utcnow())
