from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional


@dataclass
class Posting:
    source: str
    external_id: str
    url: str
    text: str
    title: str = ""
    company: str = ""
    location: str = ""
    remote: Optional[bool] = None
    salary: str = ""
    posted_at: Optional[datetime] = None
    extra: dict = field(default_factory=dict)

    def content_hash(self) -> str:
        """Fingerprint for cross-source de-duplication. Includes the posting
        month so that a company re-posting every month still counts once per
        month in the trend series."""
        norm = re.sub(r"\W+", " ", f"{self.company} {self.title} {self.text[:600]}".lower()).strip()
        month = self.posted_at.strftime("%Y-%m") if self.posted_at else ""
        return hashlib.sha1(f"{month}|{norm}".encode()).hexdigest()


class Source:
    name = "source"

    def fetch(self, known_ids: set[str]) -> Iterator[Posting]:  # pragma: no cover
        raise NotImplementedError
