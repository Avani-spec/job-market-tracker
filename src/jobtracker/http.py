"""A polite HTTP client: robots.txt, per-host rate limiting, retries with backoff."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)
DEFAULT_UA = "JobMarketTracker/0.1 (+https://github.com/<your-username>/job-market-tracker)"


class RateLimiter:
    """Guarantees at least ``min_interval`` seconds between calls per host."""

    def __init__(self, min_interval: float = 1.0, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self.clock, self.sleep = clock, sleep
        self._last: dict[str, float] = {}

    def wait(self, host: str):
        now = self.clock()
        last = self._last.get(host)
        if last is not None and now - last < self.min_interval:
            self.sleep(self.min_interval - (now - last))
        self._last[host] = self.clock()


class RobotsDisallowed(Exception):
    pass


class PoliteSession:
    def __init__(self, min_interval: float = 1.0, user_agent: str = DEFAULT_UA,
                 timeout: float = 20.0, retries: int = 4, respect_robots: bool = True):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = user_agent
        retry = Retry(total=retries, backoff_factor=1.0, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET",), respect_retry_after_header=True)
        self.s.mount("https://", HTTPAdapter(max_retries=retry))
        self.s.mount("http://", HTTPAdapter(max_retries=retry))
        self.limiter = RateLimiter(min_interval)
        self.timeout = timeout
        self.ua = user_agent
        self.respect_robots = respect_robots
        self._robots: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.s.get(base + "/robots.txt", timeout=self.timeout)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[base] = rp
        return self._robots[base].can_fetch(self.ua, url)

    def get(self, url: str, **kw) -> requests.Response:
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        self.limiter.wait(urlparse(url).netloc)
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def get_json(self, url: str, **kw):
        return self.get(url, **kw).json()
