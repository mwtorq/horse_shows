"""
Rescrape HorseShowsOnline ClassResults to restore ShowClass.Entries (and related
summary fields) for classes that lost HSO entry-count data after SHR merges.

Also archives each ClassResults page under horseshowsonline/{year}/results/.

Usage:
  python scripts/rescrape_hso_entries.py --dry-run
  python scripts/rescrape_hso_entries.py --apply
  python scripts/rescrape_hso_entries.py --apply --year 2025
  python scripts/rescrape_hso_entries.py --apply --show-list-id 10296
  python scripts/rescrape_hso_entries.py --apply --limit 10
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from hso_archive import save_hso_driver_page  # noqa: E402
from scrape_class_results import (  # noqa: E402
    get_column_indices_for_class_grid,
    get_db_connection,
    log_import_activity,
    print_with_timestamp,
    setup_driver,
)


def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = value.strip().upper()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def similarity(a: str, b: str) -> float:
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def normalize_class_name(value: Optional[str]) -> str:
    """Normalize class titles for HSO↔SHR compare."""
    if not value:
        return ""
    text = value.strip().upper()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " AND ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    stop = {
        "THE", "A", "AN", "AND", "OF", "AT", "TO", "FOR",
        "ASB", "AHA", "USEF", "UPHA", "AHHS", "AMHA",
        "OPEN", "MONARCH", "CHAMPIONSHIP", "CHAMP", "CLASS",
        "HORSE", "PONY", "SECTION", "SEC", "DIVISION", "DIV",
    }
    tokens = [t for t in text.split() if t not in stop]
    return " ".join(tokens)


def class_name_similarity(a: Optional[str], b: Optional[str]) -> float:
    na, nb = normalize_class_name(a), normalize_class_name(b)
    if not na or not nb:
        return similarity(a or "", b or "")
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    if not ta or not tb:
        return seq
    inter = ta & tb
    if not inter:
        return seq
    jaccard = len(inter) / len(ta | tb)
    # Containment: shorter name's tokens mostly inside longer
    containment = len(inter) / min(len(ta), len(tb))
    return max(seq, jaccard, containment)


def normalize_class_key(class_num: Optional[str], class_name: Optional[str]) -> str:
    return f"{normalize_text(class_num)}|{normalize_text(class_name)}"


def list_shows_needing_entries(
    conn,
    year: Optional[int] = None,
    show_list_id: Optional[int] = None,
    limit: Optional[int] = None,
) -> List[Tuple[int, str, Optional[int], str, int]]:
    """
    Shows that lost HSO entry counts in the SHR merge:

    - Have both ShowGUID (can re-hit HSO) and SHRShowID (were merged)
    - Still have ShowClass rows with Entries = 0 that either have results
      (typical SHR insert with blank Class) or a non-empty Class number
    """
    cur = conn.cursor()
    sql = """
        SELECT sl.ID, sl.ShowGUID, sl.Year, sl.ShowName, COUNT(*) AS MissingEntries
        FROM sResults.ShowList sl
        INNER JOIN sResults.ShowClass sc ON sc.ShowListID = sl.ID
        WHERE sl.ShowGUID IS NOT NULL AND LTRIM(RTRIM(sl.ShowGUID)) <> ''
          AND sl.SHRShowID IS NOT NULL AND LTRIM(RTRIM(sl.SHRShowID)) <> ''
          AND ISNULL(sc.Entries, 0) = 0
          AND (
                LTRIM(RTRIM(ISNULL(sc.Class, ''))) <> ''
                OR EXISTS (
                    SELECT 1 FROM sResults.ShowResults sr
                    WHERE sr.ShowClassID = sc.ID
                )
              )
    """
    params: List[Any] = []
    if year is not None:
        sql += " AND sl.Year = ?"
        params.append(year)
    if show_list_id is not None:
        sql += " AND sl.ID = ?"
        params.append(show_list_id)
    sql += """
        GROUP BY sl.ID, sl.ShowGUID, sl.Year, sl.ShowName
        ORDER BY sl.Year DESC, sl.ID
    """
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    result = [
        (int(r[0]), str(r[1]), int(r[2]) if r[2] is not None else None, r[3] or "", int(r[4] or 0))
        for r in rows
    ]
    if limit is not None:
        result = result[:limit]
    return result


def load_db_classes(conn, show_list_id: int) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT ID, Class, ClassName, ClassType, DivisionName, Entries, Placings
        FROM sResults.ShowClass
        WHERE ShowListID = ?
        """,
        show_list_id,
    )
    rows = []
    for r in cur.fetchall():
        rows.append(
            {
                "ID": r[0],
                "Class": (r[1] or "").strip(),
                "ClassName": (r[2] or "").strip(),
                "ClassType": (r[3] or "").strip() if r[3] else "",
                "DivisionName": (r[4] or "").strip() if r[4] else "",
                "Entries": int(r[5]) if r[5] is not None else 0,
                "Placings": int(r[6]) if r[6] is not None else 0,
            }
        )
    cur.close()
    return rows


def find_best_db_class(
    db_classes: List[Dict[str, Any]],
    class_num: str,
    class_name: str,
    used_ids: set,
) -> Optional[Dict[str, Any]]:
    candidates = [c for c in db_classes if c["ID"] not in used_ids]
    if not candidates:
        return None

    def rank(c: Dict[str, Any]) -> Tuple[int, int, int]:
        # Prefer rows that need Entries, then rows that already hold results
        # (SHR inserts often have blank Class), then rows with a Class number.
        needs = 1 if c["Entries"] == 0 else 0
        blank_class = 1 if not c["Class"] else 0
        return (needs, blank_class, 1 if c["Class"] else 0)

    # 1) Exact Class + ClassName
    key = normalize_class_key(class_num, class_name)
    exact = [
        c
        for c in candidates
        if normalize_class_key(c["Class"], c["ClassName"]) == key and key != "|"
    ]
    if exact:
        return sorted(exact, key=rank, reverse=True)[0]

    # 2) Exact ClassName (case-insensitive)
    name_hits = [
        c
        for c in candidates
        if normalize_text(c["ClassName"]) == normalize_text(class_name) and class_name
    ]
    if name_hits:
        same_num = [
            c for c in name_hits if normalize_text(c["Class"]) == normalize_text(class_num)
        ]
        pool = same_num or name_hits
        return sorted(pool, key=rank, reverse=True)[0]

    # 3) Exact Class number if unique among needing-Entries / blank-Class rows
    if class_num:
        num_hits = [
            c
            for c in candidates
            if normalize_text(c["Class"]) == normalize_text(class_num) and c["Class"]
        ]
        if len(num_hits) == 1:
            return num_hits[0]
        needing = [c for c in num_hits if c["Entries"] == 0]
        if len(needing) == 1:
            return needing[0]

    # 4) Fuzzy ClassName — strongly prefer Entries=0 / blank Class (SHR orphans)
    best, best_score = None, 0.0
    for c in candidates:
        score = class_name_similarity(class_name, c["ClassName"])
        if class_num and normalize_text(c["Class"]) == normalize_text(class_num):
            score = min(1.0, score + 0.05)
        if c["Entries"] == 0:
            score = min(1.0, score + 0.03)
        if not c["Class"]:
            score = min(1.0, score + 0.02)
        if score > best_score:
            best_score, best = score, c
    if best and best_score >= 0.82:
        return best
    return None


def stamp_entries_on_siblings(
    cur,
    show_list_id: int,
    class_num: str,
    class_name: str,
    entries: int,
    placings: int,
    exclude_id: int,
    db_classes: List[Dict[str, Any]],
    dry_run: bool,
) -> int:
    """Fill Entries on other classes in the show that match this HSO class name."""
    if entries <= 0 or not class_name:
        return 0
    sibling_ids = []
    for c in db_classes:
        if c["ID"] == exclude_id or c["Entries"] > 0:
            continue
        score = class_name_similarity(class_name, c["ClassName"])
        if score >= 0.82 or normalize_text(c["ClassName"]) == normalize_text(class_name):
            sibling_ids.append(c["ID"])
            c["Entries"] = entries
            if not c["Class"] and class_num:
                c["Class"] = class_num
    if not sibling_ids or dry_run:
        return len(sibling_ids)
    for sid in sibling_ids:
        cur.execute(
            """
            UPDATE sResults.ShowClass
            SET Entries = ?,
                Class = CASE WHEN LTRIM(RTRIM(ISNULL(Class,''))) = '' THEN ? ELSE Class END,
                Placings = CASE WHEN ISNULL(Placings,0) = 0 AND ? > 0 THEN ? ELSE Placings END,
                UpdatedDate = GETDATE()
            WHERE ID = ? AND ShowListID = ? AND ISNULL(Entries, 0) = 0
            """,
            entries,
            class_num[:50] if class_num else "",
            placings,
            placings,
            sid,
            show_list_id,
        )
    return len(sibling_ids)


def parse_int(value: str, default: int = 0) -> int:
    value = (value or "").strip()
    if value.isdigit():
        return int(value)
    return default


def extract_class_summaries_from_grid(driver) -> List[Dict[str, str]]:
    grid = None
    try:
        grid = driver.find_element(By.CSS_SELECTOR, "table[id*='grMaster']")
    except Exception:
        grids = driver.find_elements(By.CSS_SELECTOR, "table.dxgvTable")
        grid = grids[0] if grids else None
    if grid is None:
        raise RuntimeError("ClassResults grid not found")

    column_map = get_column_indices_for_class_grid(grid)
    rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DXDataRow'], tr.dxgvDataRow")
    summaries: List[Dict[str, str]] = []
    exclude = [
        "copyright",
        "all rights reserved",
        "privacy policy",
        "terms of service",
        "horseshowsonline",
        "timeslice",
    ]

    for row in rows:
        try:
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            if not cells:
                continue
            summary = {
                "Class": "",
                "Class Name": "",
                "Class Type": "",
                "Division Name": "",
                "Entries": "",
                "Placings": "",
            }
            for field, idx in column_map.items():
                if idx is not None and idx < len(cells):
                    summary[field] = cells[idx].text.strip()
            class_text = summary["Class"].lower()
            name_text = summary["Class Name"].lower()
            if any(x in (class_text + " " + name_text) for x in exclude):
                continue
            if not summary["Class"] and not summary["Class Name"]:
                continue
            entries = summary["Entries"].strip()
            if entries and not entries.isdigit():
                continue
            if not entries:
                summary["Entries"] = "0"
            if not summary["Placings"].strip():
                summary["Placings"] = "0"
            summaries.append(summary)
        except Exception:
            continue
    return summaries


def apply_summary_to_db(
    conn,
    show_list_id: int,
    summary: Dict[str, str],
    db_classes: List[Dict[str, Any]],
    used_ids: set,
    dry_run: bool,
) -> str:
    class_num = summary.get("Class", "").strip()
    class_name = summary.get("Class Name", "").strip()
    class_type = summary.get("Class Type", "").strip()
    division = summary.get("Division Name", "").strip()
    entries = parse_int(summary.get("Entries", "0"))
    placings = parse_int(summary.get("Placings", "0"))

    match = find_best_db_class(db_classes, class_num, class_name, used_ids)
    cur = conn.cursor()
    try:
        if match:
            used_ids.add(match["ID"])
            sets = []
            params: List[Any] = []
            # Always take HSO Entries when DB is 0/NULL; never overwrite a higher
            # existing Entries with a lower HSO value unless DB was 0.
            if match["Entries"] == 0 or entries > match["Entries"]:
                if entries != match["Entries"]:
                    sets.append("Entries = ?")
                    params.append(entries)
            if match["Placings"] == 0 and placings > 0:
                sets.append("Placings = ?")
                params.append(placings)
            if class_num and not match["Class"]:
                sets.append("Class = ?")
                params.append(class_num[:50])
            if class_name and (
                not match["ClassName"]
                or similarity(class_name, match["ClassName"]) >= 0.97
            ):
                # Prefer longer/more complete HSO name when nearly identical
                if len(class_name) >= len(match["ClassName"] or ""):
                    sets.append("ClassName = ?")
                    params.append(class_name[:500])
            if class_type and not match["ClassType"]:
                sets.append("ClassType = ?")
                params.append(class_type[:200])
            if division and not match["DivisionName"]:
                sets.append("DivisionName = ?")
                params.append(division[:200])

            if not sets:
                sib = stamp_entries_on_siblings(
                    cur,
                    show_list_id,
                    class_num,
                    class_name,
                    entries,
                    placings,
                    match["ID"],
                    db_classes,
                    dry_run,
                )
                if sib:
                    return (
                        f"SKIP id={match['ID']} '{class_num}' '{class_name[:40]}' "
                        f"(already current; +{sib} siblings Entries={entries})"
                    )
                return f"SKIP id={match['ID']} '{class_num}' '{class_name[:40]}' (no changes)"

            sets.append("UpdatedDate = GETDATE()")
            params.append(match["ID"])
            action = (
                f"UPDATE id={match['ID']} '{class_num}' '{class_name[:40]}' "
                f"Entries {match['Entries']}->{entries}"
            )
            if dry_run:
                sib = stamp_entries_on_siblings(
                    cur,
                    show_list_id,
                    class_num,
                    class_name,
                    entries,
                    placings,
                    match["ID"],
                    db_classes,
                    dry_run=True,
                )
                if sib:
                    action += f" (+{sib} siblings)"
                return f"WOULD {action}"
            cur.execute(
                f"UPDATE sResults.ShowClass SET {', '.join(sets)} WHERE ID = ?",
                params,
            )
            sib = stamp_entries_on_siblings(
                cur,
                show_list_id,
                class_num,
                class_name,
                entries,
                placings,
                match["ID"],
                db_classes,
                dry_run=False,
            )
            if sib:
                action += f" (+{sib} siblings)"
            if entries >= match["Entries"]:
                match["Entries"] = entries
            return action

        # No match: insert HSO class summary so Entries are retained
        action = f"INSERT '{class_num}' '{class_name[:40]}' Entries={entries}"
        if dry_run:
            return f"WOULD {action}"
        cur.execute(
            """
            INSERT INTO sResults.ShowClass
                (ShowListID, Class, ClassName, ClassType, DivisionName, Entries, Placings)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            show_list_id,
            class_num[:50],
            class_name[:500],
            class_type[:200] or None,
            division[:200] or None,
            entries,
            placings,
        )
        new_id = cur.fetchone()[0]
        db_classes.append(
            {
                "ID": new_id,
                "Class": class_num,
                "ClassName": class_name,
                "ClassType": class_type,
                "DivisionName": division,
                "Entries": entries,
                "Placings": placings,
            }
        )
        used_ids.add(new_id)
        return f"{action} id={new_id}"
    finally:
        cur.close()


def rescrape_show(
    driver,
    conn,
    show_list_id: int,
    show_guid: str,
    year: Optional[int],
    show_name: str,
    dry_run: bool,
    sleep_medium: float = 0.8,
) -> Tuple[int, int]:
    # HSO rejects bare ClassResults links without an active show session.
    # Establish context via ShowDetails first (same pattern as scrape_class_results).
    details_url = f"https://horseshowsonline.com/ShowDetails?ShowGUID={show_guid}"
    print_with_timestamp(f"  Navigating {details_url}")
    driver.get(details_url)
    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "li.dxtc-tab, table[id*='grMaster'], a[href*='ClassResults'], body")
            )
        )
    except TimeoutException:
        time.sleep(sleep_medium)

    try:
        save_hso_driver_page(
            driver,
            year,
            "showdetails",
            show_name or "show",
            show_guid=show_guid,
            extra_id=f"sl{show_list_id}",
        )
    except Exception as archive_err:
        print_with_timestamp(f"  [WARNING] Failed to archive ShowDetails: {archive_err}")

    page_text = (driver.page_source or "").lower()
    if "no show has been selected" in page_text or "invalidshow" in (driver.current_url or "").lower():
        raise RuntimeError(f"HSO session rejected ShowGUID {show_guid} (InvalidShow)")

    url = f"https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}"
    print_with_timestamp(f"  Navigating {url}")
    driver.get(url)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable")
            )
        )
    except TimeoutException:
        time.sleep(sleep_medium * 2)

    # Always archive the page we scraped (even on dry-run — disk evidence)
    save_hso_driver_page(
        driver,
        year,
        "classresults",
        show_name or "show",
        show_guid=show_guid,
        extra_id=f"sl{show_list_id}",
    )

    page_text = (driver.page_source or "").lower()
    if "no show has been selected" in page_text or "invalidshow" in (driver.current_url or "").lower():
        raise RuntimeError(f"HSO session rejected ClassResults for ShowGUID {show_guid}")

    summaries = extract_class_summaries_from_grid(driver)
    print_with_timestamp(f"  Parsed {len(summaries)} HSO class summary rows")
    db_classes = load_db_classes(conn, show_list_id)
    used_ids: set = set()
    updated = 0
    unchanged = 0

    for summary in summaries:
        result = apply_summary_to_db(
            conn, show_list_id, summary, db_classes, used_ids, dry_run=dry_run
        )
        if result.startswith("SKIP"):
            unchanged += 1
        else:
            updated += 1
            print_with_timestamp(f"    {result}")

    if not dry_run:
        conn.commit()
        log_import_activity(
            conn,
            "rescrape_hso_entries.py",
            target_table="ShowClass",
            action="RESTORE_ENTRIES",
            row_count=updated,
            additional_info=(
                f"ShowGUID: {show_guid}, ShowListID: {show_list_id}, "
                f"HSO classes: {len(summaries)}, updated/inserted: {updated}, skip: {unchanged}"
            ),
        )
    return updated, unchanged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rescrape HSO ClassResults to restore ShowClass.Entries"
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Parse and report only (still saves HTML)")
    mode.add_argument("--apply", action="store_true", help="Write Entries updates to the database")
    parser.add_argument("--year", type=int, help="Limit to ShowList.Year")
    parser.add_argument("--show-list-id", type=int, help="Limit to one ShowList.ID")
    parser.add_argument("--limit", type=int, help="Max number of shows to process")
    parser.add_argument("--headed", action="store_true", help="Run browser headed")
    args = parser.parse_args()

    conn = get_db_connection()
    shows = list_shows_needing_entries(
        conn, year=args.year, show_list_id=args.show_list_id, limit=args.limit
    )
    print_with_timestamp(
        f"Shows needing Entries restore: {len(shows)} "
        f"(mode={'dry-run' if args.dry_run else 'apply'})"
    )
    if not shows:
        conn.close()
        return

    driver = setup_driver(headless=not args.headed)
    total_upd = 0
    total_skip = 0
    try:
        for idx, (sl_id, guid, year, name, missing) in enumerate(shows, 1):
            print_with_timestamp(
                f"\n[{idx}/{len(shows)}] ShowListID={sl_id} year={year} "
                f"missing_entries_classes={missing} '{name}'"
            )
            try:
                upd, skip = rescrape_show(
                    driver, conn, sl_id, guid, year, name, dry_run=args.dry_run
                )
                total_upd += upd
                total_skip += skip
            except Exception as e:
                print_with_timestamp(f"  [ERROR] {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
            time.sleep(0.5)
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        conn.close()

    print_with_timestamp(
        f"Done. class updates/inserts={total_upd} skips={total_skip} shows={len(shows)}"
    )


if __name__ == "__main__":
    main()
