"""
Match SHR-only ShowList orphans to existing HSO (ShowGUID) rows and merge.

Uses the same composite name/date/location/state scorer as scrape_saddlehorsereport.py.

Usage:
  python scripts/repair_shr_showlist_matches.py --dry-run
  python scripts/repair_shr_showlist_matches.py --apply
  python scripts/repair_shr_showlist_matches.py --apply --year 2025
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scrape_saddlehorsereport import (  # noqa: E402
    find_best_hso_show_match,
    get_db_connection,
    normalize_state_code,
    print_with_timestamp,
)


def count_match_stats(conn) -> Tuple[int, int, int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          SUM(CASE WHEN SHRShowID IS NOT NULL AND LTRIM(RTRIM(SHRShowID)) <> ''
                    AND ShowGUID IS NOT NULL AND ShowGUID <> '' THEN 1 ELSE 0 END),
          SUM(CASE WHEN SHRShowID IS NOT NULL AND LTRIM(RTRIM(SHRShowID)) <> ''
                    AND (ShowGUID IS NULL OR ShowGUID = '') THEN 1 ELSE 0 END),
          SUM(CASE WHEN SHRShowID IS NOT NULL AND LTRIM(RTRIM(SHRShowID)) <> '' THEN 1 ELSE 0 END)
        FROM sResults.ShowList
        """
    )
    matched, orphans, total = cur.fetchone()
    cur.close()
    return int(matched or 0), int(orphans or 0), int(total or 0)


def list_orphans(conn, year: Optional[int] = None) -> List[tuple]:
    cur = conn.cursor()
    if year:
        cur.execute(
            """
            SELECT ID, Year, ShowName, ShowDate, ShowLocation, StateProv, SHRShowID
            FROM sResults.ShowList
            WHERE SHRShowID IS NOT NULL AND LTRIM(RTRIM(SHRShowID)) <> ''
              AND (ShowGUID IS NULL OR ShowGUID = '')
              AND Year = ?
            ORDER BY Year, ID
            """,
            year,
        )
    else:
        cur.execute(
            """
            SELECT ID, Year, ShowName, ShowDate, ShowLocation, StateProv, SHRShowID
            FROM sResults.ShowList
            WHERE SHRShowID IS NOT NULL AND LTRIM(RTRIM(SHRShowID)) <> ''
              AND (ShowGUID IS NULL OR ShowGUID = '')
            ORDER BY Year, ID
            """
        )
    rows = cur.fetchall()
    cur.close()
    return rows


def merge_orphan_into_hso(
    conn,
    orphan_id: int,
    hso_id: int,
    shr_id: str,
    show_date: Optional[str],
    location: Optional[str],
    state: Optional[str],
) -> None:
    """Move classes/judges from orphan to HSO row, stamp SHRShowID, delete orphan."""
    cur = conn.cursor()
    try:
        state_abbr = normalize_state_code(state)
        cur.execute(
            """
            UPDATE sResults.ShowList
            SET SHRShowID = COALESCE(NULLIF(SHRShowID, ''), ?),
                ShowLocation = COALESCE(NULLIF(ShowLocation, ''), ?),
                ShowDate = COALESCE(NULLIF(ShowDate, ''), ?),
                StateProv = COALESCE(NULLIF(StateProv, ''), ?),
                UpdatedDate = GETDATE()
            WHERE ID = ?
            """,
            shr_id,
            location or None,
            show_date or None,
            state_abbr,
            hso_id,
        )

        # Prefer HSO class when both sides have the same ClassName; else reparent.
        cur.execute(
            """
            SELECT ID, ClassName FROM sResults.ShowClass WHERE ShowListID = ?
            """,
            orphan_id,
        )
        orphan_classes = cur.fetchall()
        cur.execute(
            """
            SELECT ID, ClassName FROM sResults.ShowClass WHERE ShowListID = ?
            """,
            hso_id,
        )
        hso_by_name = {(n or "").strip().upper(): i for i, n in cur.fetchall()}

        for oc_id, oc_name in orphan_classes:
            key = (oc_name or "").strip().upper()
            if key and key in hso_by_name:
                hso_class_id = hso_by_name[key]
                # Move results from orphan class onto HSO class, then drop orphan class
                cur.execute(
                    """
                    UPDATE sr
                    SET sr.ShowClassID = ?
                    FROM sResults.ShowResults sr
                    WHERE sr.ShowClassID = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM sResults.ShowResults x
                          WHERE x.ShowClassID = ?
                            AND ISNULL(x.Place, -1) = ISNULL(sr.Place, -1)
                            AND ISNULL(x.Entry, '') = ISNULL(sr.Entry, '')
                            AND ISNULL(x.HorseID, 0) = ISNULL(sr.HorseID, 0)
                      )
                    """,
                    hso_class_id,
                    oc_id,
                    hso_class_id,
                )
                # Reassign judge cards that still point at leftover orphan results
                # (cards follow ShowResultsID; leftovers deleted with results below)
                cur.execute(
                    "DELETE FROM sResults.ShowResults_JudgeCard WHERE ShowResultsID IN "
                    "(SELECT ID FROM sResults.ShowResults WHERE ShowClassID = ?)",
                    oc_id,
                )
                cur.execute(
                    "DELETE FROM sResults.ShowResults WHERE ShowClassID = ?",
                    oc_id,
                )
                cur.execute("DELETE FROM sResults.ShowClass WHERE ID = ?", oc_id)
            else:
                cur.execute(
                    "UPDATE sResults.ShowClass SET ShowListID = ? WHERE ID = ?",
                    hso_id,
                    oc_id,
                )

        # Judges: move unique names; drop duplicates
        cur.execute(
            """
            SELECT ID, JudgeName FROM sResults.ShowJudge WHERE ShowListID = ?
            """,
            orphan_id,
        )
        for jid, jname in cur.fetchall():
            cur.execute(
                """
                SELECT ID FROM sResults.ShowJudge
                WHERE ShowListID = ? AND JudgeName = ?
                """,
                hso_id,
                jname,
            )
            existing = cur.fetchone()
            if existing:
                # Repoint cards from orphan judge to HSO judge, then delete orphan judge
                cur.execute(
                    """
                    UPDATE jc
                    SET jc.ShowJudgeID = ?
                    FROM sResults.ShowResults_JudgeCard jc
                    WHERE jc.ShowJudgeID = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM sResults.ShowResults_JudgeCard x
                          WHERE x.ShowResultsID = jc.ShowResultsID AND x.ShowJudgeID = ?
                      )
                    """,
                    existing[0],
                    jid,
                    existing[0],
                )
                cur.execute(
                    "DELETE FROM sResults.ShowResults_JudgeCard WHERE ShowJudgeID = ?",
                    jid,
                )
                cur.execute("DELETE FROM sResults.ShowJudge WHERE ID = ?", jid)
            else:
                cur.execute(
                    "UPDATE sResults.ShowJudge SET ShowListID = ? WHERE ID = ?",
                    hso_id,
                    jid,
                )

        # Clear SHRShowID on orphan before delete (unique-ish safety)
        cur.execute(
            "UPDATE sResults.ShowList SET SHRShowID = NULL WHERE ID = ?",
            orphan_id,
        )
        cur.execute("DELETE FROM sResults.ShowList WHERE ID = ?", orphan_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair SHR ShowList orphans into HSO rows")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Print proposed merges only")
    mode.add_argument("--apply", action="store_true", help="Perform merges")
    parser.add_argument("--year", type=int, action="append", help="Limit to year(s); repeatable")
    args = parser.parse_args()

    conn = get_db_connection()
    before = count_match_stats(conn)
    print_with_timestamp(
        f"Before: matched_hso={before[0]} orphans={before[1]} total_shr={before[2]}"
    )

    years = args.year or [None]
    proposed = 0
    applied = 0
    unmatched = 0

    for year in years:
        orphans = list_orphans(conn, year)
        print_with_timestamp(
            f"Orphans to consider year={year or 'ALL'}: {len(orphans)}"
        )
        for oid, oyear, name, sdate, loc, state, shr_id in orphans:
            match = find_best_hso_show_match(
                conn,
                show_name=name or "",
                year=int(oyear) if oyear is not None else None,
                show_date=sdate or "",
                location=loc or "",
                state=state or "",
                exclude_shr_id=str(shr_id),
            )
            if not match:
                unmatched += 1
                continue
            hso_id, score = match
            proposed += 1
            print_with_timestamp(
                f"  {'WOULD MERGE' if args.dry_run else 'MERGE'} "
                f"orphan={oid} sid={shr_id} '{name}' -> HSO={hso_id} score={score:.2f} "
                f"date={sdate!r} loc={loc!r} st={state!r}"
            )
            if args.apply:
                merge_orphan_into_hso(
                    conn,
                    orphan_id=oid,
                    hso_id=hso_id,
                    shr_id=str(shr_id),
                    show_date=sdate,
                    location=loc,
                    state=state,
                )
                applied += 1

    after = count_match_stats(conn)
    print_with_timestamp(
        f"Done: proposed={proposed} applied={applied} unmatched_orphans={unmatched}"
    )
    print_with_timestamp(
        f"After: matched_hso={after[0]} orphans={after[1]} total_shr={after[2]}"
    )
    conn.close()


if __name__ == "__main__":
    main()
