"""
Backfill sResults.ShowList.HPSLabel / HPSMultiplier from SHR judges HTML archives.

Does not touch JudgeCards — only show-level HPS fields.

Usage:
  python scripts/backfill_showlist_hps_from_archives.py
  python scripts/backfill_showlist_hps_from_archives.py --year 2026
  python scripts/backfill_showlist_hps_from_archives.py --sid 18424
"""

from __future__ import annotations

import argparse
import os
import sys

from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reload_judgecards_from_archives import (  # noqa: E402
    find_show_list_ids,
    list_judge_archives,
)
from scrape_saddlehorsereport import (  # noqa: E402
    ensure_schema,
    get_db_connection,
    parse_show_meta,
    print_with_timestamp,
    update_show_hps,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ShowList HPS from SHR archives")
    parser.add_argument("--year", type=int)
    parser.add_argument("--sid", type=str)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_db_connection()
    ensure_schema(conn)
    archives = list_judge_archives(year=args.year, sid=args.sid)
    print_with_timestamp(f"Archives to scan: {len(archives)} (dry_run={args.dry_run})")

    updated = 0
    skipped = 0
    no_show = 0
    for year, sid, path in archives:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        meta = parse_show_meta(soup)
        label = meta.get("hps_label")
        mult = meta.get("hps_multiplier")
        if not label and mult is None:
            skipped += 1
            continue
        show_ids = find_show_list_ids(conn, sid)
        if not show_ids:
            no_show += 1
            continue
        for show_list_id in show_ids:
            if args.dry_run:
                print_with_timestamp(
                    f"  WOULD set show={show_list_id} sid={sid} "
                    f"HPSLabel={label!r} HPSMultiplier={mult}"
                )
            else:
                update_show_hps(conn, show_list_id, label, mult)
                print_with_timestamp(
                    f"  Updated show={show_list_id} sid={sid} "
                    f"HPSLabel={label!r} HPSMultiplier={mult}"
                )
            updated += 1

    print_with_timestamp(
        f"Done. updated={updated} no_hps_in_archive={skipped} no_showlist={no_show}"
    )
    conn.close()


if __name__ == "__main__":
    main()
