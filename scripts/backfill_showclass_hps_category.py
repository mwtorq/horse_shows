"""
Backfill sResults.ShowClass.HPSCategory from SHR judges (or results) HTML archives.

Matches archive class headers to existing ShowClass rows by ClassName (exact, then
fuzzy via find_or_insert_class which updates HPS without inserting on HSO-numbered shows
when called carefully).

Usage:
  python scripts/backfill_showclass_hps_category.py --year 2026
  python scripts/backfill_showclass_hps_category.py --sid 18424
"""

from __future__ import annotations

import argparse
import os
import sys

from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hso_shr_class_match import ClassSide, match_classes  # noqa: E402
from reload_judgecards_from_archives import (  # noqa: E402
    find_show_list_ids,
    list_judge_archives,
    load_hso_class_sides,
)
from scrape_saddlehorsereport import (  # noqa: E402
    ensure_schema,
    get_db_connection,
    parse_class_hps_headers,
    print_with_timestamp,
    update_class_hps_category,
)

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ShowClass.HPSCategory")
    parser.add_argument("--year", type=int)
    parser.add_argument("--sid", type=str)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_db_connection()
    ensure_schema(conn)
    archives = list_judge_archives(year=args.year, sid=args.sid)
    print_with_timestamp(f"Archives to scan: {len(archives)} (dry_run={args.dry_run})")

    updated = 0
    unmatched = 0
    for _year, sid, path in archives:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
        headers = parse_class_hps_headers(soup)
        if not headers:
            continue
        show_ids = find_show_list_ids(conn, sid)
        if not show_ids:
            continue
        for show_list_id in show_ids:
            hso_sides = load_hso_class_sides(conn, show_list_id)
            shr_sides = [
                ClassSide(class_id=None, class_name=h["class_name"]) for h in headers
            ]
            matches, un_shr, _ = match_classes(shr_sides, hso_sides, min_score=0.72)
            name_to_hps = {h["class_name"]: h["hps_category"] for h in headers}
            for m in matches:
                if not m.hso.class_id:
                    continue
                hps = name_to_hps.get(m.shr.class_name)
                if not hps:
                    continue
                if args.dry_run:
                    print_with_timestamp(
                        f"  WOULD show={show_list_id} class={m.hso.class_id} "
                        f"'{m.hso.class_name}' <- {hps!r}"
                    )
                else:
                    update_class_hps_category(conn, int(m.hso.class_id), hps)
                    updated += 1
            unmatched += len(un_shr)

    print_with_timestamp(f"Done. updated={updated} unmatched_shr_headers={unmatched}")
    conn.close()


if __name__ == "__main__":
    main()
