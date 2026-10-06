# Job Market Intelligence & Skill Tracker

A data pipeline that collects public job postings, extracts the technologies
each one asks for, and tracks how skill demand changes over time.

```
 sources ──► polite HTTP client ──► parse (BeautifulSoup) ──► de-duplicate ──► PostgreSQL
 (HN API,     robots.txt, per-host                               │
  HTML boards) rate limit, retries                               ▼
                                              skill extraction (NLTK + taxonomy)
                                                                 │
                                               monthly trends, movers, co-occurrence
```

## Sources

| Source | How | Notes |
|---|---|---|
| `hn` | Official [Hacker News API](https://github.com/HackerNews/API): monthly *"Ask HN: Who is hiring?"* threads, one posting per top-level comment | Comment HTML is parsed with BeautifulSoup. The `Company \| Role \| Location \| …` header is split into structured fields. Years of history are available, which makes good trend data. |
| `board` | Config-driven HTML scraper; CSS selectors live in `boards/*.yaml` | `boards/python_org.yaml` is an example. Selectors can go stale when a site changes its markup. If a scrape returns 0 rows, inspect the page and update them. |

Large commercial job sites (LinkedIn, Indeed, Glassdoor) forbid scraping in
their terms of service, so they are deliberately not included. Before adding
any site, check its terms. `robots.txt` is enforced automatically.

## Pipeline details

- **Politeness and reliability.** `PoliteSession` checks `robots.txt`, keeps a
  minimum interval between requests per host, sends an identifying
  User-Agent, and retries 429/5xx responses with exponential backoff
  (respecting `Retry-After`).
- **Incremental scraping.** IDs already in the database are never fetched
  again. HTML boards stop paginating at the first page with nothing new.
- **De-duplication.** There is a `UNIQUE(source, external_id)` constraint plus
  a content hash of company + title + text + posting month, with
  `INSERT … ON CONFLICT DO NOTHING`. The month is part of the hash, so a
  company re-posting every month still counts once per month in the trend
  series.
- **Auditability.** Every run is recorded in `scrape_runs` (seen / new /
  duplicate counts, status, error). Progress is committed every 50 postings,
  so a crash keeps what was already stored.
- **Skill extraction.** An NLTK `RegexpTokenizer` keeps names like `C++`,
  `C#`, `.NET` and `Node.js` intact. 1–3-grams are then matched against
  `skills.yaml` (~65 skills with aliases such as `k8s → Kubernetes`).
  Ambiguous names (`Go`, `R`, `C`, `Spark`, `Swift`) only match with the right
  casing and context, so "go to conferences" is not counted as Go. After
  editing the taxonomy, run `jobtracker reextract`.
- **Analysis.** Covers top skills, monthly share of postings per skill,
  biggest movers (last 6 months vs the 6 before), skill co-occurrence, and the
  role mix.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[postgres,dev]"
pytest                                  # 13 offline tests (no network needed)

# local SQLite
jobtracker -v scrape hn --months 12     # ~12 threads x ~400 comments, polite pacing
jobtracker report --out reports/
jobtracker cooccur PyTorch
jobtracker skills "Python/Django, k8s, Postgres, LLMs"

# PostgreSQL
docker compose up -d
cp .env.example .env && set -a && . ./.env
jobtracker scrape hn --months 24
```

### Scheduling

Use cron (see `crontab.example`) or a systemd timer for production. For a
quick setup, `jobtracker schedule --every-hours 24 hn --months 1` loops in
the foreground.

## Output

`jobtracker report` writes `top_skills.csv/png`, `monthly_skill_share.csv`,
`skill_trends.png`, `movers.csv` and `roles.csv` to `reports/`.

<!-- Add a screenshot of reports/skill_trends.png and a few findings here after your first real scrape. -->

## Layout

```
src/jobtracker/
  http.py            robots.txt, rate limiting, retries
  sources/hn.py      HN "Who is hiring?" source + header parser
  sources/html_board.py   YAML-configured BeautifulSoup scraper
  skills.py, skills.yaml  tokeniser, taxonomy, role classifier
  db.py              SQLAlchemy Core schema (PostgreSQL / SQLite)
  pipeline.py        scrape → store → extract, run bookkeeping
  analysis.py        trends and report
  cli.py
boards/              site configs
tests/               fake-API and HTML fixtures, no network required
```
