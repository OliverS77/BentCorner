"""Shadow check for the sync (docs/SYNC-PLAN.md §3b): rebuild the library from the logs alone – copies AND the fields
the sync carries – and compare it with collection.json. Only reads; run it on a COPY of real data:

    set BC_HOME=<copy>   (a folder with data/my-data …, never app\\)
    python tools/sync_shadow.py [game …] [--show 20] [--fill]   (--fill: with the repair of old lines, in memory)

Prints per game: entries, copies, how many differ (count / per field) and examples.
"""
import json
import os
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("BC_HOME"):
    sys.exit("BC_HOME must point at a copy of the data (never the real app folder)")

from collection import shadow  # noqa: E402


def main():
    args = sys.argv[1:]
    show = int(args[args.index("--show") + 1]) if "--show" in args else 10
    wanted = [a for a in args if not a.startswith("--") and not a.isdigit()]
    import games
    home = pathlib.Path(os.environ["BC_HOME"])
    keys = wanted or [g for g, _n, _r in games.GAMES if games.folders(g, home / "data")["mine"].exists()]
    total = 0
    for g in keys:
        mine = games.folders(g, home / "data")["mine"]
        rep = shadow.report(mine, fill="--fill" in args)
        total += rep["differ"]
        print(f"== {g}: {rep['entries']} entries, {rep['copies']} copies, {rep['logs']} logs – "
              f"differ: {rep['differ']} (count {rep['by_field'].get('count', 0)}, "
              + ", ".join(f"{k} {v}" for k, v in sorted(rep["by_field"].items()) if k != "count") + ")"
              + f"; not in logs (trade marks): {rep['trade_only']}")
        for ex in rep["examples"][:show]:
            print("   ", json.dumps(ex, ensure_ascii=False))
    print(f"TOTAL differ: {total}")


if __name__ == "__main__":
    main()
