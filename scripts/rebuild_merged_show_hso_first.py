"""
HSO-first rebuild for dual-linked (ShowGUID + SHRShowID) shows.

1. Snapshot SHR judge cards (ClassName/Entry/Place/Judge) before wipe
2. Wipe ShowResults_JudgeCard → ShowResults → ShowClass (keep ShowList + ShowJudge)
3. Recapture from HSO with substantive classdetail archives
4. Reload JudgeCards from SHR judges HTML archives (Entry-aware) when present
5. Fall back to fuzzy-matching pre-wipe snapshot onto HSO ShowResults if archive empty

Usage:
  python scripts/rebuild_merged_show_hso_first.py --show-list-id 10296
  python scripts/rebuild_merged_show_hso_first.py --apply-all --skip-show-list-id 10296
  python scripts/rebuild_merged_show_hso_first.py --show-list-id 10296 --snapshot-only
  python scripts/rebuild_merged_show_hso_first.py --show-list-id 10296 --judges-only
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hso_shr_class_match import (  # noqa: E402
    ClassSide,
    match_classes,
    write_match_report,
)
from reload_judgecards_from_archives import reload_archives_for_show  # noqa: E402
from scrape_class_results import (  # noqa: E402
    get_db_connection,
    log_import_activity,
    print_with_timestamp,
    scrape_class_results_for_show,
    setup_driver,
)

SNAPSHOT_ROOT = os.path.join(REPO_ROOT, "merge_rebuild_snapshots")


def snapshot_path(show_list_id: int) -> str:
    return os.path.join(SNAPSHOT_ROOT, f"show_{show_list_id}_judges.json")


def list_merged_shows(
    conn,
    show_list_id: Optional[int] = None,
    skip_ids: Optional[List[int]] = None,
    limit: Optional[int] = None,
) -> List[Tuple[int, str, Optional[int], str, str]]:
    cur = conn.cursor()
    sql = """
        SELECT sl.ID, sl.ShowGUID, sl.Year, sl.ShowName, sl.SHRShowID
        FROM sResults.ShowList sl
        WHERE sl.ShowGUID IS NOT NULL AND LTRIM(RTRIM(sl.ShowGUID)) <> ''
          AND sl.SHRShowID IS NOT NULL AND LTRIM(RTRIM(sl.SHRShowID)) <> ''
    """
    params: List[Any] = []
    if show_list_id is not None:
        sql += " AND sl.ID = ?"
        params.append(show_list_id)
    if skip_ids:
        sql += f" AND sl.ID NOT IN ({','.join('?' * len(skip_ids))})"
        params.extend(skip_ids)
    sql += " ORDER BY sl.Year DESC, sl.ID"
    cur.execute(sql, params)
    rows = [
        (int(r[0]), str(r[1]), int(r[2]) if r[2] is not None else None, r[3] or "", str(r[4]))
        for r in cur.fetchall()
    ]
    cur.close()
    if limit is not None:
        rows = rows[:limit]
    return rows


def snapshot_judge_cards(conn, show_list_id: int) -> Dict[str, Any]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          sc.ID AS ShrClassID,
          sc.Class AS ShrClassNum,
          sc.ClassName,
          sc.Entries,
          sr.ID AS ShowResultsID,
          sr.Entry,
          sr.Place,
          h.HorseName,
          c.Rider,
          j.JudgeName,
          jc.Entry AS JudgeEntry,
          jc.Place AS JudgePlace
        FROM sResults.ShowResults_JudgeCard jc
        INNER JOIN sResults.ShowResults sr ON sr.ID = jc.ShowResultsID
        INNER JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        INNER JOIN sResults.ShowJudge j ON j.ID = jc.ShowJudgeID
        LEFT JOIN sResults.Horse h ON h.ID = sr.HorseID
        LEFT JOIN sResults.Competitors c ON c.ID = sr.RiderID
        WHERE sc.ShowListID = ?
        ORDER BY sc.ClassName, sr.Place, j.JudgeName
        """,
        show_list_id,
    )
    cols = [d[0] for d in cur.description]
    cards = [dict(zip(cols, row)) for row in cur.fetchall()]

    # Also capture blank-class result identity even without cards (for matching)
    cur.execute(
        """
        SELECT sc.ID, sc.ClassName, sc.Entries, sr.Entry, sr.Place, h.HorseName, c.Rider
        FROM sResults.ShowResults sr
        INNER JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        LEFT JOIN sResults.Horse h ON h.ID = sr.HorseID
        LEFT JOIN sResults.Competitors c ON c.ID = sr.RiderID
        WHERE sc.ShowListID = ?
          AND LTRIM(RTRIM(ISNULL(sc.Class, ''))) = ''
        """,
        show_list_id,
    )
    blank_results = [
        {
            "ShrClassID": r[0],
            "ClassName": r[1],
            "Entries": r[2],
            "Entry": r[3],
            "Place": r[4],
            "HorseName": r[5],
            "Rider": r[6],
        }
        for r in cur.fetchall()
    ]
    cur.close()

    payload = {
        "show_list_id": show_list_id,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "judge_cards": cards,
        "blank_results": blank_results,
    }
    path = snapshot_path(show_list_id)
    os.makedirs(SNAPSHOT_ROOT, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print_with_timestamp(
        f"Snapshot {show_list_id}: cards={len(cards)} blank_results={len(blank_results)} -> {path}"
    )
    return payload


def load_snapshot(show_list_id: int) -> Dict[str, Any]:
    path = snapshot_path(show_list_id)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def wipe_show_classes_and_results(conn, show_list_id: int) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        DELETE jc
        FROM sResults.ShowResults_JudgeCard jc
        INNER JOIN sResults.ShowResults sr ON sr.ID = jc.ShowResultsID
        INNER JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    cards = cur.rowcount or 0
    cur.execute(
        """
        DELETE sr
        FROM sResults.ShowResults sr
        INNER JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    results = cur.rowcount or 0
    cur.execute("DELETE FROM sResults.ShowClass WHERE ShowListID = ?", show_list_id)
    classes = cur.rowcount or 0
    conn.commit()
    cur.close()
    print_with_timestamp(
        f"Wiped show {show_list_id}: cards={cards} results={results} classes={classes}"
    )


def hso_recapture(
    conn,
    driver,
    show_list_id: int,
    show_guid: str,
    year: Optional[int],
    show_name: str,
    archive_class_details: bool = True,
):
    count, driver = scrape_class_results_for_show(
        driver,
        show_list_id,
        show_guid,
        year,
        show_name,
        conn,
        show_class_ids=None,
        use_direct_url=True,
        sleep_short=0.3,
        sleep_medium=0.5,
        sleep_long=1,
        prefer_hso_identity=True,
        archive_class_details=archive_class_details,
    )
    print_with_timestamp(f"HSO recapture show {show_list_id}: saved/enriched={count}")
    return count, driver


def _entries_set(rows: List[Dict[str, Any]], key: str = "Entry") -> Set[str]:
    out: Set[str] = set()
    for r in rows:
        e = r.get(key)
        if e is not None and str(e).strip():
            out.add(str(e).strip())
    return out


def build_shr_sides(snapshot: Dict[str, Any]) -> List[ClassSide]:
    by_name: Dict[str, Dict[str, Any]] = {}
    for card in snapshot.get("judge_cards") or []:
        name = (card.get("ClassName") or "").strip()
        if not name:
            continue
        bucket = by_name.setdefault(
            name,
            {"class_id": card.get("ShrClassID"), "entries": card.get("Entries"), "entry_nums": set()},
        )
        if card.get("Entry"):
            bucket["entry_nums"].add(str(card["Entry"]).strip())
    for row in snapshot.get("blank_results") or []:
        name = (row.get("ClassName") or "").strip()
        if not name:
            continue
        bucket = by_name.setdefault(
            name,
            {"class_id": row.get("ShrClassID"), "entries": row.get("Entries"), "entry_nums": set()},
        )
        if row.get("Entry"):
            bucket["entry_nums"].add(str(row["Entry"]).strip())
    sides = []
    for name, meta in by_name.items():
        sides.append(
            ClassSide(
                class_id=int(meta["class_id"]) if meta.get("class_id") is not None else None,
                class_name=name,
                entries_count=int(meta["entries"]) if meta.get("entries") is not None else None,
                entry_numbers=meta["entry_nums"] or set(),
            )
        )
    return sides


def build_hso_sides(conn, show_list_id: int) -> List[ClassSide]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sc.ID, sc.Class, sc.ClassName, sc.Entries
        FROM sResults.ShowClass sc
        WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    classes = cur.fetchall()
    sides: List[ClassSide] = []
    for cid, cnum, cname, entries in classes:
        cur.execute(
            """
            SELECT Entry FROM sResults.ShowResults
            WHERE ShowClassID = ? AND Entry IS NOT NULL AND LTRIM(RTRIM(Entry)) <> ''
            """,
            cid,
        )
        entry_nums = {str(r[0]).strip() for r in cur.fetchall() if r[0]}
        sides.append(
            ClassSide(
                class_id=int(cid),
                class_name=cname or "",
                class_num=cnum,
                entries_count=int(entries) if entries is not None else None,
                entry_numbers=entry_nums,
            )
        )
    cur.close()
    return sides


def reattach_judges(conn, show_list_id: int, snapshot: Dict[str, Any]) -> Tuple[int, str]:
    shr_sides = build_shr_sides(snapshot)
    hso_sides = build_hso_sides(conn, show_list_id)
    matches, un_shr, un_hso = match_classes(shr_sides, hso_sides)
    report = os.path.join(SNAPSHOT_ROOT, f"show_{show_list_id}_class_match.csv")
    write_match_report(report, matches, un_shr, un_hso)
    print_with_timestamp(
        f"Class match {show_list_id}: matched={len(matches)} "
        f"unmatched_shr={len(un_shr)} unmatched_hso={len(un_hso)} report={report}"
    )

    name_to_hso_id = {m.shr.class_name: m.hso.class_id for m in matches if m.hso.class_id}

    # Judge name -> ID
    cur = conn.cursor()
    cur.execute(
        "SELECT ID, JudgeName FROM sResults.ShowJudge WHERE ShowListID = ?",
        show_list_id,
    )
    judge_ids = {name: jid for jid, name in cur.fetchall()}

    attached = 0
    missing_class = 0
    missing_result = 0
    for card in snapshot.get("judge_cards") or []:
        shr_name = (card.get("ClassName") or "").strip()
        hso_class_id = name_to_hso_id.get(shr_name)
        if not hso_class_id:
            missing_class += 1
            continue
        entry = (card.get("JudgeEntry") or card.get("Entry") or "").strip()
        place = card.get("Place")
        horse = (card.get("HorseName") or "").strip()
        rider = (card.get("Rider") or "").strip()
        result_id = None
        # Prefer JudgeCard.Entry → HSO ShowResults.Entry (who the judge ranked)
        if entry:
            cur.execute(
                """
                SELECT TOP 1 ID FROM sResults.ShowResults
                WHERE ShowClassID = ? AND LTRIM(RTRIM(ISNULL(Entry,''))) = ?
                ORDER BY CASE WHEN Place = ? THEN 0 ELSE 1 END, ID
                """,
                hso_class_id,
                entry,
                place,
            )
            row = cur.fetchone()
            if row:
                result_id = row[0]
        if result_id is None:
            sr_entry = (card.get("Entry") or "").strip()
            if sr_entry and sr_entry != entry:
                cur.execute(
                    """
                    SELECT TOP 1 ID FROM sResults.ShowResults
                    WHERE ShowClassID = ? AND LTRIM(RTRIM(ISNULL(Entry,''))) = ?
                    ORDER BY ID
                    """,
                    hso_class_id,
                    sr_entry,
                )
                row = cur.fetchone()
                if row:
                    result_id = row[0]
        if result_id is None and place is not None:
            cur.execute(
                """
                SELECT TOP 1 sr.ID
                FROM sResults.ShowResults sr
                LEFT JOIN sResults.Horse h ON h.ID = sr.HorseID
                LEFT JOIN sResults.Competitors c ON c.ID = sr.RiderID
                WHERE sr.ShowClassID = ? AND sr.Place = ?
                  AND (
                    (? <> '' AND UPPER(LTRIM(RTRIM(ISNULL(h.HorseName,'')))) = UPPER(?))
                    OR (? <> '' AND UPPER(LTRIM(RTRIM(ISNULL(c.Rider,'')))) = UPPER(?))
                    OR (? = '' AND ? = '')
                  )
                """,
                hso_class_id,
                place,
                horse,
                horse,
                rider,
                rider,
                horse,
                rider,
            )
            row = cur.fetchone()
            if row:
                result_id = row[0]
        if result_id is None:
            missing_result += 1
            continue
        jname = (card.get("JudgeName") or "").strip()
        jid = judge_ids.get(jname)
        if jid is None:
            cur.execute(
                """
                INSERT INTO sResults.ShowJudge (ShowListID, JudgeName)
                OUTPUT INSERTED.ID VALUES (?, ?)
                """,
                show_list_id,
                jname,
            )
            jid = cur.fetchone()[0]
            judge_ids[jname] = jid
            conn.commit()
        cur.execute(
            """
            SELECT ID FROM sResults.ShowResults_JudgeCard
            WHERE ShowResultsID = ? AND ShowJudgeID = ?
            """,
            result_id,
            jid,
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO sResults.ShowResults_JudgeCard (ShowResultsID, ShowJudgeID, Entry, Place)
            VALUES (?, ?, ?, ?)
            """,
            result_id,
            jid,
            entry or None,
            card.get("JudgePlace"),
        )
        attached += 1
    conn.commit()
    cur.close()
    print_with_timestamp(
        f"Reattached judges {show_list_id}: attached={attached} "
        f"missing_class={missing_class} missing_result={missing_result}"
    )
    return attached, report


def verify_show(conn, show_list_id: int) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          COUNT(*) AS classes,
          SUM(CASE WHEN NULLIF(LTRIM(RTRIM(Class)),'') IS NULL THEN 1 ELSE 0 END) AS blank,
          SUM(CASE WHEN ISNULL(Entries,0)>0 THEN 1 ELSE 0 END) AS with_entries
        FROM sResults.ShowClass WHERE ShowListID = ?
        """,
        show_list_id,
    )
    print_with_timestamp(f"Verify classes {show_list_id}: {cur.fetchone()}")
    cur.execute(
        """
        SELECT COUNT(*) FROM sResults.ShowResults sr
        JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    results = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COUNT(*) FROM sResults.ShowResults_JudgeCard jc
        JOIN sResults.ShowResults sr ON sr.ID = jc.ShowResultsID
        JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    cards = cur.fetchone()[0]
    print_with_timestamp(f"Verify results={results} judgecards={cards}")
    cur.close()


def rebuild_one(
    conn,
    driver,
    show_list_id: int,
    show_guid: str,
    year: Optional[int],
    show_name: str,
    shr_show_id: Optional[str] = None,
    snapshot_only: bool = False,
    wipe_only: bool = False,
    judges_only: bool = False,
    skip_recapture: bool = False,
    no_class_archives: bool = False,
):
    log_import_activity(
        conn,
        "rebuild_merged_show_hso_first.py",
        action="START_SHOW",
        additional_info=f"ShowListID={show_list_id}",
    )
    if judges_only:
        # Prefer on-disk SHR archives; fall back to snapshot
        arch = reload_archives_for_show(
            conn, show_list_id, str(shr_show_id or ""), year=year
        )
        if arch.get("attached", 0) == 0:
            snap = load_snapshot(show_list_id)
            reattach_judges(conn, show_list_id, snap)
        verify_show(conn, show_list_id)
        return driver

    snap = snapshot_judge_cards(conn, show_list_id)
    if snapshot_only:
        return driver

    wipe_show_classes_and_results(conn, show_list_id)
    if wipe_only:
        return driver

    if not skip_recapture:
        _, driver = hso_recapture(
            conn,
            driver,
            show_list_id,
            show_guid,
            year,
            show_name,
            archive_class_details=not no_class_archives,
        )

    # After each HSO rebuild: reload judges/cards from SHR archives (Entry-aware)
    arch = reload_archives_for_show(
        conn, show_list_id, str(shr_show_id or ""), year=year
    )
    if arch.get("attached", 0) == 0:
        # Single-HPS / empty archive / no file — try pre-wipe snapshot
        print_with_timestamp(
            f"  Archive attach=0 for {show_list_id}; falling back to snapshot reattach"
        )
        reattach_judges(conn, show_list_id, snap)
    verify_show(conn, show_list_id)
    log_import_activity(
        conn,
        "rebuild_merged_show_hso_first.py",
        action="COMPLETE_SHOW",
        additional_info=f"ShowListID={show_list_id}",
    )
    return driver


def main() -> None:
    parser = argparse.ArgumentParser(description="HSO-first rebuild for merged shows")
    parser.add_argument("--show-list-id", type=int)
    parser.add_argument("--skip-show-list-id", type=int, action="append", default=[])
    parser.add_argument("--apply-all", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--snapshot-only", action="store_true")
    parser.add_argument("--wipe-only", action="store_true")
    parser.add_argument("--judges-only", action="store_true")
    parser.add_argument("--skip-recapture", action="store_true")
    parser.add_argument("--no-class-archives", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    if not args.show_list_id and not args.apply_all:
        parser.error("Provide --show-list-id or --apply-all")

    conn = get_db_connection()
    shows = list_merged_shows(
        conn,
        show_list_id=args.show_list_id,
        skip_ids=args.skip_show_list_id or None,
        limit=args.limit,
    )
    if not shows:
        print_with_timestamp("No shows selected")
        conn.close()
        return

    print_with_timestamp(f"Shows to rebuild: {len(shows)}")
    need_driver = not (args.snapshot_only or args.wipe_only or args.judges_only or args.skip_recapture)
    driver = setup_driver(headless=not args.headed) if need_driver else None
    try:
        for idx, (sl_id, guid, year, name, shr_id) in enumerate(shows, 1):
            print_with_timestamp(
                f"\n[{idx}/{len(shows)}] Rebuild ShowListID={sl_id} SHR={shr_id} '{name}'"
            )
            try:
                driver = rebuild_one(
                    conn,
                    driver,
                    sl_id,
                    guid,
                    year,
                    name,
                    shr_show_id=shr_id,
                    snapshot_only=args.snapshot_only,
                    wipe_only=args.wipe_only,
                    judges_only=args.judges_only,
                    skip_recapture=args.skip_recapture,
                    no_class_archives=args.no_class_archives,
                )
            except Exception as e:
                print_with_timestamp(f"  [ERROR] {e}")
                import traceback

                traceback.print_exc()
                try:
                    conn.rollback()
                except Exception:
                    pass
            time.sleep(0.3)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        conn.close()
    print_with_timestamp("Done.")


if __name__ == "__main__":
    main()