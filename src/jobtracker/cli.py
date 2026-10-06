"""jobtracker command line.

    jobtracker scrape hn --months 12          # HN "Who is hiring?" threads
    jobtracker scrape board boards/python_org.yaml
    jobtracker reextract                      # after editing skills.yaml
    jobtracker report --out reports/
    jobtracker skills "We use Python, k8s and Postgres"   # try the extractor
    jobtracker schedule --every-hours 24 hn   # simple built-in scheduler
"""
from __future__ import annotations

import argparse
import logging
import time

import pandas as pd

from . import analysis, db, pipeline
from .skills import extract_skills


def make_source(args):
    if args.kind == "hn":
        from .sources.hn import HNWhoIsHiring
        return HNWhoIsHiring(months=args.months)
    from .sources.html_board import HTMLBoard
    return HTMLBoard.from_yaml(args.config)


def main(argv=None):
    p = argparse.ArgumentParser(prog="jobtracker")
    p.add_argument("--db", help="SQLAlchemy URL (default: $DATABASE_URL or sqlite:///jobs.db)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("scrape", "schedule"):
        s = sub.add_parser(name)
        if name == "schedule":
            s.add_argument("--every-hours", type=float, default=24)
        k = s.add_subparsers(dest="kind", required=True)
        hn = k.add_parser("hn"); hn.add_argument("--months", type=int, default=3)
        b = k.add_parser("board"); b.add_argument("config")
    sub.add_parser("reextract")
    r = sub.add_parser("report"); r.add_argument("--out", default="reports"); r.add_argument("--source")
    r.add_argument("--top", type=int, default=20)
    sk = sub.add_parser("skills"); sk.add_argument("text")
    co = sub.add_parser("cooccur"); co.add_argument("skill")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if a.cmd == "skills":
        print(dict(extract_skills(a.text)))
        return
    eng = db.get_engine(a.db)
    if a.cmd == "scrape":
        print(pipeline.run(make_source(a), eng))
    elif a.cmd == "schedule":
        while True:  # for production prefer cron / systemd timers (see README)
            print(time.strftime("%F %T"), pipeline.run(make_source(a), eng), flush=True)
            time.sleep(a.every_hours * 3600)
    elif a.cmd == "reextract":
        print(f"re-extracted skills for {pipeline.reextract(eng)} postings")
    elif a.cmd == "cooccur":
        _, skills = analysis.load_frames(eng)
        print(analysis.cooccurrence(skills, a.skill).round(3).to_string())
    elif a.cmd == "report":
        res = analysis.report(eng, a.out, a.source, a.top)
        with pd.option_context("display.width", 120):
            print(f"{res['postings']:,} postings across {res['months']} months\n")
            print(res["top"].round(3).to_string(), "\n")
            print(res["roles"].round(3).to_string(), "\n")
            if "movers" in res:
                print("Biggest movers (percentage points):")
                print(res["movers"].round(3).to_string())
        print(f"\nCSV and PNG files written to {a.out}/")


if __name__ == "__main__":
    main()
