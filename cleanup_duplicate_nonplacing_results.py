"""
Remove duplicate non-placing rows (Place = 0) from sResults.ShowResults.

These are rows written twice by scrape_class_results.py between 2026-01-25 and 2026-01-28:
same class, same entry number, same horse, rider and trainer, and identical in every payload
column, inserted in the same batch with consecutive IDs. The pre-insert duplicate check in
save_show_result_to_database did not see the sibling row.

A row is only a duplicate here if it matches another row of the same class on EVERY column
except ID, CreatedDate and UpdatedDate. That is deliberately strict: a handful of classes
legitimately list one entry number against two different horses or riders, and those rows
differ on HorseID or RiderID, so they are never selected. The oldest row of each group is
kept.

Dry run by default. Pass --apply to delete.

    python cleanup_duplicate_nonplacing_results.py
    python cleanup_duplicate_nonplacing_results.py --apply
    python cleanup_duplicate_nonplacing_results.py --apply --batch-size 500

Do not run with --apply while a scraper is active. Deletes are batched and committed
separately so an interrupted run leaves the table consistent and can simply be re-run, but a
concurrent scraper counts Place = 0 rows to decide whether a class is complete, and removing
rows underneath it can make a class it is working on look short.
"""

import sys

from scrape_class_results import get_db_connection, print_with_timestamp

# Every column that carries scraped data. Rows matching on all of these are the same row.
PAYLOAD_PARTITION = """
    ShowClassID, ISNULL(Entry, ''), ISNULL(HorseID, -1), ISNULL(RiderID, -1),
    ISNULL(TrainerID, -1), ISNULL(Country, ''), ISNULL(Prize, ''), ISNULL(AddBack, ''),
    ISNULL(Start, ''), ISNULL(Score, ''), ISNULL([Percent], ''), ISNULL(USEF, ''), ISNULL(EC, '')
"""

DUPLICATE_IDS = f"""
    SELECT ID, ShowClassID
    FROM (
        SELECT ID, ShowClassID,
               ROW_NUMBER() OVER (PARTITION BY {PAYLOAD_PARTITION} ORDER BY ID) AS RowNum
        FROM sResults.ShowResults
        WHERE Place = 0
    ) ranked
    WHERE RowNum > 1
"""


def report(conn):
    """Read-only summary of what --apply would remove"""
    cursor = conn.cursor()

    cursor.execute(f"""
        SELECT COUNT(*) AS Removable, COUNT(DISTINCT ShowClassID) AS ClassesAffected
        FROM ({DUPLICATE_IDS}) d
    """)
    removable, classes = cursor.fetchone()
    print_with_timestamp(f"  Rows to delete:            {removable}")
    print_with_timestamp(f"  Classes affected:          {classes}")

    cursor.execute("""
        SELECT COUNT(*) FROM sResults.ShowResults WITH (NOLOCK) WHERE Place = 0
    """)
    print_with_timestamp(f"  Non-placing rows in total: {cursor.fetchone()[0]}")

    cursor.execute(f"""
        SELECT CAST(r.CreatedDate AS DATE) AS Day, COUNT(*) AS Rows_
        FROM sResults.ShowResults r WITH (NOLOCK)
        JOIN ({DUPLICATE_IDS}) d ON d.ID = r.ID
        GROUP BY CAST(r.CreatedDate AS DATE)
        ORDER BY 1
    """)
    print_with_timestamp("  By creation date:")
    for day, count in cursor.fetchall():
        print_with_timestamp(f"    {day}  {count}")

    # Rows kept per group must still be at least one, and classes already marked complete are
    # not re-queued by this, but a class can drop below Entries - Placings once the extra copy
    # is gone. Worth knowing before running.
    cursor.execute(f"""
        SELECT COUNT(*) FROM (
            SELECT sc.ID
            FROM sResults.ShowClass sc WITH (NOLOCK)
            JOIN (SELECT ShowClassID, COUNT(*) AS Removing FROM ({DUPLICATE_IDS}) d
                  GROUP BY ShowClassID) x ON x.ShowClassID = sc.ID
            JOIN (SELECT ShowClassID, COUNT(*) AS NP FROM sResults.ShowResults WITH (NOLOCK)
                  WHERE Place = 0 GROUP BY ShowClassID) ec ON ec.ShowClassID = sc.ID
            WHERE sc.Entries IS NOT NULL AND sc.Placings IS NOT NULL
              AND (ec.NP - x.Removing) < (sc.Entries - sc.Placings)
              AND ec.NP >= (sc.Entries - sc.Placings)
        ) y
    """)
    print_with_timestamp(f"  Classes that fall below Entries - Placings afterwards: {cursor.fetchone()[0]}")

    cursor.execute(f"""
        SELECT TOP 10 r.ShowClassID, r.Entry, r.HorseID, r.RiderID, r.ID AS DeletingID,
               (SELECT MIN(k.ID) FROM sResults.ShowResults k WITH (NOLOCK)
                WHERE k.ShowClassID = r.ShowClassID AND k.Place = 0
                  AND ISNULL(k.Entry,'') = ISNULL(r.Entry,'')
                  AND ISNULL(k.HorseID,-1) = ISNULL(r.HorseID,-1)) AS KeepingID
        FROM sResults.ShowResults r WITH (NOLOCK)
        JOIN ({DUPLICATE_IDS}) d ON d.ID = r.ID
        ORDER BY r.ShowClassID, r.ID
    """)
    rows = cursor.fetchall()
    if rows:
        print_with_timestamp("  Sample (ShowClassID, Entry, HorseID, RiderID, deleting, keeping):")
        for r in rows:
            print_with_timestamp(f"    {r[0]}, {r[1]}, {r[2]}, {r[3]}, delete ID {r[4]}, keep ID {r[5]}")

    cursor.close()
    return removable


def delete_duplicates(conn, batch_size):
    cursor = conn.cursor()
    cursor.execute(f"SELECT ID FROM ({DUPLICATE_IDS}) d ORDER BY ID")
    ids = [row[0] for row in cursor.fetchall()]
    cursor.close()

    print_with_timestamp(f"  Deleting {len(ids)} rows in batches of {batch_size}...")
    deleted = 0
    for start in range(0, len(ids), batch_size):
        batch = ids[start:start + batch_size]
        placeholders = ','.join('?' * len(batch))
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"DELETE FROM sResults.ShowResults WHERE Place = 0 AND ID IN ({placeholders})",
                *batch)
            conn.commit()
            deleted += cursor.rowcount
            print_with_timestamp(f"    {deleted}/{len(ids)}")
        except Exception as e:
            conn.rollback()
            print_with_timestamp(f"    [ERROR] Batch starting at {start} failed, rolled back: {e}")
            raise
        finally:
            cursor.close()
    return deleted


def main(apply_changes=False, batch_size=1000):
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("Duplicate non-placing result cleanup" + ("" if apply_changes else " (DRY RUN)"))
    print_with_timestamp("=" * 60 + "\n")

    conn = get_db_connection()
    try:
        removable = report(conn)
        if not apply_changes:
            print_with_timestamp("\n  Dry run only. Re-run with --apply to delete these rows.")
            return
        if not removable:
            print_with_timestamp("\n  Nothing to delete.")
            return
        deleted = delete_duplicates(conn, batch_size)
        print_with_timestamp(f"\n  Deleted {deleted} rows. Re-checking...")
        report(conn)
    finally:
        conn.close()
        print_with_timestamp("\n[OK] Database connection closed")


if __name__ == '__main__':
    apply_changes = False
    batch_size = 1000

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i].lower()
        if arg == '--apply':
            apply_changes = True
        elif arg == '--batch-size':
            if i + 1 >= len(sys.argv):
                print_with_timestamp("[ERROR] --batch-size requires a value")
                sys.exit(1)
            batch_size = int(sys.argv[i + 1])
            i += 1
        elif arg in ('--help', '-h'):
            print(__doc__)
            sys.exit(0)
        else:
            print_with_timestamp(f"[ERROR] Unknown argument: {sys.argv[i]}")
            sys.exit(1)
        i += 1

    main(apply_changes=apply_changes, batch_size=batch_size)
