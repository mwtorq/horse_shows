"""
Insert all archive.org discovered ShowGUIDs into the database
Only inserts if not already present
"""

import pyodbc
from datetime import datetime

# Read all GUIDs from file
with open('2014_showguids_archive.txt', 'r') as f:
    guids = [line.strip() for line in f if line.strip()]

print(f"Loaded {len(guids)} GUIDs from file")

# Connect to database
try:
    conn = pyodbc.connect(
        'DRIVER={SQL Server};'
        'SERVER=localhost;'
        'DATABASE=HorseShows;'
        'Trusted_Connection=yes;'
        'TrustServerCertificate=yes'
    )
    cursor = conn.cursor()
    print("Connected to database")
    
    # Check which GUIDs already exist
    print("\nChecking for existing GUIDs...")
    cursor.execute("""
        SELECT ShowGUID 
        FROM sResults.ShowList 
        WHERE Year = 2014
    """)
    existing_guids = set(row[0].lower() for row in cursor.fetchall())
    print(f"Found {len(existing_guids)} existing 2014 shows in database")
    
    # Filter to new GUIDs only
    new_guids = [g for g in guids if g.lower() not in existing_guids]
    print(f"\n{len(new_guids)} new GUIDs to insert")
    
    if len(new_guids) == 0:
        print("All GUIDs already exist in database!")
        conn.close()
        exit(0)
    
    # Insert new GUIDs
    print("\nInserting new GUIDs...")
    inserted = 0
    skipped = 0
    
    for i, guid in enumerate(new_guids):
        try:
            # Check once more if it exists (in case of duplicates in file)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM sResults.ShowList 
                WHERE ShowGUID = ?
            """, guid)
            
            if cursor.fetchone()[0] > 0:
                skipped += 1
                continue
            
            # Insert with minimal data - scraper will fill in details later
            cursor.execute("""
                INSERT INTO sResults.ShowList (Year, ShowGUID, ShowName, ShowDate)
                VALUES (?, ?, ?, ?)
            """, 2014, guid, f'2014 Show (Archive) - {guid[:8]}', '2014')
            
            inserted += 1
            
            if (i + 1) % 50 == 0:
                print(f"  Progress: {i + 1}/{len(new_guids)} processed, {inserted} inserted")
                conn.commit()  # Commit in batches
        
        except Exception as e:
            print(f"  Error inserting {guid}: {e}")
            skipped += 1
    
    # Final commit
    conn.commit()
    
    print(f"\n{'='*80}")
    print(f"COMPLETE")
    print(f"{'='*80}")
    print(f"Total GUIDs processed: {len(new_guids)}")
    print(f"Successfully inserted: {inserted}")
    print(f"Skipped/errors: {skipped}")
    
    # Show final count
    cursor.execute("SELECT COUNT(*) FROM sResults.ShowList WHERE Year = 2014")
    total_2014 = cursor.fetchone()[0]
    print(f"\nTotal 2014 shows in database: {total_2014}")
    
    conn.close()
    print("\nDatabase connection closed")

except pyodbc.Error as e:
    print(f"Database error: {e}")
    print("\nNote: If connection fails, you can manually run the SQL script:")
    print("  See: SQL/insert_2014_archive_guids.sql")
