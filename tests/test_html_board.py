from jobtracker.sources.html_board import HTMLBoard

CFG = {
    "name": "demo", "start_url": "https://jobs.example.org/",
    "listing": {"item": "ol.jobs > li", "link": "h2 a", "company": "h2 span.co",
                "location": "span.loc", "posted": "time", "posted_attr": "datetime",
                "next_page": "a.next"},
    "detail": {"body": "div.desc"},
}
LISTING = """<ol class="jobs">
<li><h2><a href="/jobs/1/">Python Developer</a> <span class="co">Acme</span></h2>
    <span class="loc">Remote</span><time datetime="2026-09-01T10:00:00Z">Sep 1</time></li>
<li><h2><a href="/jobs/2/">Data Engineer</a> <span class="co">Beta</span></h2>
    <span class="loc">Pune, India</span><time datetime="2026-09-03">Sep 3</time></li>
</ol><a class="next" href="?page=2">Next</a>"""
DETAIL = {"https://jobs.example.org/jobs/1/": "<div class='desc'>Django, Postgres, Docker</div>",
          "https://jobs.example.org/jobs/2/": "<div class='desc'>Airflow and Spark</div>"}


class Resp:
    def __init__(self, text): self.text = text


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        if url in DETAIL:
            return Resp(DETAIL[url])
        return Resp(LISTING if "page=2" not in url else "<ol class='jobs'></ol>")


def test_parse_listing():
    rows, nxt = HTMLBoard(CFG, FakeSession()).parse_listing(LISTING, CFG["start_url"])
    assert [r["title"] for r in rows] == ["Python Developer", "Data Engineer"]
    assert rows[0]["url"] == "https://jobs.example.org/jobs/1/" and rows[1]["location"] == "Pune, India"
    assert rows[0]["posted_at"].year == 2026 and nxt == "https://jobs.example.org/?page=2"


def test_fetch_incremental_stops_on_known_page():
    sess = FakeSession()
    got = list(HTMLBoard(CFG, sess).fetch(known_ids={"https://jobs.example.org/jobs/1/"}))
    assert [p.title for p in got] == ["Data Engineer"] and "Airflow" in got[0].text
    sess2 = FakeSession()
    assert list(HTMLBoard(CFG, sess2).fetch(known_ids=set(DETAIL))) == []
    assert sess2.calls == ["https://jobs.example.org/"]
