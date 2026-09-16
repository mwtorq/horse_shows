"""
Add ShowResults_JudgeCard.Entry (before Place) and reload all judge cards
from archived SHR judges HTML under saddlehorsereport/{year}/judges/.

Entry is the entry number that judge ranked at Place (from the judge column),
so HSO ShowResults can be joined on Entry.

Usage:
  python scripts/reload_judgecards_from_archives.py --dry-run
  python scripts/reload_judgecards_from_archives.py --apply
  python scripts/reload_judgecards_from_archives.py --apply --year 2026
  python scripts/reload_judgecards_from_archives.py --apply --sid 18546
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hso_shr_class_match import ClassSide, class_name_similarity, match_classes  # noqa: E402
from scrape_saddlehorsereport import (  # noqa: E402
    ensure_schema,
    find_or_insert_class,
    get_db_connection,
    get_or_create_show_result,
    parse_judge_card_classes,
    parse_show_meta,
    print_with_timestamp,
    upsert_judge_card,
    upsert_judges,
)

SHR_ROOT = os.path.join(REPO_ROOT, "saddlehorsereport")


def ensure_entry_column_ordered(conn) -> None:
    """
    Ensure Entry exists immediately before Place by rebuilding the table if needed.
    """
    ensure_schema(conn)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COLUMN_NAME, ORDINAL_POSITION
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA='sResults' AND TABLE_NAME='ShowResults_JudgeCard'
        ORDER BY ORDINAL_POSITION
        """
    )
    cols = [r[0] for r in cur.fetchall()]
    if "Entry" in cols:
        # If Entry exists but not before Place, rebuild
        if cols.index("Entry") < cols.index("Place"):
            cur.close()
            print_with_timestamp("Entry column already present before Place")
            return
        print_with_timestamp("Entry exists but not before Place; rebuilding table order...")
    else:
        print_with_timestamp("Adding Entry column (rebuild for column order)...")

    cur.execute(
        """
        IF OBJECT_ID('sResults.ShowResults_JudgeCard_new', 'U') IS NOT NULL
            DROP TABLE sResults.ShowResults_JudgeCard_new;

        CREATE TABLE sResults.ShowResults_JudgeCard_new (
            ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            ShowResultsID INT NOT NULL,
            ShowJudgeID INT NOT NULL,
            Entry NVARCHAR(50) NULL,
            Place INT NULL,
            CreatedDate DATETIME NOT NULL
                CONSTRAINT DF_ShowResults_JudgeCard_CreatedDate_new DEFAULT GETDATE(),
            UpdatedDate DATETIME NULL,
            CONSTRAINT FK_JudgeCard_ShowResults_new FOREIGN KEY (ShowResultsID)
                REFERENCES sResults.ShowResults(ID),
            CONSTRAINT FK_JudgeCard_ShowJudge_new FOREIGN KEY (ShowJudgeID)
                REFERENCES sResults.ShowJudge(ID)
        );

        SET IDENTITY_INSERT sResults.ShowResults_JudgeCard_new ON;
        INSERT INTO sResults.ShowResults_JudgeCard_new
            (ID, ShowResultsID, ShowJudgeID, Entry, Place, CreatedDate, UpdatedDate)
        SELECT
            ID, ShowResultsID, ShowJudgeID,
            CASE WHEN COL_LENGTH('sResults.ShowResults_JudgeCard', 'Entry') IS NOT NULL
                 THEN Entry ELSE NULL END,
            Place, CreatedDate, UpdatedDate
        FROM sResults.ShowResults_JudgeCard;
        SET IDENTITY_INSERT sResults.ShowResults_JudgeCard_new OFF;

        -- Drop old FKs/indexes by dropping table
        DROP TABLE sResults.ShowResults_JudgeCard;
        EXEC sp_rename 'sResults.ShowResults_JudgeCard_new', 'ShowResults_JudgeCard';
        EXEC sp_rename 'sResults.DF_ShowResults_JudgeCard_CreatedDate_new',
             'DF_ShowResults_JudgeCard_CreatedDate';
        EXEC sp_rename 'sResults.FK_JudgeCard_ShowResults_new', 'FK_JudgeCard_ShowResults';
        EXEC sp_rename 'sResults.FK_JudgeCard_ShowJudge_new', 'FK_JudgeCard_ShowJudge';

        CREATE UNIQUE INDEX UX_JudgeCard_Result_Judge
            ON sResults.ShowResults_JudgeCard(ShowResultsID, ShowJudgeID);
        CREATE INDEX IX_JudgeCard_ShowJudgeID ON sResults.ShowResults_JudgeCard(ShowJudgeID);
        CREATE INDEX IX_JudgeCard_Entry ON sResults.ShowResults_JudgeCard(Entry);
        """
    )
    # The CASE WHEN COL_LENGTH in INSERT may fail if Entry doesn't exist yet —
    # use a safer two-path approach in Python instead.
    conn.rollback()
    cur.close()

    cur = conn.cursor()
    has_entry = "Entry" in cols
    cur.execute(
        """
        IF OBJECT_ID('sResults.ShowResults_JudgeCard_new', 'U') IS NOT NULL
            DROP TABLE sResults.ShowResults_JudgeCard_new;

        CREATE TABLE sResults.ShowResults_JudgeCard_new (
            ID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            ShowResultsID INT NOT NULL,
            ShowJudgeID INT NOT NULL,
            Entry NVARCHAR(50) NULL,
            Place INT NULL,
            CreatedDate DATETIME NOT NULL
                CONSTRAINT DF_ShowResults_JudgeCard_CreatedDate_new DEFAULT GETDATE(),
            UpdatedDate DATETIME NULL
        );
        """
    )
    conn.commit()
    if has_entry:
        cur.execute(
            """
            SET IDENTITY_INSERT sResults.ShowResults_JudgeCard_new ON;
            INSERT INTO sResults.ShowResults_JudgeCard_new
                (ID, ShowResultsID, ShowJudgeID, Entry, Place, CreatedDate, UpdatedDate)
            SELECT ID, ShowResultsID, ShowJudgeID, Entry, Place, CreatedDate, UpdatedDate
            FROM sResults.ShowResults_JudgeCard;
            SET IDENTITY_INSERT sResults.ShowResults_JudgeCard_new OFF;
            """
        )
    else:
        cur.execute(
            """
            SET IDENTITY_INSERT sResults.ShowResults_JudgeCard_new ON;
            INSERT INTO sResults.ShowResults_JudgeCard_new
                (ID, ShowResultsID, ShowJudgeID, Entry, Place, CreatedDate, UpdatedDate)
            SELECT ID, ShowResultsID, ShowJudgeID, NULL, Place, CreatedDate, UpdatedDate
            FROM sResults.ShowResults_JudgeCard;
            SET IDENTITY_INSERT sResults.ShowResults_JudgeCard_new OFF;
            """
        )
    conn.commit()
    cur.execute("DROP TABLE sResults.ShowResults_JudgeCard")
    conn.commit()
    cur.execute("EXEC sp_rename 'sResults.ShowResults_JudgeCard_new', 'ShowResults_JudgeCard'")
    conn.commit()
    # Recreate constraints/indexes
    for sql in (
        """
        ALTER TABLE sResults.ShowResults_JudgeCard ADD CONSTRAINT
            DF_ShowResults_JudgeCard_CreatedDate DEFAULT GETDATE() FOR CreatedDate
        """,
        """
        ALTER TABLE sResults.ShowResults_JudgeCard WITH CHECK ADD CONSTRAINT
            FK_JudgeCard_ShowResults FOREIGN KEY (ShowResultsID)
            REFERENCES sResults.ShowResults(ID)
        """,
        """
        ALTER TABLE sResults.ShowResults_JudgeCard WITH CHECK ADD CONSTRAINT
            FK_JudgeCard_ShowJudge FOREIGN KEY (ShowJudgeID)
            REFERENCES sResults.ShowJudge(ID)
        """,
        """
        CREATE UNIQUE INDEX UX_JudgeCard_Result_Judge
            ON sResults.ShowResults_JudgeCard(ShowResultsID, ShowJudgeID)
        """,
        """
        CREATE INDEX IX_JudgeCard_ShowJudgeID ON sResults.ShowResults_JudgeCard(ShowJudgeID)
        """,
        """
        CREATE INDEX IX_JudgeCard_Entry ON sResults.ShowResults_JudgeCard(Entry)
        """,
    ):
        try:
            cur.execute(sql)
            conn.commit()
        except Exception as e:
            print_with_timestamp(f"  [WARNING] post-rebuild DDL: {e}")
            conn.rollback()
    cur.close()
    print_with_timestamp("ShowResults_JudgeCard rebuilt with Entry before Place")


def list_judge_archives(
    year: Optional[int] = None, sid: Optional[str] = None
) -> List[Tuple[int, str, str]]:
    """Return (year, sid, path) for each judges HTML archive."""
    out: List[Tuple[int, str, str]] = []
    years = [year] if year else None
    root_years = []
    if years:
        root_years = [os.path.join(SHR_ROOT, str(year), "judges")]
    else:
        if not os.path.isdir(SHR_ROOT):
            return out
        for name in sorted(os.listdir(SHR_ROOT)):
            if name.isdigit():
                root_years.append(os.path.join(SHR_ROOT, name, "judges"))
    for jdir in root_years:
        if not os.path.isdir(jdir):
            continue
        y = int(os.path.basename(os.path.dirname(jdir)))
        for fn in os.listdir(jdir):
            if not fn.lower().endswith(".html"):
                continue
            if fn.lower().endswith("_raw.txt"):
                continue
            m = re.search(r"sid(\d+)", fn, re.I)
            if not m:
                continue
            this_sid = m.group(1)
            if sid and this_sid != str(sid):
                continue
            out.append((y, this_sid, os.path.join(jdir, fn)))
    return out


def find_show_list_ids(conn, shr_id: str) -> List[int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ID FROM sResults.ShowList
        WHERE SHRShowID = ?
        ORDER BY CASE WHEN ShowGUID IS NOT NULL AND LTRIM(RTRIM(ShowGUID)) <> '' THEN 0 ELSE 1 END, ID
        """,
        shr_id,
    )
    ids = [int(r[0]) for r in cur.fetchall()]
    cur.close()
    return ids


def wipe_judge_cards_for_show(conn, show_list_id: int) -> int:
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
    n = cur.rowcount or 0
    conn.commit()
    cur.close()
    return n


def load_hso_class_sides(conn, show_list_id: int) -> List[ClassSide]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT sc.ID, sc.Class, sc.ClassName, sc.Entries
        FROM sResults.ShowClass sc WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    sides = []
    for cid, cnum, cname, entries in cur.fetchall():
        cur.execute(
            """
            SELECT Entry FROM sResults.ShowResults
            WHERE ShowClassID = ? AND Entry IS NOT NULL AND LTRIM(RTRIM(Entry)) <> ''
            """,
            cid,
        )
        ents = {str(r[0]).strip() for r in cur.fetchall() if r[0]}
        sides.append(
            ClassSide(
                class_id=int(cid),
                class_name=cname or "",
                class_num=cnum,
                entries_count=int(entries) if entries is not None else None,
                entry_numbers=ents,
            )
        )
    cur.close()
    return sides


def find_result_id(
    conn,
    show_class_id: int,
    entry: Optional[str],
    place: Optional[int],
) -> Optional[int]:
    cur = conn.cursor()
    if entry:
        cur.execute(
            """
            SELECT TOP 1 ID FROM sResults.ShowResults
            WHERE ShowClassID = ? AND LTRIM(RTRIM(ISNULL(Entry,''))) = ?
            ORDER BY CASE WHEN Place = ? THEN 0 ELSE 1 END, ID
            """,
            show_class_id,
            str(entry).strip(),
            place,
        )
        row = cur.fetchone()
        if row:
            cur.close()
            return int(row[0])
    # Fallback: create/attach by entry+place via helper
    cur.close()
    return get_or_create_show_result(conn, show_class_id, entry, place, None)


def reload_one_archive(
    conn,
    year: int,
    sid: str,
    path: str,
    dry_run: bool,
    only_show_list_id: Optional[int] = None,
) -> Dict[str, int]:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    meta = parse_show_meta(soup)
    blocks = parse_judge_card_classes(soup)
    show_ids = find_show_list_ids(conn, sid)
    if only_show_list_id is not None:
        show_ids = [i for i in show_ids if i == int(only_show_list_id)]
    stats = {
        "blocks": len(blocks),
        "cards_parsed": sum(len(b.get("cards") or []) for b in blocks),
        "shows": len(show_ids),
        "wiped": 0,
        "attached": 0,
        "skipped": 0,
    }
    if not show_ids:
        print_with_timestamp(f"  [SKIP] no ShowList for SHR sid={sid} ({os.path.basename(path)})")
        return stats

    judge_names = meta.get("judges") or []
    # Also collect judge names from cards
    for b in blocks:
        for c in b.get("cards") or []:
            jn = (c.get("judge_name") or "").strip()
            if jn and not any((j.get("name") or "").strip() == jn for j in judge_names):
                judge_names.append({"name": jn, "role": None, "sort_order": None})

    for show_list_id in show_ids:
        if dry_run:
            print_with_timestamp(
                f"  WOULD reload sid={sid} show={show_list_id} "
                f"blocks={stats['blocks']} cards={stats['cards_parsed']} "
                f"file={os.path.basename(path)}"
            )
            continue

        wiped = wipe_judge_cards_for_show(conn, show_list_id)
        stats["wiped"] += wiped
        judge_map = upsert_judges(conn, show_list_id, judge_names)

        # Prefer matching onto existing HSO numbered classes when present
        hso_sides = load_hso_class_sides(conn, show_list_id)
        shr_sides = [
            ClassSide(
                class_id=None,
                class_name=b["class_name"],
                entry_numbers={
                    str(c.get("entry")).strip()
                    for c in (b.get("cards") or [])
                    if c.get("entry")
                },
            )
            for b in blocks
            if b.get("class_name")
        ]
        matches, _, _ = match_classes(shr_sides, hso_sides, min_score=0.72)
        name_to_class_id = {m.shr.class_name: m.hso.class_id for m in matches if m.hso.class_id}

        for block in blocks:
            cname = (block.get("class_name") or "").strip()
            if not cname:
                continue
            class_id = name_to_class_id.get(cname)
            if class_id is None:
                # On HSO-primary shows (numbered classes exist), do not create SHR blank orphans
                has_numbered = any(
                    (s.class_num or "").strip() for s in hso_sides
                )
                if has_numbered:
                    stats["skipped"] += len(block.get("cards") or [])
                    continue
                class_id = find_or_insert_class(conn, show_list_id, cname)
            for card in block.get("cards") or []:
                jname = (card.get("judge_name") or "").strip()
                if not jname:
                    stats["skipped"] += 1
                    continue
                if jname not in judge_map:
                    judge_map.update(
                        upsert_judges(
                            conn,
                            show_list_id,
                            [{"name": jname, "role": None, "sort_order": None}],
                        )
                    )
                entry = (card.get("entry") or "").strip() or None
                final = (card.get("final") or "").strip() or None
                judge_place = card.get("place")
                # Link to the judge's Entry row (not Final) so per-judge places differ
                result_id = find_result_id(
                    conn, class_id, entry or final, None
                )
                if entry and final and entry == final and judge_place is not None:
                    # Stamp official Final place on this entry's result
                    get_or_create_show_result(
                        conn, class_id, entry, judge_place, None
                    )
                    result_id = find_result_id(conn, class_id, entry, None) or result_id
                if not result_id or jname not in judge_map:
                    stats["skipped"] += 1
                    continue
                upsert_judge_card(
                    conn,
                    result_id,
                    judge_map[jname],
                    judge_place,
                    entry=entry,
                )
                stats["attached"] += 1
                if final and final != entry and judge_place is not None:
                    get_or_create_show_result(
                        conn, class_id, final, judge_place, None
                    )
        print_with_timestamp(
            f"  Reloaded sid={sid} show={show_list_id} wiped={wiped} "
            f"attached={stats['attached']} skipped={stats['skipped']} "
            f"({meta.get('show_name') or os.path.basename(path)})"
        )
    return stats


def reload_archives_for_show(
    conn,
    show_list_id: int,
    shr_id: str,
    year: Optional[int] = None,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Reload JudgeCards for one ShowList from SHR judges HTML archives."""
    totals = {
        "archives": 0,
        "attached": 0,
        "wiped": 0,
        "cards_parsed": 0,
        "skipped": 0,
        "blocks": 0,
    }
    if not shr_id:
        print_with_timestamp(f"  No SHRShowID for show {show_list_id}; skip archive reload")
        return totals

    archives = list_judge_archives(year=year, sid=str(shr_id))
    if not archives:
        archives = list_judge_archives(sid=str(shr_id))
    totals["archives"] = len(archives)
    if not archives:
        print_with_timestamp(
            f"  No SHR judge archive for sid={shr_id} (show {show_list_id})"
        )
        return totals

    for y, sid, path in archives:
        st = reload_one_archive(
            conn,
            y,
            sid,
            path,
            dry_run=dry_run,
            only_show_list_id=show_list_id,
        )
        for k in ("attached", "wiped", "cards_parsed", "skipped", "blocks"):
            totals[k] += st.get(k, 0)
    print_with_timestamp(
        f"  Archive judge reload show={show_list_id} sid={shr_id}: "
        f"archives={totals['archives']} parsed={totals['cards_parsed']} "
        f"attached={totals['attached']} skipped={totals['skipped']}"
    )
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description="Reload JudgeCards with Entry from SHR archives")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--year", type=int)
    parser.add_argument("--sid", type=str)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--schema-only", action="store_true")
    args = parser.parse_args()
    dry_run = args.dry_run or not args.apply

    conn = get_db_connection()
    ensure_entry_column_ordered(conn)
    if args.schema_only:
        conn.close()
        return

    archives = list_judge_archives(year=args.year, sid=args.sid)
    if args.limit:
        archives = archives[: args.limit]
    print_with_timestamp(f"Judge archives to reload: {len(archives)} (dry_run={dry_run})")

    totals = {"attached": 0, "wiped": 0, "cards_parsed": 0, "skipped": 0}
    for year, sid, path in archives:
        try:
            st = reload_one_archive(conn, year, sid, path, dry_run=dry_run)
            for k in totals:
                totals[k] += st.get(k, 0)
        except Exception as e:
            print_with_timestamp(f"  [ERROR] sid={sid} {path}: {e}")
            import traceback

            traceback.print_exc()
            try:
                conn.rollback()
            except Exception:
                pass
    print_with_timestamp(f"Done. totals={totals}")
    conn.close()


if __name__ == "__main__":
    main()
