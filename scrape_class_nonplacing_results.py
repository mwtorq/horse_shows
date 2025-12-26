"""
Scraper to collect non-placing entry results data for classes where Entries > Placings
Navigates to ClassResults page and captures entries from the "Non placing entries" grid
Saves to sResults.ShowResults table with Place = 0
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, InvalidSessionIdException
import time
import pyodbc
from datetime import datetime

# Import necessary functions from scrape_class_results.py
from scrape_class_results import (
    setup_driver,
    get_db_connection,
    print_with_timestamp,
    activate_shows_by_year_tab,
    select_year,
    find_and_click_show_row,
    activate_class_results_tab,
    get_column_indices_for_class_grid,
    get_column_indices_for_entry_grid,
    expand_row,
    collapse_row,
    extract_entry_details_from_row,
    get_or_create_showclass,
    get_or_create_competitor_by_role,
    get_or_create_horse,
    save_show_result_to_database,
    retry_on_stale_element,
    reconnect_browser_and_navigate,
    get_show_list_id_from_guid,
    create_importlog_table_if_not_exists,
    create_showclass_table_if_not_exists,
    log_import_activity
)

def get_classes_with_nonplacing_entries(conn, start_from_show_guid=None):
    """Get classes where Entries > Placings (meaning there are non-placing entries to scrape)
    Only includes classes where the count of existing non-placing results doesn't match the expected count
    
    Args:
        conn: Database connection
        start_from_show_guid: Optional ShowGUID to start from
    
    Returns: List of tuples (show_list_id, show_guid, year, show_name, show_class_id, class_num, class_name, entries, placings)
    """
    try:
        cursor = conn.cursor()
        
        # Get starting ShowListID if ShowGUID provided
        start_from_id = None
        if start_from_show_guid:
            start_from_id = get_show_list_id_from_guid(conn, start_from_show_guid)
            if start_from_id:
                print_with_timestamp(f"[INFO] Starting from ShowGUID {start_from_show_guid} (ShowListID: {start_from_id})")
            else:
                print_with_timestamp(f"[WARNING] ShowGUID {start_from_show_guid} not found, ignoring --start-from parameter")
        
        if start_from_id:
            cursor.execute("""
                SELECT 
                    sl.ID,
                    sl.ShowGUID,
                    sl.Year,
                    sl.ShowName,
                    sc.ID AS ShowClassID,
                    sc.Class,
                    sc.ClassName,
                    sc.Entries,
                    sc.Placings,
                    ISNULL(existing_counts.NonPlacingCount, 0) AS ExistingNonPlacingCount,
                    (sc.Entries - sc.Placings) AS ExpectedNonPlacingCount
                FROM sResults.ShowClass sc
                INNER JOIN sResults.ShowList sl ON sc.ShowListID = sl.ID
                LEFT JOIN (
                    SELECT ShowClassID, COUNT(*) AS NonPlacingCount
                    FROM sResults.ShowResults
                    WHERE Place = 0
                    GROUP BY ShowClassID
                ) existing_counts ON existing_counts.ShowClassID = sc.ID
                WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                AND sl.StartDate IS NOT NULL
                AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
                AND sc.Entries IS NOT NULL
                AND sc.Placings IS NOT NULL
                AND sc.Entries > sc.Placings
                AND sl.ID >= ?
                AND ISNULL(sc.NonPlacingComplete, 0) = 0
                AND ISNULL(existing_counts.NonPlacingCount, 0) < (sc.Entries - sc.Placings)
                ORDER BY sl.ID, sc.ID
            """, start_from_id)
        else:
            cursor.execute("""
                SELECT 
                    sl.ID,
                    sl.ShowGUID,
                    sl.Year,
                    sl.ShowName,
                    sc.ID AS ShowClassID,
                    sc.Class,
                    sc.ClassName,
                    sc.Entries,
                    sc.Placings,
                    ISNULL(existing_counts.NonPlacingCount, 0) AS ExistingNonPlacingCount,
                    (sc.Entries - sc.Placings) AS ExpectedNonPlacingCount
                FROM sResults.ShowClass sc
                INNER JOIN sResults.ShowList sl ON sc.ShowListID = sl.ID
                LEFT JOIN (
                    SELECT ShowClassID, COUNT(*) AS NonPlacingCount
                    FROM sResults.ShowResults
                    WHERE Place = 0
                    GROUP BY ShowClassID
                ) existing_counts ON existing_counts.ShowClassID = sc.ID
                WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                AND sl.StartDate IS NOT NULL
                AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
                AND sc.Entries IS NOT NULL
                AND sc.Placings IS NOT NULL
                AND sc.Entries > sc.Placings
                AND ISNULL(sc.NonPlacingComplete, 0) = 0
                AND ISNULL(existing_counts.NonPlacingCount, 0) < (sc.Entries - sc.Placings)
                ORDER BY sl.ID, sc.ID
            """)
        
        result = []
        skipped_count = 0
        for row in cursor.fetchall():
            show_list_id = row[0]
            show_guid = row[1]
            year = row[2]
            show_name = row[3]
            show_class_id = row[4]
            class_num = row[5]
            class_name = row[6]
            entries = row[7]
            placings = row[8]
            existing_count = row[9]
            expected_count = row[10]
            
            # Double-check: only include if existing count is less than expected
            if existing_count < expected_count:
                result.append((show_list_id, show_guid, year, show_name, show_class_id, class_num, class_name, entries, placings))
            else:
                skipped_count += 1
        
        cursor.close()
        print_with_timestamp(f"[OK] Found {len(result)} classes with Entries > Placings that need non-placing entries scraped")
        if skipped_count > 0:
            print_with_timestamp(f"[OK] Skipped {skipped_count} classes that already have complete non-placing entries")
        return result
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error getting classes with non-placing entries: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_column_indices_for_nonplacing_grid(detail_grid):
    """Determine column indices for non-placing entries grid
    
    Non-placing grid columns:
    Entry, Horse, Rider, Cntry (Country), Owner, Trainer, Prize, Start, Score, Percent, USEF, EC
    
    Returns column map (Place and AddBack will be set to defaults: 0 and '$0.00')
    """
    column_map = {
        'Entry': None,
        'Horse': None,
        'Rider': None,
        'Country': None,  # Maps from Cntry column
        'Owner': None,
        'Trainer': None,
        'Prize': None,
        'Start': None,
        'Score': None,
        'Percent': None,
        'USEF': None,
        'EC': None,
        'Place': None,  # Will be set to 0
        'AddBack': None,  # Will be set to '$0.00'
    }
    
    try:
        # Try to find header row
        header_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='HeaderRow'], tr.dxgvHeaderRow")
        
        if header_rows:
            header_cells = header_rows[0].find_elements(By.TAG_NAME, "th, td")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip().lower()
                
                if 'entry' in cell_text:
                    column_map['Entry'] = idx
                elif 'horse' in cell_text:
                    column_map['Horse'] = idx
                elif 'rider' in cell_text:
                    column_map['Rider'] = idx
                elif 'cntry' in cell_text or 'country' in cell_text:
                    column_map['Country'] = idx
                elif 'owner' in cell_text:
                    column_map['Owner'] = idx
                elif 'trainer' in cell_text:
                    column_map['Trainer'] = idx
                elif 'prize' in cell_text:
                    column_map['Prize'] = idx
                elif 'start' in cell_text:
                    column_map['Start'] = idx
                elif 'score' in cell_text:
                    column_map['Score'] = idx
                elif 'percent' in cell_text:
                    column_map['Percent'] = idx
                elif 'usef' in cell_text:
                    column_map['USEF'] = idx
                elif 'ec' in cell_text and 'cntry' not in cell_text:
                    column_map['EC'] = idx
    except Exception as e:
        pass
    
    # If no mappings found, use default positional mapping based on provided structure:
    # Entry=0, Horse=1, Rider=2, Cntry=3, Owner=4, Trainer=5, Prize=6, Start=7, Score=8, Percent=9, USEF=10, EC=11
    if not any(column_map[k] is not None for k in ['Entry', 'Horse', 'Rider', 'Country', 'Owner', 'Trainer']):
        try:
            data_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
            if data_rows:
                sample_cells = data_rows[0].find_elements(By.TAG_NAME, "td")
                cell_count = len(sample_cells)
                
                # Apply default positional mapping for non-placing entries (12 columns)
                if cell_count >= 12:
                    column_map['Entry'] = 0
                    column_map['Horse'] = 1
                    column_map['Rider'] = 2
                    column_map['Country'] = 3  # Cntry maps to Country
                    column_map['Owner'] = 4
                    column_map['Trainer'] = 5
                    column_map['Prize'] = 6
                    column_map['Start'] = 7
                    column_map['Score'] = 8
                    column_map['Percent'] = 9
                    column_map['USEF'] = 10
                    column_map['EC'] = 11
        except:
            pass
    
    return column_map

def scrape_nonplacing_results_for_class(driver, show_list_id, show_guid, year, show_name, show_class_id, class_num, class_name, entries, placings, row_idx, conn, sleep_short=0.5, sleep_medium=1, sleep_long=3):
    """Scrape non-placing entries for a single class
    
    Args:
        driver: WebDriver instance
        show_list_id: ID from ShowList table
        show_guid: ShowGUID string
        year: Year string
        show_name: Show name string
        show_class_id: ShowClass ID
        class_num: Class number
        class_name: Class name
        entries: Number of entries
        placings: Number of placings
        row_idx: Row index in the grid (1-based)
        conn: Database connection
        sleep_short: Short sleep duration in seconds (default: 0.5)
        sleep_medium: Medium sleep duration in seconds (default: 1)
        sleep_long: Long sleep duration in seconds (default: 3)
    
    Returns: (driver, count of entries saved)
    """
    entries_saved = 0
    
    try:
        # Check existing non-placing entries count for this class
        cursor_check = conn.cursor()
        cursor_check.execute("""
            SELECT COUNT(*) 
            FROM sResults.ShowResults 
            WHERE ShowClassID = ? AND Place = 0
        """, show_class_id)
        existing_count = cursor_check.fetchone()[0]
        cursor_check.close()
        
        expected_count = entries - placings
        if existing_count >= expected_count:
            print_with_timestamp(f"  Skipping class {class_num}: {class_name[:50]} (already has {existing_count}/{expected_count} non-placing entries)")
            # Mark as complete
            try:
                cursor_mark = conn.cursor()
                cursor_mark.execute("""
                    UPDATE sResults.ShowClass 
                    SET NonPlacingComplete = 1, UpdatedDate = GETDATE()
                    WHERE ID = ?
                """, show_class_id)
                conn.commit()
                cursor_mark.close()
            except Exception as e:
                print_with_timestamp(f"    [WARNING] Error marking class as complete: {e}")
            return driver, 0
        
        print_with_timestamp(f"  Processing class {class_num}: {class_name[:50]} (Entries: {entries}, Placings: {placings}, Non-placing: {expected_count}, Existing: {existing_count})")
        
        # Check if driver session is still valid
        try:
            _ = driver.current_url
        except (InvalidSessionIdException, Exception) as session_error:
            print_with_timestamp(f"    [WARNING] Browser session lost, attempting to reconnect...")
            new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
            if new_driver:
                driver = new_driver
                print_with_timestamp(f"    [OK] Browser reconnected successfully")
            else:
                print_with_timestamp(f"    [ERROR] Failed to reconnect browser, skipping class")
                log_import_activity(conn, 'scrape_class_nonplacing_results.py', target_table='ShowResults', 
                                  action='ERROR', error_detail=f'Browser session lost: {str(session_error)}',
                                  additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}')
                return driver, 0
        
        # Re-find the grid and row
        try:
            grid = driver.find_element(By.CSS_SELECTOR, 
                "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
        except (InvalidSessionIdException, StaleElementReferenceException) as e:
            print_with_timestamp(f"    [WARNING] Browser session issue when finding grid, attempting to reconnect...")
            new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
            if new_driver:
                driver = new_driver
                grid = driver.find_element(By.CSS_SELECTOR, 
                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
            else:
                raise
        rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
        if not rows:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            rows = []
            for r in all_rows:
                row_id = r.get_attribute('id') or ''
                row_class = r.get_attribute('class') or ''
                # Only include main grid rows, not detail rows (grPlacing, grNonPlacing, or dxdt containers)
                if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                    # Exclude detail rows from nested grids
                    if 'grPlacing' not in row_id and 'grNonPlacing' not in row_id and 'dxdt' not in row_id:
                        rows.append(r)
        
        if row_idx > len(rows):
            print_with_timestamp(f"    [WARNING] Row {row_idx} no longer available")
            return driver, 0
        
        class_row = rows[row_idx - 1]
        # Store row ID immediately while element is fresh - ensure it's a class row ID, not a detail row
        class_row_id = ''
        try:
            temp_id = class_row.get_attribute('id') or ''
            # Verify this is a class row ID (not from grPlacing or grNonPlacing detail tables)
            # Accept any row ID that doesn't contain detail table identifiers
            # Class rows should have 'grMaster' or 'DXMainTable' in their ID path, not nested grid IDs
            if temp_id and 'grPlacing' not in temp_id and 'grNonPlacing' not in temp_id:
                # Additional check: ensure it's from the main grid, not a nested detail grid
                # Main grid rows typically have 'grMaster' in the ID path
                if 'grMaster' in temp_id or 'DXMainTable' in temp_id:
                    class_row_id = temp_id
                elif 'dxdt' not in temp_id:  # dxdt indicates a detail row container
                    # If it doesn't have detail indicators, accept it
                    class_row_id = temp_id
                else:
                    print_with_timestamp(f"    [WARNING] Row {row_idx} appears to be a detail row (contains dxdt): {temp_id}")
            elif temp_id:
                # If it has grPlacing or grNonPlacing, it's definitely a detail row
                print_with_timestamp(f"    [WARNING] Row {row_idx} has detail grid identifier (grPlacing/grNonPlacing) in ID: {temp_id}")
                # Don't use detail row IDs - they won't work for expand_row
                class_row_id = ''
        except Exception as e:
            print_with_timestamp(f"    [WARNING] Error getting row ID: {e}")
        
        if not class_row_id:
            # Try alternative: use row index as fallback identifier
            print_with_timestamp(f"    [WARNING] Could not get class row ID for row {row_idx}, attempting to use row index")
            # Re-find the row and try again
            try:
                grid = driver.find_element(By.CSS_SELECTOR, 
                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                rows_refresh = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                if not rows_refresh:
                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                    rows_refresh = []
                    for r in all_rows:
                        row_id = r.get_attribute('id') or ''
                        row_class = r.get_attribute('class') or ''
                        # Only include main grid rows, not detail rows
                        if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                            # Exclude detail rows from nested grids
                            if 'grPlacing' not in row_id and 'grNonPlacing' not in row_id and 'dxdt' not in row_id:
                                rows_refresh.append(r)
                
                if row_idx <= len(rows_refresh):
                    class_row = rows_refresh[row_idx - 1]
                    temp_id = class_row.get_attribute('id') or ''
                    # Verify this is a class row ID (not from detail tables)
                    if temp_id and 'grPlacing' not in temp_id and 'grNonPlacing' not in temp_id:
                        # Additional check: ensure it's from the main grid
                        if 'grMaster' in temp_id or 'DXMainTable' in temp_id or 'dxdt' not in temp_id:
                            class_row_id = temp_id
                            print_with_timestamp(f"    [OK] Retrieved row ID on retry: {class_row_id}")
                        else:
                            print_with_timestamp(f"    [WARNING] Row ID appears to be a detail row: {temp_id}")
                    elif temp_id:
                        print_with_timestamp(f"    [WARNING] Row ID contains detail grid identifier: {temp_id}, skipping")
            except Exception as e2:
                print_with_timestamp(f"    [ERROR] Error on retry: {e2}")
        
        if not class_row_id:
            print_with_timestamp(f"    [ERROR] Could not get valid class row ID for row {row_idx} after retry")
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='ERROR', 
                              error_detail=f'Could not get valid class row ID for row {row_idx}',
                              additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, RowIdx: {row_idx}')
            return driver, 0
        
        # Expand the row if not already expanded
        print_with_timestamp(f"    Attempting to expand row {row_idx}...")
        # Re-find the row right before expanding
        try:
            grid = driver.find_element(By.CSS_SELECTOR,
                "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            rows_refresh = []
            for r in all_rows:
                try:
                    row_id = r.get_attribute('id') or ''
                    row_class = r.get_attribute('class') or ''
                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                        rows_refresh.append(r)
                except StaleElementReferenceException:
                    continue
            
                if row_idx <= len(rows_refresh):
                    class_row = rows_refresh[row_idx - 1]
                    # Get fresh class row ID and verify it's from the main grid, not a detail row
                    temp_id = class_row.get_attribute('id') or ''
                    # Accept any row ID that doesn't contain detail grid identifiers
                    if temp_id and 'grPlacing' not in temp_id and 'grNonPlacing' not in temp_id:
                        # Additional check: ensure it's from the main grid
                        if 'grMaster' in temp_id or 'DXMainTable' in temp_id or 'dxdt' not in temp_id:
                            class_row_id = temp_id
                        else:
                            print_with_timestamp(f"      [WARNING] Row ID appears to be a detail row: {temp_id}")
                    elif temp_id:
                        # If it has detail grid identifiers, don't use it
                        print_with_timestamp(f"      [WARNING] Row ID contains detail grid identifier (grPlacing/grNonPlacing): {temp_id}, keeping original")
                    # If invalid, keep the original class_row_id
        except Exception as e:
            print_with_timestamp(f"      [DEBUG] Error re-finding row before expand: {e}")
        
        def create_reconnect_func():
            return reconnect_browser_and_navigate(driver, show_guid, year, show_name)
        
        row_expanded = expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
        if row_expanded:
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='ROW_EXPANDED', 
                              additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, RowID: {class_row_id}')
            # Wait for non-placing entries grid to load
            try:
                # Look for "Non placing entries" or similar text, or grid with non-placing data
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='gr'], table.dxgvTable"))
                )
            except:
                time.sleep(sleep_short)  # Fallback to short sleep if wait fails
            
            # Re-find the row after expansion
            try:
                grid = driver.find_element(By.CSS_SELECTOR,
                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                all_rows = grid.find_elements(By.TAG_NAME, "tr")
                rows = []
                for r in all_rows:
                    row_id = r.get_attribute('id') or ''
                    row_class = r.get_attribute('class') or ''
                    # Only include main grid rows, not detail rows
                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                        # Exclude detail rows from nested grids
                        if 'grPlacing' not in row_id and 'grNonPlacing' not in row_id and 'dxdt' not in row_id:
                            rows.append(r)
                
                if row_idx <= len(rows):
                    class_row = rows[row_idx - 1]
            except:
                pass
            
            # Find non-placing entries detail rows with retry on stale element errors
            detail_rows = []
            
            # Try multiple strategies to find non-placing entries grid (with retry on stale element and reconnection)
            max_strategy_retries = 3
            strategy_retry_delay = 0.5
            strategy_success = False
            driver_reconnected = False
            
            for strategy_attempt in range(max_strategy_retries):
                if strategy_success:
                    break
                
                try:
                    # On second retry or later, try reconnecting browser if stale elements persist
                    if strategy_attempt > 0 and not driver_reconnected:
                        print_with_timestamp(f"      [RETRY] Attempting browser reconnection before retry {strategy_attempt + 1}/{max_strategy_retries}...")
                        new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                        if new_driver:
                            driver = new_driver
                            driver_reconnected = True
                            # Re-find grid and rows after reconnection
                            grid = driver.find_element(By.CSS_SELECTOR,
                                "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                            rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                            if not rows:
                                all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                rows = []
                                for r in all_rows:
                                    row_id = r.get_attribute('id') or ''
                                    row_class = r.get_attribute('class') or ''
                                    # Only include main grid rows, not detail rows
                                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                        # Exclude detail rows from nested grids
                                        if 'grPlacing' not in row_id and 'grNonPlacing' not in row_id and 'dxdt' not in row_id:
                                            rows.append(r)
                            
                            if row_idx <= len(rows):
                                class_row = rows[row_idx - 1]
                                class_row_id = class_row.get_attribute('id') or ''
                                # Re-expand the row after reconnection
                                print_with_timestamp(f"      [RECONNECT] Re-expanding row after browser reconnection...")
                                expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                time.sleep(sleep_medium)
                    
                    # Strategy 1: Look for non-placing entry grids following the class row (NOT grPlacing)
                    grid = driver.find_element(By.CSS_SELECTOR,
                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                    all_trs = grid.find_elements(By.TAG_NAME, "tr")
                    
                    # Find the class row index
                    class_row_idx = -1
                    for i, tr in enumerate(all_trs):
                        try:
                            tr_id = tr.get_attribute('id') or ''
                            if tr_id == class_row_id:
                                class_row_idx = i
                                break
                        except StaleElementReferenceException:
                            continue
                    
                    if class_row_idx >= 0:
                        # Look for rows following the class row that contain non-placing entry grids
                        for i in range(class_row_idx + 1, len(all_trs)):
                            try:
                                next_tr = all_trs[i]
                                next_tr_id = next_tr.get_attribute('id') or ''
                                next_tr_class = next_tr.get_attribute('class') or ''
                                
                                # If this is another class row, stop
                                if 'DataRow' in next_tr_id and 'dxdt' not in next_tr_id and 'dxgvDetailRow' not in next_tr_class:
                                    cells = next_tr.find_elements(By.TAG_NAME, "td")
                                    if len(cells) >= 2:
                                        break
                                
                                # Look for tables that are NOT grPlacing (those are the placing entries)
                                nested_tables = next_tr.find_elements(By.TAG_NAME, "table")
                                for nested_table in nested_tables:
                                    table_id = nested_table.get_attribute('id') or ''
                                    
                                    # Skip placing entry grids (grPlacing)
                                    if 'grPlacing' in table_id:
                                        continue
                                    
                                    # Look for non-placing entry grids
                                    table_rows = nested_table.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                                    if table_rows:
                                        # Check if this looks like an entry table (has many columns)
                                        for tr in table_rows[:1]:  # Check first row to see structure
                                            cells = tr.find_elements(By.TAG_NAME, "td")
                                            # Non-placing entry rows have 12 columns (Entry, Horse, Rider, Country, Owner, Trainer, Prize, Start, Score, Percent, USEF, EC)
                                            if len(cells) >= 12:  # 12 columns for non-placing entries
                                                # This could be a non-placing entry grid
                                                # Store all rows from this table
                                                for nr in table_rows:
                                                    nr_id = nr.get_attribute('id') or ''
                                                    if 'HeaderRow' not in nr_id and 'FilterRow' not in nr_id:
                                                        detail_rows.append((nr, nested_table))
                                                break
                            except StaleElementReferenceException:
                                # If stale element, break out and retry the whole strategy
                                raise
                            except Exception:
                                continue
                        
                        if detail_rows:
                            print_with_timestamp(f"      Strategy 1 found {len(detail_rows)} non-placing entry rows")
                            strategy_success = True
                            break
                except StaleElementReferenceException as e:
                    if strategy_attempt < max_strategy_retries - 1:
                        print_with_timestamp(f"      Strategy 1 stale element (attempt {strategy_attempt + 1}/{max_strategy_retries}), attempting browser reconnection...")
                        
                        # Immediately attempt browser reconnection on stale element
                        if not driver_reconnected:
                            try:
                                new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                if new_driver:
                                    driver = new_driver
                                    driver_reconnected = True
                                    # Re-find grid and rows after reconnection
                                    grid = driver.find_element(By.CSS_SELECTOR,
                                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                    rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                    if not rows:
                                        all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                        rows = []
                                        for r in all_rows:
                                            row_id = r.get_attribute('id') or ''
                                            row_class = r.get_attribute('class') or ''
                                            if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                                rows.append(r)
                                    
                                    if row_idx <= len(rows):
                                        class_row = rows[row_idx - 1]
                                        # Get fresh class row ID - ensure it's from the main grid, not a detail row
                                        fresh_class_row_id = class_row.get_attribute('id') or ''
                                        # Verify this is a class row ID (not from detail tables)
                                        # Accept any row ID that doesn't contain detail grid identifiers
                                        if fresh_class_row_id and 'grPlacing' not in fresh_class_row_id and 'grNonPlacing' not in fresh_class_row_id:
                                            # Additional check: ensure it's from the main grid
                                            if 'grMaster' in fresh_class_row_id or 'DXMainTable' in fresh_class_row_id or 'dxdt' not in fresh_class_row_id:
                                                class_row_id = fresh_class_row_id
                                                # Re-expand the row after reconnection
                                                print_with_timestamp(f"      [RECONNECT] Re-expanding row {row_idx} after browser reconnection...")
                                                expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                time.sleep(sleep_long)  # Longer wait after reconnection
                                                print_with_timestamp(f"      Retrying Strategy 1 after reconnection...")
                                            else:
                                                print_with_timestamp(f"      [WARNING] Row ID appears to be a detail row: {fresh_class_row_id}")
                                                break
                                        elif fresh_class_row_id:
                                            # If it has detail grid identifiers, don't use it
                                            print_with_timestamp(f"      [WARNING] Row ID contains detail grid identifier: {fresh_class_row_id}, cannot use for expansion")
                                            break
                                        else:
                                            print_with_timestamp(f"      [ERROR] Invalid class row ID after reconnection: {fresh_class_row_id} (empty or None)")
                                            break
                                    else:
                                        print_with_timestamp(f"      [ERROR] Row {row_idx} no longer available after reconnection")
                                        break
                            except Exception as reconnect_error:
                                print_with_timestamp(f"      [WARNING] Error during browser reconnection: {reconnect_error}")
                                time.sleep(strategy_retry_delay)
                        
                        detail_rows = []  # Reset for retry
                        continue  # Continue to next iteration
                    else:
                        print_with_timestamp(f"      Strategy 1 error (final attempt): {e}")
                        break  # Break out of loop on final attempt
                except Exception as e:
                    print_with_timestamp(f"      Strategy 1 error: {e}")
            
            # Alternative strategy: Look for text "Non placing" or similar in the page
            if not detail_rows:
                try:
                    # Try to find any table with "Non" or "non-placing" in nearby text
                    page_text = driver.page_source.lower()
                    if 'non placing' in page_text or 'non-placing' in page_text:
                        # Look for all tables that might contain non-placing entries
                        all_tables = driver.find_elements(By.CSS_SELECTOR, "table[id*='gr'], table.dxgvTable")
                        for table in all_tables:
                            table_id = table.get_attribute('id') or ''
                            # Skip placing grids
                            if 'grPlacing' in table_id:
                                continue
                            
                            # Check if this table has entry-like rows
                            table_rows = table.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                            if table_rows:
                                for tr in table_rows[:1]:
                                    cells = tr.find_elements(By.TAG_NAME, "td")
                                    if len(cells) >= 12:  # 12 columns for non-placing entries
                                        # Store all rows
                                        for nr in table_rows:
                                            nr_id = nr.get_attribute('id') or ''
                                            if 'HeaderRow' not in nr_id and 'FilterRow' not in nr_id:
                                                detail_rows.append((nr, table))
                                        break
                except Exception as e:
                    print_with_timestamp(f"      [WARNING] Error in alternative strategy: {e}")
            
            print_with_timestamp(f"      Found {len(detail_rows)} non-placing entry rows")
            
            # Log extraction
            if detail_rows:
                log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='EXTRACT_DATA', 
                                  additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, Rows found: {len(detail_rows)}')
            
            if detail_rows:
                # Get column mapping for non-placing entries (same as placing but without Place)
                grid_table = detail_rows[0][1] if isinstance(detail_rows[0], tuple) else None
                if grid_table:
                    entry_column_map = get_column_indices_for_nonplacing_grid(grid_table)
                    print_with_timestamp(f"      Non-placing entry column mapping: {entry_column_map}")
                else:
                    print_with_timestamp(f"      [WARNING] Could not find grid table for column mapping")
                    entry_column_map = {}
                
                # Extract all entry details
                all_entry_details = []
                max_nonplacing = entries - placings  # Maximum number of non-placing entries expected
                seen_entries = set()
                
                for detail_row_item in detail_rows:
                    if isinstance(detail_row_item, tuple):
                        detail_row = detail_row_item[0]
                    else:
                        detail_row = detail_row_item
                    
                    if entry_column_map:
                        try:
                            cells = detail_row.find_elements(By.TAG_NAME, "td")
                            if len(cells) >= 3:
                                entry_data = {}
                                # Set Place to 0 for non-placing entries
                                entry_data['Place'] = '0'
                                # Set AddBack to '$0.00' for non-placing entries (not in grid)
                                entry_data['AddBack'] = '$0.00'
                                
                                for field, idx in entry_column_map.items():
                                    if field in ['Place', 'AddBack']:
                                        continue  # Already set to defaults, skip these fields
                                    if idx is not None and len(cells) > idx:
                                        entry_data[field] = cells[idx].text.strip()
                                    else:
                                        entry_data[field] = ''
                                
                                # Check for duplicates using Entry number
                                entry_number = entry_data.get('Entry', '').strip()
                                if entry_number:
                                    if entry_number in seen_entries:
                                        continue  # Skip duplicate
                                    seen_entries.add(entry_number)
                                
                                if entry_data and len(all_entry_details) < max_nonplacing:
                                    all_entry_details.append(entry_data)
                        except StaleElementReferenceException:
                            # Use retry function for stale elements
                            def extract_nonplacing_entry():
                                cells = detail_row.find_elements(By.TAG_NAME, "td")
                                if len(cells) < 3:
                                    return None
                                entry_data = {}
                                # Set Place to 0 for non-placing entries
                                entry_data['Place'] = '0'
                                # Set AddBack to '$0.00' for non-placing entries (not in grid)
                                entry_data['AddBack'] = '$0.00'
                                
                                for field, idx in entry_column_map.items():
                                    if field in ['Place', 'AddBack']:
                                        continue  # Already set to defaults
                                    if idx is not None and len(cells) > idx:
                                        entry_data[field] = cells[idx].text.strip()
                                    else:
                                        entry_data[field] = ''
                                return entry_data
                            
                            entry_details = retry_on_stale_element(extract_nonplacing_entry, max_retries=3, delay=sleep_short, reconnect_func=create_reconnect_func)
                            if entry_details:
                                entry_details['Place'] = '0'  # Ensure Place is set
                                entry_details['AddBack'] = '$0.00'  # Ensure AddBack is set
                                entry_number = entry_details.get('Entry', '').strip()
                                if entry_number and entry_number not in seen_entries:
                                    seen_entries.add(entry_number)
                                    if len(all_entry_details) < max_nonplacing:
                                        all_entry_details.append(entry_details)
                        except Exception:
                            pass
                
                # Save to database
                if all_entry_details:
                    print_with_timestamp(f"      Extracted {len(all_entry_details)} non-placing entry details, saving to database...")
                    cursor = conn.cursor()
                    try:
                        for entry_details in all_entry_details:
                            if save_show_result_to_database(conn, show_class_id, entry_details, cursor=cursor, commit=False):
                                entries_saved += 1
                        conn.commit()
                        print_with_timestamp(f"      Saved {entries_saved}/{len(all_entry_details)} non-placing entries")
                        
                        # Check if we've reached the expected count and mark as complete
                        cursor_check_complete = conn.cursor()
                        cursor_check_complete.execute("""
                            SELECT COUNT(*) 
                            FROM sResults.ShowResults 
                            WHERE ShowClassID = ? AND Place = 0
                        """, show_class_id)
                        final_count = cursor_check_complete.fetchone()[0]
                        cursor_check_complete.close()
                        
                        if final_count >= expected_count:
                            cursor_mark = conn.cursor()
                            cursor_mark.execute("""
                                UPDATE sResults.ShowClass 
                                SET NonPlacingComplete = 1, UpdatedDate = GETDATE()
                                WHERE ID = ?
                            """, show_class_id)
                            conn.commit()
                            cursor_mark.close()
                            print_with_timestamp(f"      [OK] Marked class as complete ({final_count}/{expected_count} non-placing entries)")
                    except Exception as e:
                        conn.rollback()
                        print_with_timestamp(f"      [WARNING] Error in batch save: {e}")
                    finally:
                        cursor.close()
            else:
                print_with_timestamp(f"      [WARNING] No non-placing entry rows found after expansion")
            
            # Collapse the row
            try:
                collapse_row(driver, class_row_id, reconnect_func=create_reconnect_func)
            except:
                pass
        
        return driver, entries_saved
        
    except InvalidSessionIdException as e:
        print_with_timestamp(f"    [ERROR] Invalid browser session, attempting to reconnect...")
        import traceback
        error_trace = traceback.format_exc()
        new_driver = None
        try:
            new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
            if new_driver:
                driver = new_driver
                print_with_timestamp(f"    [OK] Browser reconnected, but class processing failed")
        except Exception as reconnect_error:
            print_with_timestamp(f"    [ERROR] Failed to reconnect browser: {reconnect_error}")
        
        # Log the error
        log_import_activity(conn, 'scrape_class_nonplacing_results.py', target_table='ShowResults', 
                          action='ERROR', error_detail=f'InvalidSessionIdException: {str(e)}',
                          additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, Reconnected: {new_driver is not None}')
        return driver, entries_saved
    except Exception as e:
        print_with_timestamp(f"    [ERROR] Error scraping non-placing entries: {e}")
        import traceback
        error_trace = traceback.format_exc()
        log_import_activity(conn, 'scrape_class_nonplacing_results.py', target_table='ShowResults', 
                          action='ERROR', error_detail=str(e),
                          additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, Trace: {error_trace[:2000]}')
        traceback.print_exc()
        return driver, entries_saved

def scrape_nonplacing_results_for_show(driver, show_list_id, show_guid, year, show_name, class_data_list, conn, sleep_short=0.5, sleep_medium=1, sleep_long=3):
    """Scrape non-placing entries for all classes in a show
    
    Args:
        driver: WebDriver instance
        show_list_id: ID from ShowList table
        show_guid: ShowGUID string
        year: Year string
        show_name: Show name string
        class_data_list: List of class data tuples (show_class_id, class_num, class_name, entries, placings, row_idx)
        conn: Database connection
        sleep_short: Short sleep duration in seconds (default: 0.5)
        sleep_medium: Medium sleep duration in seconds (default: 1)
        sleep_long: Long sleep duration in seconds (default: 3)
    
    Returns: (driver, total entries saved)
    """
    print_with_timestamp(f"\n{'='*60}")
    print_with_timestamp(f"Scraping non-placing entries for ShowGUID: {show_guid} (Year: {year})")
    print_with_timestamp(f"Show: {show_name}")
    print_with_timestamp(f"Classes to process: {len(class_data_list)}")
    print_with_timestamp(f"{'='*60}")
    
    # Log show processing start
    log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='PROCESS_SHOW_START', 
                      additional_info=f'ShowGUID: {show_guid}, Year: {year}, ShowName: {show_name}, Classes: {len(class_data_list)}')
    
    total_entries_saved = 0
    
    try:
        # Navigate to ShowSelector page first
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        if 'ShowSelector' not in driver.current_url:
            print_with_timestamp("  Navigating to ShowSelector page...")
            driver.get(show_selector_url)
            time.sleep(sleep_long)
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='NAVIGATE', 
                              additional_info=f'Navigated to ShowSelector page for ShowGUID: {show_guid}')
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(driver, sleep_medium=sleep_long, sleep_short=sleep_short):
            print_with_timestamp(f"  [WARNING] Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            driver.get(class_results_url)
            time.sleep(sleep_long)
        else:
            # Select the year
            if not select_year(driver, year, sleep_short=sleep_medium, sleep_medium=sleep_long):
                print_with_timestamp(f"  [WARNING] Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                driver.get(class_results_url)
                time.sleep(sleep_long)
            else:
                # Find and click the show row to navigate to ClassResults
                if not find_and_click_show_row(driver, show_guid, year, show_name, sleep_medium=sleep_long):
                    print_with_timestamp(f"  [WARNING] Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    driver.get(class_results_url)
                    time.sleep(sleep_long)
        
        # Wait for the ClassResults page to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
            )
        except TimeoutException:
            print_with_timestamp(f"  [WARNING] Grid table not found after 10 seconds")
        
        time.sleep(sleep_medium)
        
        # Find the results grid
        grid = None
        grid_selectors = [
            "table[id*='grMaster'][id*='DXMainTable']",
            "table[id*='grMaster']",
            "table[id*='DXMainTable']",
            "table.dxgvTable_Office2010Blue",
            "table.dxgvTable",
        ]
        
        for selector in grid_selectors:
            try:
                grids = driver.find_elements(By.CSS_SELECTOR, selector)
                for g in grids:
                    if g.is_displayed():
                        tr_count = len(g.find_elements(By.TAG_NAME, "tr"))
                        if tr_count > 1:
                            grid = g
                            break
                if grid:
                    break
            except:
                continue
        
        if not grid:
            print_with_timestamp(f"  [WARNING] Could not find results grid for ShowGUID: {show_guid}")
            return driver, 0
        
        # Get column mapping for class summary (to find row indices)
        class_column_map = get_column_indices_for_class_grid(grid)
        
        # Build a lookup map: (Class, ClassName) -> row_index
        grid_lookup = {}
        class_rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
        if not class_rows:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            for r in all_rows:
                row_id = r.get_attribute('id') or ''
                row_class = r.get_attribute('class') or ''
                # Only include main grid rows, not detail rows
                if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                    # Exclude detail rows from nested grids
                    if 'grPlacing' not in row_id and 'grNonPlacing' not in row_id and 'dxdt' not in row_id:
                        class_rows.append(r)
        
        for idx, class_row in enumerate(class_rows, 1):
            try:
                cells = class_row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 3:
                    class_col_idx = class_column_map.get('Class')
                    class_name_col_idx = class_column_map.get('Class Name')
                    
                    if class_col_idx is not None and len(cells) > class_col_idx:
                        grid_class = cells[class_col_idx].text.strip().lower()
                    else:
                        grid_class = ''
                    
                    if class_name_col_idx is not None and len(cells) > class_name_col_idx:
                        grid_class_name = cells[class_name_col_idx].text.strip().lower()
                    else:
                        grid_class_name = ''
                    
                    if grid_class or grid_class_name:
                        lookup_key = (grid_class, grid_class_name)
                        grid_lookup[lookup_key] = idx
            except:
                continue
        
        # Process each class
        for class_idx, (show_class_id, class_num, class_name, entries, placings) in enumerate(class_data_list, 1):
            # Find row index for this class
            lookup_key = (str(class_num).strip().lower(), (class_name or '').strip().lower())
            row_idx = grid_lookup.get(lookup_key)
            
            if not row_idx:
                print_with_timestamp(f"  [WARNING] Could not find grid row for Class {class_num}: {class_name[:50]}")
                log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='CLASS_SKIP', 
                                  additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, Reason: Row not found in grid')
                continue
            
            # Log class processing start
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='PROCESS_CLASS_START', 
                              target_table='ShowResults',
                              additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, RowIdx: {row_idx}, Class {class_idx}/{len(class_data_list)}')
            
            driver, entries_saved = scrape_nonplacing_results_for_class(
                driver, show_list_id, show_guid, year, show_name,
                show_class_id, class_num, class_name, entries, placings, row_idx, conn,
                sleep_short=sleep_short, sleep_medium=sleep_medium, sleep_long=sleep_long
            )
            total_entries_saved += entries_saved
            
            # Log class processing completion
            if entries_saved > 0:
                log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='PROCESS_CLASS_COMPLETE', 
                                  target_table='ShowResults', row_count=entries_saved,
                                  additional_info=f'ShowClassID: {show_class_id}, Class: {class_num}, Entries saved: {entries_saved}')
        
        print_with_timestamp(f"  [OK] Completed non-placing entries for ShowGUID {show_guid}: {total_entries_saved} entries saved")
        
        # Log show processing completion
        log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='PROCESS_SHOW_COMPLETE', 
                          row_count=total_entries_saved,
                          additional_info=f'ShowGUID: {show_guid}, Year: {year}, Total entries saved: {total_entries_saved}, Classes processed: {len(class_data_list)}')
        
        return driver, total_entries_saved
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error scraping non-placing entries for ShowGUID {show_guid}: {e}")
        import traceback
        traceback.print_exc()
        return driver, total_entries_saved

def main(start_from_show_guid=None, sleep_short=0.5, sleep_medium=1):
    """Main function to scrape non-placing entry results
    
    Args:
        start_from_show_guid: Optional ShowGUID to start from
        sleep_short: Short sleep duration in seconds (default: 0.5)
        sleep_medium: Medium sleep duration in seconds (default: 1)
    """
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("HorseShowsOnline - Non-Placing Entry Results Scraper")
    print_with_timestamp("=" * 60 + "\n")
    
    driver = None
    conn = None
    
    try:
        # Setup driver
        print_with_timestamp("Initializing browser (headless mode)...")
        driver = setup_driver(headless=True)
        print_with_timestamp("  [OK] Browser initialized\n")
        
        # Connect to database
        print_with_timestamp("Connecting to database...")
        conn = get_db_connection()
        print_with_timestamp("[OK] Connected to database\n")
        
        # Ensure tables exist (including ShowClass with NonPlacingComplete column)
        create_importlog_table_if_not_exists(conn)
        create_showclass_table_if_not_exists(conn)
        
        # Log script start
        log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='START', 
                          additional_info=f'start_from_show_guid={start_from_show_guid}')
        
        # Get classes with non-placing entries
        print_with_timestamp("Fetching classes with Entries > Placings...")
        class_data_list = get_classes_with_nonplacing_entries(conn, start_from_show_guid=start_from_show_guid)
        print_with_timestamp(f"[OK] Found {len(class_data_list)} classes with non-placing entries\n")
        
        if not class_data_list:
            print_with_timestamp("[WARNING] No classes found with Entries > Placings.")
            return
        
        # Group classes by show
        shows_dict = {}
        for row in class_data_list:
            show_list_id, show_guid, year, show_name, show_class_id, class_num, class_name, entries, placings = row
            if (show_list_id, show_guid, year, show_name) not in shows_dict:
                shows_dict[(show_list_id, show_guid, year, show_name)] = []
            shows_dict[(show_list_id, show_guid, year, show_name)].append((show_class_id, class_num, class_name, entries, placings))
        
        # Process each show
        total_entries = 0
        for idx, ((show_list_id, show_guid, year, show_name), class_list) in enumerate(shows_dict.items(), 1):
            print_with_timestamp(f"\nProcessing show {idx}/{len(shows_dict)}...")
            driver, entries_saved = scrape_nonplacing_results_for_show(
                driver, show_list_id, show_guid, year, show_name, class_list, conn,
                sleep_short=sleep_short, sleep_medium=sleep_medium, sleep_long=sleep_medium * 2 + 1
            )
            total_entries += entries_saved
            
            time.sleep(sleep_medium)
        
        print_with_timestamp(f"\n{'='*60}")
        print_with_timestamp(f"Scraping complete! Total non-placing entries collected: {total_entries}")
        print_with_timestamp(f"{'='*60}\n")
        
        # Log completion
        if conn:
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='COMPLETE', 
                              row_count=total_entries, additional_info=f'Total entries: {total_entries}')
        
    except KeyboardInterrupt:
        print_with_timestamp("\n\n[WARNING] Scraping interrupted by user")
        if conn:
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='INTERRUPTED', 
                              error_detail='User interrupted scraping')
    except Exception as e:
        print_with_timestamp(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        error_trace = traceback.format_exc()
        if conn:
            log_import_activity(conn, 'scrape_class_nonplacing_results.py', action='ERROR', 
                              error_detail=str(e), additional_info=error_trace[:4000])
        traceback.print_exc()
    finally:
        if conn:
            try:
                conn.close()
                print_with_timestamp("[OK] Database connection closed")
            except:
                pass
        if driver:
            print_with_timestamp("\nClosing browser...")
            driver.quit()

if __name__ == '__main__':
    import sys
    
    start_from_show_guid = None
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        arg_lower = arg.lower()
        
        if arg_lower in ['--start-from', '-s']:
            if i + 1 < len(sys.argv):
                start_from_show_guid = sys.argv[i + 1]
                print_with_timestamp(f"[INFO] Command-line argument detected: Will start from ShowGUID {start_from_show_guid}")
                i += 1
            else:
                print_with_timestamp("[ERROR] --start-from requires a ShowGUID value")
                sys.exit(1)
        elif arg_lower in ['--help', '-h']:
            print_with_timestamp("Usage: python scrape_class_nonplacing_results.py [OPTIONS]")
            print_with_timestamp("Options:")
            print_with_timestamp("  --start-from SHOWGUID, -s SHOWGUID: Start processing from the specified ShowGUID")
            sys.exit(0)
        
        i += 1
    
    main(start_from_show_guid=start_from_show_guid, sleep_short=0.5, sleep_medium=1)

