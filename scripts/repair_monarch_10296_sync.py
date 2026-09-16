"""One-shot: undo unsafe Entry-only blank-class trainer sync on Monarch (10296)."""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrape_class_results import get_db_connection, print_with_timestamp
from recapture_merged_hso_shows import revert_unsafe_blank_trainer_sync


def backfill_blank_entries(conn, show_list_id: int) -> int:
    """Set Entries on blank-Class rows to result count so export is not 'out of 0'."""
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE sc
            SET sc.Entries = x.cnt,
                sc.Placings = CASE
                    WHEN ISNULL(sc.Placings, 0) > 0 THEN sc.Placings
                    ELSE x.placed END,
                sc.UpdatedDate = GETDATE()
            FROM sResults.ShowClass sc
            INNER JOIN (
                SELECT sr.ShowClassID,
                       COUNT(*) AS cnt,
                       SUM(CASE WHEN ISNULL(sr.Place, 0) > 0 THEN 1 ELSE 0 END) AS placed
                FROM sResults.ShowResults sr
                GROUP BY sr.ShowClassID
            ) x ON x.ShowClassID = sc.ID
            WHERE sc.ShowListID = ?
              AND LTRIM(RTRIM(ISNULL(sc.Class, ''))) = ''
              AND ISNULL(sc.Entries, 0) = 0
              AND x.cnt > 0
            """,
            show_list_id,
        )
        n = cur.rowcount or 0
        conn.commit()
        return n
    except Exception as e:
        conn.rollback()
        print_with_timestamp(f"backfill_blank_entries failed: {e}")
        return 0
    finally:
        cur.close()


def main() -> None:
    conn = get_db_connection()
    sl = 10296
    reverted = revert_unsafe_blank_trainer_sync(conn, sl, "2026-09-15 19:00")
    print_with_timestamp(f"Reverted unsafe blank trainers on {sl}: {reverted}")
    filled = backfill_blank_entries(conn, sl)
    print_with_timestamp(f"Backfilled Entries on blank classes: {filled}")

    cur = conn.cursor()
    cur.execute(
        """
        SELECT
          SUM(CASE WHEN ISNULL(sc.Entries,0)=0 AND sr.Place IS NOT NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN NULLIF(LTRIM(RTRIM(sc.Class)),'') IS NULL THEN 1 ELSE 0 END),
          SUM(CASE WHEN sr.TrainerID IS NULL AND NULLIF(LTRIM(RTRIM(sc.Class)),'') IS NULL THEN 1 ELSE 0 END)
        FROM sResults.ShowResults sr
        JOIN sResults.ShowClass sc ON sc.ID = sr.ShowClassID
        WHERE sc.ShowListID = ?
        """,
        sl,
    )
    print_with_timestamp(f"After: place_out_of_0, blank_result_rows, blank_null_trainer = {cur.fetchone()}")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
