"""
Repair SHR rows where the rider was stored as HorseName (Academy/Equitation pattern),
and remove the bogus person-name rows that were inserted into sResults.Horse.

SHR results pages put equitation riders in the Horse column with Rider/Owner as
literal 'n/a'. After scrape_saddlehorsereport.normalize_shr_entry_identity, new
scrapes are correct; this script fixes already-loaded ShowResults + Horse clutter.

Default scope: SHR-only ShowList rows (no ShowGUID) plus blank-Class rows on any
show. Use --all-shr-classes to include every class on shows that have SHRShowID.

Usage:
  python scripts/repair_shr_rider_as_horse.py --dry-run
  python scripts/repair_shr_rider_as_horse.py --apply
  python scripts/repair_shr_rider_as_horse.py --apply --show-list-id 12345
  python scripts/repair_shr_rider_as_horse.py --apply --all-shr-classes
  python scripts/repair_shr_rider_as_horse.py --apply --purge-orphan-horses-only
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, List, Optional, Set, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scrape_class_results import get_db_connection, print_with_timestamp  # noqa: E402
from scrape_saddlehorsereport import (  # noqa: E402
    get_or_create_competitor,
    normalize_shr_entry_identity,
)


def list_bad_rows(
    conn,
    show_list_id: Optional[int] = None,
    all_shr_classes: bool = False,
    limit: Optional[int] = None,
) -> List[Tuple[Any, ...]]:
    """Rows where Horse holds the rider and Rider is missing/n/a."""
    cur = conn.cursor()
    sql = """
        SELECT
          sl.ID AS ShowListID,
          sl.ShowName,
          sc.ID AS ShowClassID,
          sc.Class,
          sc.ClassName,
          sr.ID AS ShowResultsID,
          sr.HorseID,
          sr.RiderID,
          h.HorseName,
          c.Rider
        FROM sResults.ShowResults sr
        INNER JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        INNER JOIN sResults.ShowList sl ON sl.ID = sc.ShowListID
        INNER JOIN sResults.Horse h ON h.ID = sr.HorseID
        LEFT JOIN sResults.Competitors c ON c.ID = sr.RiderID
        WHERE sr.HorseID IS NOT NULL
          AND (
            c.Rider IS NULL
            OR LTRIM(RTRIM(c.Rider)) = ''
            OR UPPER(LTRIM(RTRIM(c.Rider))) IN ('N/A', 'NA', 'NONE')
          )
          AND (
            sc.ClassName LIKE '%Academy%'
            OR sc.ClassName LIKE '%Equitation%'
            OR sc.ClassName LIKE '%Showmanship%'
            OR sc.ClassName LIKE '%Horsemanship%'
            OR h.HorseName LIKE '%(eq)%'
          )
    """
    params: List[Any] = []
    if show_list_id is not None:
        sql += " AND sl.ID = ?"
        params.append(show_list_id)
    elif all_shr_classes:
        sql += " AND sl.SHRShowID IS NOT NULL AND LTRIM(RTRIM(sl.SHRShowID)) <> ''"
    else:
        sql += """
          AND (
            (sl.ShowGUID IS NULL OR LTRIM(RTRIM(sl.ShowGUID)) = '')
            OR LTRIM(RTRIM(ISNULL(sc.Class, ''))) = ''
          )
          AND sl.SHRShowID IS NOT NULL AND LTRIM(RTRIM(sl.SHRShowID)) <> ''
        """
    sql += " ORDER BY sl.ID, sc.ClassName, sr.ID"
    if limit is not None:
        sql = sql.replace("SELECT\n", f"SELECT TOP {int(limit)}\n", 1)
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return rows


def looks_like_person_horse_name(horse_name: str) -> bool:
    name = (horse_name or "").strip()
    if not name:
        return False
    if re.search(r"\(eq\)\s*$", name, re.I):
        return True
    # Typical person: 2–4 alphabetic tokens, no digits, no apostrophe-heavy horse styles optional
    tokens = re.findall(r"[A-Za-z]+", name)
    if len(tokens) < 2 or len(tokens) > 4:
        return False
    if re.search(r"\d", name):
        return False
    # Horse-ish keywords reduce confidence
    horsey = {
        "OF", "THE", "AND", "CH", "CHAMPION", "LADY", "KING", "QUEEN",
        "CF", "WC", "CH", "DREAM", "MAGIC", "SPIRIT", "STAR", "FIRE",
    }
    # Still allow deletion when unreferenced and from eq cleanup set
    return True


def repair_row(
    conn,
    show_results_id: int,
    horse_id: int,
    horse_name: str,
    class_name: str,
    dry_run: bool,
    horse_ids_to_purge: Set[int],
) -> bool:
    identity = normalize_shr_entry_identity(
        horse_name, "n/a", "n/a", class_name=class_name
    )
    rider_name = (identity.get("rider") or "").strip()
    if not rider_name or identity.get("horse"):
        return False
    if dry_run:
        horse_ids_to_purge.add(int(horse_id))
        return True
    rider_id = get_or_create_competitor(conn, rider_name, "Rider")
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE sResults.ShowResults
        SET HorseID = NULL,
            RiderID = ?,
            UpdatedDate = GETDATE()
        WHERE ID = ?
        """,
        rider_id,
        show_results_id,
    )
    conn.commit()
    cur.close()
    horse_ids_to_purge.add(int(horse_id))
    return True


def purge_bogus_horse_rows(
    conn,
    candidate_ids: Set[int],
    dry_run: bool,
    also_scan_eq_suffix: bool = True,
) -> int:
    """
    Delete Horse rows that are no longer referenced by ShowResults and look like
    person names incorrectly logged from SHR (eq marker or provided candidate set).
    """
    cur = conn.cursor()
    ids: Set[int] = set(candidate_ids)
    if also_scan_eq_suffix:
        cur.execute(
            """
            SELECT h.ID
            FROM sResults.Horse h
            WHERE h.HorseName LIKE '%(eq)%'
               OR (
                 -- unreferenced horses whose name matches a Competitors.Rider
                 NOT EXISTS (SELECT 1 FROM sResults.ShowResults sr WHERE sr.HorseID = h.ID)
                 AND EXISTS (
                   SELECT 1 FROM sResults.Competitors c
                   WHERE UPPER(LTRIM(RTRIM(c.Rider))) = UPPER(LTRIM(RTRIM(h.HorseName)))
                      OR UPPER(LTRIM(RTRIM(c.Rider))) = UPPER(LTRIM(RTRIM(
                           REPLACE(REPLACE(h.HorseName, ' (eq)', ''), '(eq)', '')
                         )))
                 )
               )
            """
        )
        ids.update(int(r[0]) for r in cur.fetchall())

    deleted = 0
    for hid in sorted(ids):
        cur.execute(
            "SELECT HorseName FROM sResults.Horse WHERE ID = ?",
            hid,
        )
        row = cur.fetchone()
        if not row:
            continue
        hname = row[0] or ""
        cur.execute(
            "SELECT COUNT(*) FROM sResults.ShowResults WHERE HorseID = ?",
            hid,
        )
        refs = cur.fetchone()[0]
        if refs > 0:
            continue
        if not (
            re.search(r"\(eq\)\s*$", hname, re.I)
            or hid in candidate_ids
            or looks_like_person_horse_name(hname)
        ):
            continue
        if dry_run:
            deleted += 1
            if deleted <= 20:
                print_with_timestamp(f"  WOULD DELETE Horse id={hid} name='{hname}'")
            continue
        try:
            cur.execute("DELETE FROM sResults.Horse WHERE ID = ?", hid)
            deleted += 1
        except Exception as e:
            print_with_timestamp(f"  [WARNING] Could not delete Horse id={hid}: {e}")
            conn.rollback()
            continue
    if not dry_run:
        conn.commit()
    cur.close()
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair SHR rider-as-HorseName rows and purge bogus Horse records"
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--show-list-id", type=int)
    parser.add_argument(
        "--all-shr-classes",
        action="store_true",
        help="Include all classes on any show with SHRShowID (not just orphans/blank)",
    )
    parser.add_argument(
        "--purge-orphan-horses-only",
        action="store_true",
        help="Only delete unreferenced person-as-Horse rows (skip ShowResults rewrite)",
    )
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    dry_run = args.dry_run or not args.apply

    conn = get_db_connection()
    horse_ids_to_purge: Set[int] = set()
    fixed = 0

    if not args.purge_orphan_horses_only:
        rows = list_bad_rows(
            conn,
            show_list_id=args.show_list_id,
            all_shr_classes=args.all_shr_classes,
            limit=args.limit,
        )
        print_with_timestamp(f"Candidate ShowResults: {len(rows)} (dry_run={dry_run})")
        for r in rows:
            sl_id, _show, _scid, _cnum, cname, srid, hid, _rid, hname, _rider = r
            ok = repair_row(
                conn,
                int(srid),
                int(hid),
                hname or "",
                cname or "",
                dry_run=dry_run,
                horse_ids_to_purge=horse_ids_to_purge,
            )
            if ok:
                fixed += 1
                if fixed <= 15:
                    print_with_timestamp(
                        f"  {'WOULD FIX' if dry_run else 'FIXED'} sl={sl_id} "
                        f"sr={srid} horse_id={hid} '{hname}' -> Rider "
                        f"(class={((cname or '')[:40])})"
                    )
        print_with_timestamp(
            f"ShowResults {'would fix' if dry_run else 'fixed'}={fixed}/{len(rows)}"
        )
    else:
        print_with_timestamp("Skipping ShowResults rewrite (--purge-orphan-horses-only)")

    purged = purge_bogus_horse_rows(
        conn,
        horse_ids_to_purge,
        dry_run=dry_run,
        also_scan_eq_suffix=True,
    )
    print_with_timestamp(
        f"Horse table {'would delete' if dry_run else 'deleted'} unreferenced "
        f"person-rows={purged}"
    )
    conn.close()


if __name__ == "__main__":
    main()
