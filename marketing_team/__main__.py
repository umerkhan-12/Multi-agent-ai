"""CLI.

  python -m marketing_team seed              # load demo data
  python -m marketing_team status            # $ marketing status --today
  python -m marketing_team run               # run the daily analytics loop + brief
  python -m marketing_team attribution       # which posts brought calls and sales
  python -m marketing_team message "how much is coaching?" --channel whatsapp --sender 923001234567
"""
from __future__ import annotations

import argparse
import json

from . import db, orchestrator, seed
from .config import settings


def main() -> None:
    ap = argparse.ArgumentParser(prog="marketing_team")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    sub.add_parser("status")
    sub.add_parser("run")
    a = sub.add_parser("attribution")
    a.add_argument("--days", type=int, default=30)
    m = sub.add_parser("message")
    m.add_argument("text")
    m.add_argument("--channel", default="whatsapp")
    m.add_argument("--sender", default="923000000000")
    m.add_argument("--ref")
    args = ap.parse_args()

    db.init_db()
    if args.cmd == "seed":
        print(seed.seed())
    elif args.cmd == "status":
        print(f"$ marketing status --today   (LLM: {settings.provider})")
        for k, v in db.status_today().items():
            print(f"  {k:<18}{v}")
    elif args.cmd == "run":
        out = orchestrator.run_daily()
        print(out["brief"])
        print("\nLoop fed:", json.dumps(out["loop"]))
    elif args.cmd == "attribution":
        print(f"{'Post':<28}{'Views':>9}{'Leads':>7}{'Calls':>7}{'Sales':>7}{'Revenue':>10}")
        for r in db.attribution(args.days):
            print(f"{r['title'][:27]:<28}{r['views']:>9,}{r['leads']:>7}{r['calls']:>7}{r['sales']:>7}"
                  f"{r['revenue']:>10,.0f}")
    elif args.cmd == "message":
        print(json.dumps(orchestrator.on_message(args.channel, args.sender, args.text, post_ref=args.ref,
                                                 reply=False), indent=2))


if __name__ == "__main__":
    main()
