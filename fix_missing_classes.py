"""
Script to find shows with ShowClass data but missing classes in the grid, then scrape missing class data
Compares classes found in the class summary grid with classes in ShowClass table and loads any missing ones
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import pyodbc
import sys
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
    get_or_create_showclass,
    retry_on_stale_element
)

def get_shows_with_existing_classes(conn):
    """Get shows that have ShowClass data (any classes)
    
    Returns: List of tuples (show_list_id, show_guid, year, show_name)
    """
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT DISTINCT
                sl.ID,
                sl.ShowGUID,
                sl.Year,
                sl.ShowName
            FROM sResults.ShowList sl
            WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
            AND sl.StartDate IS NOT NULL
            AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
            -- Has at least one ShowClass entry
            AND EXISTS (
                SELECT 1
                FROM sResults.ShowClass sc
                WHERE sc.ShowListID = sl.ID
            )
            ORDER BY sl.ID
        """)
        
        show_data = [(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]
        cursor.close()
        print_with_timestamp(f"[OK] Found {len(show_data)} shows with existing ShowClass data")
        return show_data
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error getting shows with existing classes: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_existing_classes_for_show(conn, show_list_id):
    """Get set of (Class, ClassName) tuples that exist in ShowClass table for a show
    
    Args:
        conn: Database connection
        show_list_id: ShowList ID
    
    Returns: Set of tuples (class_number, class_name) - both normalized (lowercase, stripped)
    """
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT Class, ClassName 
            FROM sResults.ShowClass 
            WHERE ShowListID = ?
        """, show_list_id)
        
        existing_classes = set()
        for row in cursor.fetchall():
            class_num = (row[0] or '').strip().lower()
            class_name = (row[1] or '').strip().lower()
            existing_classes.add((class_num, class_name))
        
        cursor.close()
        return existing_classes
    except Exception as e:
        print_with_timestamp(f"    [WARNING] Error getting existing classes: {e}")
        return set()

def scrape_missing_classes_for_show(driver, show_list_id, show_guid, year, show_name, conn):
    """Scrape missing class summary data for a specific show
    
    Args:
        driver: WebDriver instance
        show_list_id: ID from ShowList table
        show_guid: ShowGUID string
        year: Year string
        show_name: Show name string
        conn: Database connection
    
    Returns: (driver, count of classes saved) - tuple
    """
    print_with_timestamp(f"\n{'='*60}")
    print_with_timestamp(f"Scraping missing classes for ShowGUID: {show_guid} (Year: {year})")
    print_with_timestamp(f"Show: {show_name}")
    print_with_timestamp(f"{'='*60}")
    
    classes_saved = 0
    
    try:
        # Get existing classes from database
        existing_classes = get_existing_classes_for_show(conn, show_list_id)
        print_with_timestamp(f"  Found {len(existing_classes)} existing classes in database")
        
        # Navigate to ShowSelector page first (reuse logic from scrape_class_results.py)
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        if 'ShowSelector' not in driver.current_url:
            print_with_timestamp("  Navigating to ShowSelector page...")
            driver.get(show_selector_url)
            time.sleep(3)
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(driver):
            print_with_timestamp(f"  [WARNING] Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            driver.get(class_results_url)
            time.sleep(3)
        else:
            # Select the year
            if not select_year(driver, year):
                print_with_timestamp(f"  [WARNING] Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                driver.get(class_results_url)
                time.sleep(3)
            else:
                # Find and click the show row to navigate to ClassResults
                if not find_and_click_show_row(driver, show_guid, year, show_name):
                    print_with_timestamp(f"  [WARNING] Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    driver.get(class_results_url)
                    time.sleep(3)
        
        # Wait for the ClassResults page to load - look for the grid table
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
            )
        except TimeoutException:
            print_with_timestamp(f"  [WARNING] Grid table not found after 10 seconds")
        
        time.sleep(2)  # Additional wait for JavaScript to populate grid
        
        # Find the results grid/table (reuse logic from scrape_class_results.py)
        grid = None
        grid_selectors = [
            "table[id*='grMaster'][id*='DXMainTable']",
            "table[id*='grMaster']",
            "table[id*='DXMainTable']",
            "table.dxgvTable_Office2010Blue",
            "table.dxgvTable",
            "table[id*='MainContent'][id*='gr']",
        ]
        
        for selector in grid_selectors:
            try:
                grids = driver.find_elements(By.CSS_SELECTOR, selector)
                for g in grids:
                    if g.is_displayed():
                        tr_count = len(g.find_elements(By.TAG_NAME, "tr"))
                        if tr_count > 1:
                            grid = g
                            print_with_timestamp(f"  Found grid using selector: {selector} ({tr_count} rows)")
                            break
                if grid:
                    break
            except Exception as e:
                continue
        
        if not grid:
            # Try fallback - find any visible table with class dxgvTable
            try:
                all_tables = driver.find_elements(By.CSS_SELECTOR, "table.dxgvTable")
                for table in all_tables:
                    if table.is_displayed():
                        tr_count = len(table.find_elements(By.TAG_NAME, "tr"))
                        if tr_count > 3:
                            grid = table
                            print_with_timestamp(f"  Found grid using fallback method ({tr_count} rows)")
                            break
            except:
                pass
        
        if not grid:
            # Last resort - find table with most data rows
            try:
                all_tables = driver.find_elements(By.TAG_NAME, "table")
                best_table = None
                max_data_rows = 0
                for table in all_tables:
                    if table.is_displayed():
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        data_row_count = 0
                        for row in rows:
                            cells = row.find_elements(By.TAG_NAME, "td")
                            row_text = row.text.lower()
                            if len(cells) >= 3 and not any(x in row_text for x in ['copyright', 'privacy policy', 'contact']):
                                data_row_count += 1
                        if data_row_count > max_data_rows:
                            max_data_rows = data_row_count
                            best_table = table
                if best_table and max_data_rows > 0:
                    grid = best_table
                    print_with_timestamp(f"  Found grid using last resort method ({max_data_rows} data rows)")
            except:
                pass
        
        if not grid:
            print_with_timestamp(f"  [ERROR] Could not find results grid for ShowGUID: {show_guid}")
            return driver, 0
        
        # Get column mapping for class summary
        class_column_map = get_column_indices_for_class_grid(grid)
        print_with_timestamp(f"  Class column mapping: {class_column_map}")
        
        # Find all class summary rows using the same logic as scrape_class_results.py
        class_rows = []
        
        # Strategy 1: Look for rows with DataRow in ID
        class_rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
        
        # Strategy 2: Look for rows with dxgvDataRow class
        if not class_rows:
            class_rows = grid.find_elements(By.CSS_SELECTOR, "tr.dxgvDataRow")
        
        # Strategy 3: Get all rows and filter intelligently
        if not class_rows:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            for r in all_rows:
                row_id = r.get_attribute('id') or ''
                row_class = r.get_attribute('class') or ''
                
                # Exclude header, filter, footer, and detail rows
                exclude_patterns = ['HeaderRow', 'FilterRow', 'FooterRow', 'DetailRow', 
                                   'PagerBottomRow', 'GroupRow', 'dxgvHeaderRow', 
                                   'dxgvFilterRow', 'dxgvFooterRow']
                if any(pattern in row_id or pattern in row_class for pattern in exclude_patterns):
                    continue
                
                # Check for data row indicators
                is_data_row = ('DataRow' in row_id or 'dxgvDataRow' in row_class or
                              'dxgv' in row_class.lower() and 'data' in row_class.lower())
                
                # Include rows that have data cells (at least 3 td elements, not th)
                cells = r.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 3:
                    # Additional validation: check if this looks like a real data row
                    row_text = r.text.lower()
                    exclude_text = ['copyright', 'all rights reserved', 'privacy policy', 
                                   'terms of service', 'contact', 'version', 'security alerts']
                    if any(exclude in row_text for exclude in exclude_text):
                        continue
                    
                    # Check if the row has numeric data (like Entries column should have numbers)
                    has_numeric = any(cell.text.strip().isdigit() for cell in cells if cell.text.strip())
                    
                    class_rows.append(r)
        
        print_with_timestamp(f"  Found {len(class_rows)} class summary rows in grid")
        
        # Extract all class summaries from grid and compare with database
        print_with_timestamp(f"  Extracting class summaries from grid and comparing with database...")
        
        for row_idx, class_row in enumerate(class_rows, 1):
            try:
                # Re-find row to avoid stale element
                try:
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
                except:
                    pass

                # Extract class summary data with retry on stale element
                def get_cells_and_extract():
                    cells = class_row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 3:
                        return None, None
                    class_summary = {}
                    for field, idx in class_column_map.items():
                        if idx is not None and len(cells) > idx:
                            class_summary[field] = cells[idx].text.strip()
                        else:
                            class_summary[field] = ''
                    return class_summary, cells
                
                result = retry_on_stale_element(get_cells_and_extract, max_retries=3, delay=0.3)
                if not result or result[0] is None:
                    continue
                
                class_summary, cells = result

                # Validate that this looks like a real class row (not footer/copyright)
                class_text = class_summary.get('Class', '').lower()
                class_name_text = class_summary.get('Class Name', '').lower()
                combined_text = (class_text + ' ' + class_name_text).lower()

                exclude_text = ['copyright', 'all rights reserved', 'privacy policy', 
                               'terms of service', 'contact', 'version', 'security alerts',
                               'horseshowsonline', 'timeslice']

                if any(exclude in combined_text for exclude in exclude_text):
                    continue

                # Handle Placings - if Cell 7 is empty, assume 0
                placings = class_summary.get('Placings', '').strip()
                if not placings:
                    placings = '0'
                class_summary['Placings'] = placings

                # Validate Entries field
                entries = class_summary.get('Entries', '').strip()
                entries_is_numeric = entries.isdigit() if entries else False

                # Skip rows that don't have valid class information
                has_class = bool(class_summary.get('Class', '').strip())
                has_class_name = bool(class_summary.get('Class Name', '').strip())

                if not has_class and not has_class_name:
                    continue

                # Handle entries
                entries_int = 0
                if entries and entries_is_numeric:
                    entries_int = int(entries)
                elif not entries or entries.strip() == '':
                    entries = '0'
                    entries_int = 0
                    class_summary['Entries'] = '0'
                else:
                    # Non-numeric entries - skip this row
                    continue

                # Get class number and name (normalized for comparison)
                class_value = class_summary.get('Class', '').strip()
                class_name_value = class_summary.get('Class Name', '').strip()
                
                # If class number is missing, try to find it in cells
                if not class_value or class_value == '#' or class_value == '':
                    # Try searching cells for class number
                    for cell in cells[1:6]:  # Skip first cell (command column), check next 5
                        cell_text = cell.text.strip()
                        if cell_text and (cell_text.isdigit() or cell_text == '#'):
                            if cell_text != '#':
                                class_value = cell_text
                                class_summary['Class'] = cell_text
                            break
                
                # Normalize for comparison (lowercase, stripped)
                class_key = (class_value.lower().strip(), class_name_value.lower().strip())
                
                # Check if this class already exists in database
                if class_key in existing_classes:
                    # Already in database, skip
                    continue
                
                # This class is missing from database - save it
                print_with_timestamp(f"    Found missing class: Class='{class_value}', ClassName='{class_name_value[:50]}', Entries={entries}, Placings={placings}")
                
                # Save ShowClass to database
                show_class_id = get_or_create_showclass(conn, show_list_id, class_summary)
                if show_class_id:
                    print_with_timestamp(f"      [OK] Saved missing class to database (ShowClass ID: {show_class_id})")
                    classes_saved += 1
                    # Add to existing_classes set so we don't try to save it again if it appears twice
                    existing_classes.add(class_key)
                else:
                    print_with_timestamp(f"      [ERROR] Could not create/get ShowClass for class")
                
            except Exception as e:
                print_with_timestamp(f"    [WARNING] Error extracting class row {row_idx}: {e}")
                continue
        
        print_with_timestamp(f"  [OK] Completed processing missing classes for ShowGUID {show_guid}: {classes_saved} new classes saved")
        return driver, classes_saved
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error scraping missing classes for ShowGUID {show_guid}: {e}")
        import traceback
        traceback.print_exc()
        return driver, classes_saved

def main():
    """Main function"""
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("Fix Missing Classes - Scraper")
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
        
        # Get shows with existing ShowClass data
        print_with_timestamp("Finding shows with existing ShowClass data...")
        show_data_list = get_shows_with_existing_classes(conn)
        
        if not show_data_list:
            print_with_timestamp("[OK] No shows found with ShowClass data.")
            return
        
        print_with_timestamp(f"\nFound {len(show_data_list)} shows with existing ShowClass data\n")
        
        # Process each show
        total_classes_saved = 0
        for idx, (show_list_id, show_guid, year, show_name) in enumerate(show_data_list, 1):
            print_with_timestamp(f"\nProcessing show {idx}/{len(show_data_list)}...")
            driver, classes_saved = scrape_missing_classes_for_show(driver, show_list_id, show_guid, year, show_name, conn)
            total_classes_saved += classes_saved
            
            # Small delay between shows
            time.sleep(2)
        
        print_with_timestamp(f"\n{'='*60}")
        print_with_timestamp(f"Processing complete! Processed {len(show_data_list)} shows, saved {total_classes_saved} missing classes")
        print_with_timestamp(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        print_with_timestamp("\n\n[WARNING] Processing interrupted by user")
    except Exception as e:
        print_with_timestamp(f"\n[ERROR] Fatal Error: {e}")
        import traceback
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
    main()

