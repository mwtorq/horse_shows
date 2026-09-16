"""
Full HSO recapture for SHR-merged shows: restore Entries + Horse/Rider/Owner/Trainer
from HorseShowsOnline, archiving raw pages under horseshowsonline/{year}/{kind}/.

Kinds:
  showdetails/              - ShowDetails page
  results/                  - ClassResults summary grid
  classes/{show}/           - each expanded class detail snapshot

Usage:
  python scripts/recapture_merged_hso_shows.py --show-list-id 10296
  python scripts/recapture_merged_hso_shows.py --apply
  python scripts/recapture_merged_hso_shows.py --apply --year 2026
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scrape_class_results import (  # noqa: E402
    get_db_connection,
    log_import_activity,
    print_with_timestamp,
    scrape_class_results_for_show,
    setup_driver,
)


def list_merged_shows(
    conn,
    year: Optional[int] = None,
    show_list_id: Optional[int] = None,
    skip_show_list_ids: Optional[List[int]] = None,
    limit: Optional[int] = None,
) -> List[Tuple[int, str, Optional[int], str]]:
    cur = conn.cursor()
    sql = """
        SELECT sl.ID, sl.ShowGUID, sl.Year, sl.ShowName
        FROM sResults.ShowList sl
        WHERE sl.ShowGUID IS NOT NULL AND LTRIM(RTRIM(sl.ShowGUID)) <> ''
          AND sl.SHRShowID IS NOT NULL AND LTRIM(RTRIM(sl.SHRShowID)) <> ''
    """
    params: List[Any] = []
    if year is not None:
        sql += " AND sl.Year = ?"
        params.append(year)
    if show_list_id is not None:
        sql += " AND sl.ID = ?"
        params.append(show_list_id)
    if skip_show_list_ids:
        placeholders = ",".join("?" * len(skip_show_list_ids))
        sql += f" AND sl.ID NOT IN ({placeholders})"
        params.extend(skip_show_list_ids)
    sql += " ORDER BY sl.Year DESC, sl.ID"
    cur.execute(sql, params)
    rows = [
        (int(r[0]), str(r[1]), int(r[2]) if r[2] is not None else None, r[3] or "")
        for r in cur.fetchall()
    ]
    cur.close()
    if limit is not None:
        rows = rows[:limit]
    return rows


def sync_identity_to_blank_classes(conn, show_list_id: int) -> int:
    """
    Copy Horse/Rider/Trainer from HSO-numbered class results onto SHR blank-Class
    siblings in the same show.

    MUST match ClassName (case-insensitive). Matching by Entry alone is unsafe:
    the same entry number appears in many unrelated classes within one show.
    """
    cur = conn.cursor()
    updated = 0
    try:
        cur.execute(
            """
            UPDATE tgt
            SET
              tgt.HorseID = CASE
                  WHEN tgt.HorseID IS NULL THEN src.HorseID
                  ELSE tgt.HorseID END,
              tgt.RiderID = CASE
                  WHEN tgt.RiderID IS NULL THEN src.RiderID
                  ELSE tgt.RiderID END,
              tgt.TrainerID = CASE
                  WHEN tgt.TrainerID IS NULL AND src.TrainerID IS NOT NULL THEN src.TrainerID
                  ELSE tgt.TrainerID END,
              tgt.UpdatedDate = GETDATE()
            FROM sResults.ShowResults tgt
            INNER JOIN sResults.ShowClass tc ON tc.ID = tgt.ShowClassID
            INNER JOIN sResults.ShowClass sc ON sc.ShowListID = tc.ShowListID
              AND LTRIM(RTRIM(ISNULL(sc.Class, ''))) <> ''
              AND UPPER(LTRIM(RTRIM(ISNULL(sc.ClassName, ''))))
                = UPPER(LTRIM(RTRIM(ISNULL(tc.ClassName, ''))))
            INNER JOIN sResults.ShowResults src ON src.ShowClassID = sc.ID
              AND src.Entry = tgt.Entry
              AND ISNULL(src.Entry, '') <> ''
            WHERE tc.ShowListID = ?
              AND LTRIM(RTRIM(ISNULL(tc.Class, ''))) = ''
              AND (
                tgt.HorseID IS NULL OR tgt.RiderID IS NULL OR tgt.TrainerID IS NULL
              )
            """,
            show_list_id,
        )
        updated += cur.rowcount or 0

        # Prefer HSO identity when blank-class horse name equals rider (SHR swap)
        # and ClassName matches a numbered sibling.
        cur.execute(
            """
            UPDATE tgt
            SET
              tgt.HorseID = src.HorseID,
              tgt.RiderID = src.RiderID,
              tgt.TrainerID = COALESCE(src.TrainerID, tgt.TrainerID),
              tgt.UpdatedDate = GETDATE()
            FROM sResults.ShowResults tgt
            INNER JOIN sResults.ShowClass tc ON tc.ID = tgt.ShowClassID
            INNER JOIN sResults.Horse th ON th.ID = tgt.HorseID
            INNER JOIN sResults.Competitors tr ON tr.ID = tgt.RiderID
            INNER JOIN sResults.ShowClass sc ON sc.ShowListID = tc.ShowListID
              AND LTRIM(RTRIM(ISNULL(sc.Class, ''))) <> ''
              AND UPPER(LTRIM(RTRIM(ISNULL(sc.ClassName, ''))))
                = UPPER(LTRIM(RTRIM(ISNULL(tc.ClassName, ''))))
            INNER JOIN sResults.ShowResults src ON src.ShowClassID = sc.ID
              AND src.Entry = tgt.Entry AND ISNULL(src.Entry, '') <> ''
              AND src.HorseID IS NOT NULL
            WHERE tc.ShowListID = ?
              AND LTRIM(RTRIM(ISNULL(tc.Class, ''))) = ''
              AND UPPER(LTRIM(RTRIM(th.HorseName))) = UPPER(LTRIM(RTRIM(ISNULL(tr.Rider, ''))))
            """,
            show_list_id,
        )
        updated += cur.rowcount or 0

        conn.commit()
    except Exception as e:
        conn.rollback()
        print_with_timestamp(f"  [WARNING] sync_identity_to_blank_classes failed: {e}")
        return 0
    finally:
        cur.close()
    return updated


def revert_unsafe_blank_trainer_sync(conn, show_list_id: int, since: str) -> int:
    """
    Undo Entry-only trainer fills on blank-Class rows (no ClassName match to source).
    Clears TrainerID when the blank ClassName has no numbered sibling with the same name.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE sr
            SET sr.TrainerID = NULL, sr.UpdatedDate = GETDATE()
            FROM sResults.ShowResults sr
            INNER JOIN sResults.ShowClass tc ON tc.ID = sr.ShowClassID
            WHERE tc.ShowListID = ?
              AND LTRIM(RTRIM(ISNULL(tc.Class, ''))) = ''
              AND sr.TrainerID IS NOT NULL
              AND sr.UpdatedDate >= ?
              AND NOT EXISTS (
                SELECT 1
                FROM sResults.ShowClass sc
                WHERE sc.ShowListID = tc.ShowListID
                  AND LTRIM(RTRIM(ISNULL(sc.Class, ''))) <> ''
                  AND UPPER(LTRIM(RTRIM(ISNULL(sc.ClassName, ''))))
                    = UPPER(LTRIM(RTRIM(ISNULL(tc.ClassName, ''))))
              )
            """,
            show_list_id,
            since,
        )
        n = cur.rowcount or 0
        conn.commit()
        return n
    except Exception as e:
        conn.rollback()
        print_with_timestamp(f"  [WARNING] revert_unsafe_blank_trainer_sync failed: {e}")
        return 0
    finally:
        cur.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Recapture merged shows from HSO")
    parser.add_argument("--show-list-id", type=int, help="Single ShowList.ID (e.g. 10296)")
    parser.add_argument(
        "--skip-show-list-id",
        type=int,
        action="append",
        default=[],
        help="Skip ShowList.ID(s); repeatable",
    )
    parser.add_argument("--year", type=int, help="Limit to year")
    parser.add_argument("--limit", type=int, help="Max shows")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--no-class-archives",
        action="store_true",
        help="Skip per-class detail HTML archives (still saves showdetails + results)",
    )
    args = parser.parse_args()

    conn = get_db_connection()
    shows = list_merged_shows(
        conn,
        year=args.year,
        show_list_id=args.show_list_id,
        skip_show_list_ids=args.skip_show_list_id or None,
        limit=args.limit,
    )
    print_with_timestamp(f"Merged shows to recapture: {len(shows)}")
    if not shows:
        conn.close()
        return

    log_import_activity(
        conn,
        "recapture_merged_hso_shows.py",
        action="START",
        additional_info=f"shows={len(shows)} show_list_id={args.show_list_id} year={args.year}",
    )

    driver = setup_driver(headless=not args.headed)
    total_results = 0
    try:
        for idx, (sl_id, guid, year, name) in enumerate(shows, 1):
            print_with_timestamp(
                f"\n[{idx}/{len(shows)}] Recapture ShowListID={sl_id} year={year} '{name}'"
            )
            try:
                count, driver = scrape_class_results_for_show(
                    driver,
                    sl_id,
                    guid,
                    year,
                    name,
                    conn,
                    show_class_ids=None,
                    use_direct_url=True,
                    sleep_short=0.3,
                    sleep_medium=0.5,
                    sleep_long=1,
                    prefer_hso_identity=True,
                    archive_class_details=not args.no_class_archives,
                )
                total_results += count or 0
                print_with_timestamp(
                    f"  Recapture saved/enriched={count} (blank-class sync disabled)"
                )
                log_import_activity(
                    conn,
                    "recapture_merged_hso_shows.py",
                    target_table="ShowResults",
                    action="RECAPTURE_SHOW",
                    row_count=count,
                    additional_info=(
                        f"ShowListID={sl_id}, ShowGUID={guid}, enriched={count}, synced=0"
                    ),
                )
            except Exception as e:
                print_with_timestamp(f"  [ERROR] {e}")
                import traceback

                traceback.print_exc()
                try:
                    conn.rollback()
                except Exception:
                    pass
            time.sleep(0.4)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        log_import_activity(
            conn,
            "recapture_merged_hso_shows.py",
            action="COMPLETE",
            row_count=total_results,
            additional_info=f"shows={len(shows)} total_results={total_results}",
        )
        conn.close()

    print_with_timestamp(f"Done. shows={len(shows)} total_results_touched={total_results}")


if __name__ == "__main__":
    main()
