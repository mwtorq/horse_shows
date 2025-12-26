"""
Script to find and fix classes incorrectly associated with the wrong show
This addresses issues from when show name matching was too lenient (partial matches)
"""

import pyodbc
from datetime import datetime
import sys

def print_with_timestamp(message, end='\n'):
    """Print message with timestamp prefix"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", end=end)

def get_db_connection():
    """Get SQL Server database connection"""
    drivers = [
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 18 for SQL Server',
        'SQL Server',
        'SQL Server Native Client 11.0',
    ]
    
    for driver in drivers:
        try:
            conn_str = f'DRIVER={{{driver}}};SERVER=localhost\\SQLEXPRESS;DATABASE=HorseShows;Trusted_Connection=yes;'
            conn = pyodbc.connect(conn_str)
            print_with_timestamp(f"[OK] Connected to HorseShows database using driver: {driver}")
            return conn
        except Exception as e:
            if driver == drivers[-1]:  # Last driver
                print_with_timestamp(f"[ERROR] Database connection failed with all drivers: {e}")
                raise
            continue

def find_incorrect_associations(conn, dry_run=True):
    """Find classes that are incorrectly associated with shows
    
    Args:
        conn: Database connection
        dry_run: If True, only report issues without fixing them
    
    Returns:
        List of tuples (show_class_id, show_list_id, show_guid, show_name, class_num, class_name, issue_description)
    """
    issues = []
    
    try:
        cursor = conn.cursor()
        
        # Query to find potential mismatches
        # We'll check classes where the ShowGUID doesn't match what we'd expect
        # or where the show name doesn't match exactly
        
        print_with_timestamp("Analyzing ShowClass associations...")
        
        # Get all ShowClass records with their associated ShowList data
        cursor.execute("""
            SELECT 
                sc.ID AS ShowClassID,
                sc.ShowListID,
                sc.Class,
                sc.ClassName,
                sl.ID AS ShowListID_Actual,
                sl.ShowGUID,
                sl.ShowName,
                sl.Year
            FROM sResults.ShowClass sc
            INNER JOIN sResults.ShowList sl ON sc.ShowListID = sl.ID
            ORDER BY sl.Year DESC, sl.ShowName, sc.Class
        """)
        
        all_classes = cursor.fetchall()
        print_with_timestamp(f"Found {len(all_classes)} total class records")
        
        # Group classes by ShowGUID to find duplicates or mismatches
        show_guid_map = {}  # ShowGUID -> list of (ShowListID, ShowName, Year)
        for row in all_classes:
            show_guid = row[5]  # ShowGUID
            show_list_id = row[4]  # ShowListID_Actual
            show_name = row[6]  # ShowName
            year = row[7]  # Year
            
            if show_guid:
                if show_guid not in show_guid_map:
                    show_guid_map[show_guid] = []
                show_guid_map[show_guid].append((show_list_id, show_name, year))
        
        # Find ShowGUIDs that appear in multiple ShowList records (potential duplicates)
        duplicate_guids = {guid: shows for guid, shows in show_guid_map.items() if len(shows) > 1}
        
        if duplicate_guids:
            print_with_timestamp(f"Found {len(duplicate_guids)} ShowGUIDs associated with multiple shows (potential duplicates)")
        
        # Check for classes that might be incorrectly associated
        # Strategy: Look for classes where the show name pattern doesn't match
        # or where there are multiple shows with similar names in the same year
        
        print_with_timestamp("Checking for incorrect associations...")
        
        # Find shows with similar names in the same year (potential mismatches)
        cursor.execute("""
            SELECT 
                sl1.ID AS ShowListID1,
                sl1.ShowName AS ShowName1,
                sl1.ShowGUID AS ShowGUID1,
                sl2.ID AS ShowListID2,
                sl2.ShowName AS ShowName2,
                sl2.ShowGUID AS ShowGUID2,
                sl1.Year
            FROM sResults.ShowList sl1
            INNER JOIN sResults.ShowList sl2 
                ON sl1.Year = sl2.Year 
                AND sl1.ID < sl2.ID
                AND (
                    -- One show name contains the other (e.g., "II" vs "III")
                    sl1.ShowName LIKE sl2.ShowName + '%'
                    OR sl2.ShowName LIKE sl1.ShowName + '%'
                    OR sl1.ShowName LIKE '%' + sl2.ShowName
                    OR sl2.ShowName LIKE '%' + sl1.ShowName
                )
            WHERE sl1.ShowGUID IS NOT NULL 
                AND sl1.ShowGUID != ''
                AND sl2.ShowGUID IS NOT NULL 
                AND sl2.ShowGUID != ''
            ORDER BY sl1.Year DESC, sl1.ShowName
        """)
        
        similar_shows = cursor.fetchall()
        
        if similar_shows:
            print_with_timestamp(f"Found {len(similar_shows)} pairs of shows with similar names (potential source of confusion)")
            
            # For each pair, check if classes might be mis-assigned
            for row in similar_shows:
                show_list_id1 = row[0]
                show_name1 = row[1]
                show_guid1 = row[2]
                show_list_id2 = row[3]
                show_name2 = row[4]
                show_guid2 = row[5]
                year = row[6]
                
                # Get classes for both shows
                cursor.execute("""
                    SELECT ID, Class, ClassName, ShowListID
                    FROM sResults.ShowClass
                    WHERE ShowListID IN (?, ?)
                    ORDER BY Class
                """, show_list_id1, show_list_id2)
                
                classes = cursor.fetchall()
                
                # Check if there are duplicate class numbers/names across the two shows
                # This would indicate potential mis-assignment
                class_numbers = {}
                for class_row in classes:
                    class_num = class_row[1]  # Class
                    class_name = class_row[2]  # ClassName
                    show_list_id = class_row[3]  # ShowListID
                    
                    key = (class_num, class_name)
                    if key not in class_numbers:
                        class_numbers[key] = []
                    class_numbers[key].append((class_row[0], show_list_id))
                
                # Find classes that appear in both shows (definite issue)
                duplicate_classes = {k: v for k, v in class_numbers.items() if len(v) > 1}
                
                if duplicate_classes:
                    print_with_timestamp(f"\n  [ISSUE] Shows '{show_name1}' and '{show_name2}' (Year {year}) have duplicate classes:")
                    for (class_num, class_name), occurrences in duplicate_classes.items():
                        print_with_timestamp(f"    Class {class_num}: {class_name[:50]}")
                        for show_class_id, show_list_id in occurrences:
                            actual_show = show_name1 if show_list_id == show_list_id1 else show_name2
                            issues.append((
                                show_class_id,
                                show_list_id,
                                show_guid1 if show_list_id == show_list_id1 else show_guid2,
                                actual_show,
                                class_num,
                                class_name,
                                f"Duplicate class found in both '{show_name1}' and '{show_name2}'"
                            ))
        
        # Also check for classes where the show name doesn't match the expected pattern
        # This is harder to detect automatically, so we'll flag classes in shows with similar names
        
        cursor.close()
        
        return issues
        
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error finding incorrect associations: {e}")
        import traceback
        traceback.print_exc()
        return []

def find_classes_by_show_guid(conn, show_guid):
    """Find all classes associated with a specific ShowGUID"""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sc.ID, sc.Class, sc.ClassName, sc.ShowListID, sl.ShowName, sl.Year
            FROM sResults.ShowClass sc
            INNER JOIN sResults.ShowList sl ON sc.ShowListID = sl.ID
            WHERE sl.ShowGUID = ?
            ORDER BY sc.Class
        """, show_guid)
        return cursor.fetchall()
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error finding classes by ShowGUID: {e}")
        return []

def remove_incorrect_associations(conn, issues, confirm=True):
    """Remove classes that are incorrectly associated
    
    Args:
        conn: Database connection
        issues: List of issues from find_incorrect_associations
        confirm: If True, ask for confirmation before deleting
    
    Returns:
        Number of classes removed
    """
    if not issues:
        print_with_timestamp("No issues to fix")
        return 0
    
    print_with_timestamp(f"\nFound {len(issues)} potential issues")
    
    if confirm:
        print_with_timestamp("\nIssues to be removed:")
        for show_class_id, show_list_id, show_guid, show_name, class_num, class_name, issue_desc in issues:
            print_with_timestamp(f"  ShowClassID {show_class_id}: Class {class_num} - {class_name[:50]}")
            print_with_timestamp(f"    Show: {show_name} (ShowGUID: {show_guid})")
            print_with_timestamp(f"    Issue: {issue_desc}")
        
        response = input("\nDo you want to DELETE these classes? (yes/no): ").strip().lower()
        if response != 'yes':
            print_with_timestamp("Cancelled by user")
            return 0
    
    try:
        cursor = conn.cursor()
        removed_count = 0
        
        for show_class_id, show_list_id, show_guid, show_name, class_num, class_name, issue_desc in issues:
            try:
                # First, delete associated ShowResults
                cursor.execute("""
                    DELETE FROM sResults.ShowResults
                    WHERE ShowClassID = ?
                """, show_class_id)
                results_deleted = cursor.rowcount
                
                # Then delete the ShowClass
                cursor.execute("""
                    DELETE FROM sResults.ShowClass
                    WHERE ID = ?
                """, show_class_id)
                
                if cursor.rowcount > 0:
                    removed_count += 1
                    print_with_timestamp(f"  [OK] Removed ShowClassID {show_class_id} (Class {class_num}) and {results_deleted} associated results")
                
            except Exception as e:
                print_with_timestamp(f"  [ERROR] Error removing ShowClassID {show_class_id}: {e}")
                conn.rollback()
                continue
        
        conn.commit()
        cursor.close()
        print_with_timestamp(f"\n[OK] Removed {removed_count} incorrectly associated classes")
        return removed_count
        
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error removing associations: {e}")
        conn.rollback()
        import traceback
        traceback.print_exc()
        return 0

def remap_classes_to_correct_show(conn, issues, dry_run=True):
    """Attempt to remap classes to the correct show
    
    Args:
        conn: Database connection
        issues: List of issues from find_incorrect_associations
        dry_run: If True, only show what would be remapped
    
    Returns:
        Number of classes remapped
    """
    if not issues:
        print_with_timestamp("No issues to remap")
        return 0
    
    print_with_timestamp(f"\nAttempting to remap {len(issues)} classes...")
    print_with_timestamp("[NOTE] Remapping is complex and requires manual verification")
    print_with_timestamp("This feature is not fully implemented - use removal instead")
    
    # TODO: Implement remapping logic
    # This would require:
    # 1. Finding the correct ShowListID for each class
    # 2. Updating ShowClass.ShowListID
    # 3. Verifying the remapping is correct
    
    return 0

def main(dry_run=True, action='report'):
    """Main function
    
    Args:
        dry_run: If True, only report issues without fixing
        action: 'report', 'remove', or 'remap'
    """
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("Fix Incorrect Show Associations")
    print_with_timestamp("=" * 60 + "\n")
    
    conn = None
    
    try:
        # Connect to database
        conn = get_db_connection()
        
        # Find issues
        issues = find_incorrect_associations(conn, dry_run=dry_run)
        
        if not issues:
            print_with_timestamp("\n[OK] No incorrect associations found")
            return
        
        # Report issues
        print_with_timestamp(f"\n{'='*60}")
        print_with_timestamp(f"Found {len(issues)} potential issues")
        print_with_timestamp(f"{'='*60}\n")
        
        # Group by show for better reporting
        issues_by_show = {}
        for issue in issues:
            show_class_id, show_list_id, show_guid, show_name, class_num, class_name, issue_desc = issue
            key = (show_list_id, show_name, show_guid)
            if key not in issues_by_show:
                issues_by_show[key] = []
            issues_by_show[key].append(issue)
        
        print_with_timestamp("Issues grouped by show:\n")
        for (show_list_id, show_name, show_guid), show_issues in issues_by_show.items():
            print_with_timestamp(f"Show: {show_name} (ShowListID: {show_list_id}, ShowGUID: {show_guid})")
            print_with_timestamp(f"  {len(show_issues)} potentially incorrect classes:")
            for show_class_id, _, _, _, class_num, class_name, issue_desc in show_issues:
                print_with_timestamp(f"    - ShowClassID {show_class_id}: Class {class_num} - {class_name[:60]}")
                print_with_timestamp(f"      Issue: {issue_desc}")
            print_with_timestamp("")
        
        # Take action based on mode
        if action == 'remove':
            if dry_run:
                print_with_timestamp("\n[DRY RUN] Would remove classes (use --execute to actually remove)")
            else:
                removed = remove_incorrect_associations(conn, issues, confirm=True)
                print_with_timestamp(f"\nRemoved {removed} classes")
        elif action == 'remap':
            if dry_run:
                print_with_timestamp("\n[DRY RUN] Would remap classes (remapping not fully implemented)")
            else:
                remapped = remap_classes_to_correct_show(conn, issues, dry_run=False)
                print_with_timestamp(f"\nRemapped {remapped} classes")
        else:
            print_with_timestamp("\n[REPORT MODE] No changes made")
            print_with_timestamp("Use --remove to remove incorrect associations")
            print_with_timestamp("Use --remap to attempt remapping (not fully implemented)")
        
    except Exception as e:
        print_with_timestamp(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            try:
                conn.close()
                print_with_timestamp("\n[OK] Database connection closed")
            except:
                pass

if __name__ == '__main__':
    import sys
    
    dry_run = True
    action = 'report'
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i].lower()
        
        if arg in ['--execute', '--no-dry-run']:
            dry_run = False
            print_with_timestamp("[INFO] Execute mode: Changes will be made")
        elif arg in ['--remove', '--delete']:
            action = 'remove'
            print_with_timestamp("[INFO] Action: Remove incorrect associations")
        elif arg in ['--remap']:
            action = 'remap'
            print_with_timestamp("[INFO] Action: Remap to correct shows (not fully implemented)")
        elif arg in ['--help', '-h']:
            print_with_timestamp("Usage: python fix_incorrect_show_associations.py [OPTIONS]")
            print_with_timestamp("\nOptions:")
            print_with_timestamp("  --execute, --no-dry-run: Actually make changes (default is dry-run)")
            print_with_timestamp("  --remove, --delete: Remove incorrectly associated classes")
            print_with_timestamp("  --remap: Attempt to remap classes to correct shows (not fully implemented)")
            print_with_timestamp("  --help, -h: Show this help message")
            print_with_timestamp("\nExamples:")
            print_with_timestamp("  python fix_incorrect_show_associations.py")
            print_with_timestamp("    # Report issues only (dry-run)")
            print_with_timestamp("  python fix_incorrect_show_associations.py --remove")
            print_with_timestamp("    # Show what would be removed (dry-run)")
            print_with_timestamp("  python fix_incorrect_show_associations.py --remove --execute")
            print_with_timestamp("    # Actually remove incorrect associations")
            sys.exit(0)
        
        i += 1
    
    main(dry_run=dry_run, action=action)


