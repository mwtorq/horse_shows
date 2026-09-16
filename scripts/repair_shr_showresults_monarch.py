"""
Rebuild Monarch National Championship ShowResults from archived SHR HTML.

Wipes ShowResults + JudgeCards for ShowList 10783, then reloads results and
judge cards using the fixed RiderID / Final-entry merge logic.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional

from bs4 import BeautifulSoup

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from scrape_saddlehorsereport import (  # noqa: E402
    find_or_insert_class,
    get_db_connection,
    get_or_create_competitor,
    get_or_create_horse_fill_nulls,
    get_or_create_show_result,
    parse_judge_card_classes,
    parse_place,
    parse_results_classes,
    parse_show_meta,
    print_with_timestamp,
    upsert_judge_card,
    upsert_judges,
)

SHOW_LIST_ID = 10783
YEAR = 2026
RESULTS_HTML = os.path.join(
    REPO_ROOT,
    "saddlehorsereport",
    "2026",
    "results",
    "debug_shr_results_Monarch_National_Championship_sid18546.html",
)
JUDGES_HTML = os.path.join(
    REPO_ROOT,
    "saddlehorsereport",
    "2026",
    "judges",
    "debug_shr_judges_Monarch_National_Championship_sid18546.html",
)


def load_soup(path: str) -> BeautifulSoup:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return BeautifulSoup(f.read(), "html.parser")


def wipe_show_results(conn, show_list_id: int) -> None:
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
    cards = cur.rowcount
    cur.execute(
        """
        DELETE sr
        FROM sResults.ShowResults sr
        INNER JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        show_list_id,
    )
    results = cur.rowcount
    # Drop empty classes so fuzzy leftovers do not collide on reload
    cur.execute(
        """
        DELETE sc
        FROM sResults.ShowClass sc
        WHERE sc.ShowListID = ?
          AND NOT EXISTS (
              SELECT 1 FROM sResults.ShowResults sr WHERE sr.ShowClassID = sc.ID
          )
        """,
        show_list_id,
    )
    classes = cur.rowcount
    conn.commit()
    cur.close()
    print_with_timestamp(
        f"Wiped cards={cards} results={results} empty_classes={classes}"
    )


def load_results(conn, show_list_id: int, soup: BeautifulSoup) -> int:
    classes = parse_results_classes(soup)
    count = 0
    for cls in classes:
        cname = (cls.get("class_name") or "").strip()
        if not cname:
            continue
        # Skip bogus headers that look like judge name rows
        if cname.upper().startswith("PL ") or cname.upper() in ("PL", "HORSE", "RIDER", "OWNER"):
            continue
        class_id = find_or_insert_class(conn, show_list_id, cname)
        for entry in cls.get("entries") or []:
            horse_name = (entry.get("horse") or "").strip()
            if not horse_name:
                continue
            details: Dict[str, Optional[str]] = {"owner": entry.get("owner")}
            horse_id = get_or_create_horse_fill_nulls(conn, horse_name, details)
            rider_id = get_or_create_competitor(conn, entry.get("rider") or "", "Rider")
            if entry.get("owner"):
                get_or_create_competitor(conn, entry["owner"], "Owner")
            rid = get_or_create_show_result(
                conn,
                class_id,
                None,
                parse_place(entry.get("place")),
                horse_id,
                rider_id=rider_id,
            )
            if rid:
                count += 1
    return count


def load_judges(conn, show_list_id: int, soup: BeautifulSoup) -> int:
    meta = parse_show_meta(soup)
    judge_map = upsert_judges(conn, show_list_id, meta.get("judges") or [])
    class_cards = parse_judge_card_classes(soup)
    count = 0
    for block in class_cards:
        cname = (block.get("class_name") or "").strip()
        if not cname or cname.upper().startswith("PL "):
            continue
        class_id = find_or_insert_class(conn, show_list_id, cname)
        for card in block.get("cards") or []:
            jname = card["judge_name"]
            if jname not in judge_map:
                judge_map.update(
                    upsert_judges(
                        conn,
                        show_list_id,
                        [{"name": jname, "role": None, "sort_order": None}],
                    )
                )
            entry_num = (card.get("entry") or "").strip() or None
            final_num = (card.get("final") or "").strip() or None
            judge_place = card.get("place")
            official_place = (
                judge_place if (entry_num and final_num and entry_num == final_num) else None
            )
            result_id = get_or_create_show_result(
                conn,
                class_id,
                entry_num or final_num,
                official_place,
                None,
            )
            if result_id and jname in judge_map:
                upsert_judge_card(
                    conn,
                    result_id,
                    judge_map[jname],
                    judge_place,
                    entry=entry_num,
                )
                count += 1
            if final_num and final_num != entry_num and judge_place is not None:
                get_or_create_show_result(
                    conn,
                    class_id,
                    final_num,
                    judge_place,
                    None,
                )    return count


def main() -> None:
    conn = get_db_connection()
    wipe_show_results(conn, SHOW_LIST_ID)

    results_soup = load_soup(RESULTS_HTML)
    n_results = load_results(conn, SHOW_LIST_ID, results_soup)
    print_with_timestamp(f"Loaded result rows={n_results}")

    judges_soup = load_soup(JUDGES_HTML)
    n_cards = load_judges(conn, SHOW_LIST_ID, judges_soup)
    print_with_timestamp(f"Loaded judge-card writes={n_cards}")

    cur = conn.cursor()
    cur.execute(
        """
        SELECT COUNT(*) total,
         SUM(CASE WHEN HorseID IS NULL THEN 1 ELSE 0 END) no_horse,
         SUM(CASE WHEN RiderID IS NULL THEN 1 ELSE 0 END) no_rider,
         SUM(CASE WHEN Entry IS NULL OR Entry = '' THEN 1 ELSE 0 END) no_entry
        FROM sResults.ShowResults sr
        JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        SHOW_LIST_ID,
    )
    stats = cur.fetchone()
    cur.execute(
        "SELECT COUNT(*) FROM sResults.ShowClass WHERE ShowListID = ?",
        SHOW_LIST_ID,
    )
    n_classes = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COUNT(*) FROM sResults.ShowResults_JudgeCard jc
        JOIN sResults.ShowResults sr ON sr.ID = jc.ShowResultsID
        JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        SHOW_LIST_ID,
    )
    n_jc = cur.fetchone()[0]
    cur.close()
    conn.close()
    print_with_timestamp(
        f"Final: classes={n_classes} results={stats[0]} "
        f"no_horse={stats[1]} no_rider={stats[2]} no_entry={stats[3]} "
        f"judge_cards={n_jc}"
    )


if __name__ == "__main__":
    main()
