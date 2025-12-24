"""
Script to find shows with ShowClass data but missing Class 1, then scrape Class 1 data
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

# Import necessary functions from scrape_class_results.py
from scrape_class_results import (
    setup_driver,
    get_db_connection,
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
    reconnect_browser_and_navigate
)

def get_shows_missing_class1(conn):
    """Get shows that have ShowClass data but are missing Class 1
    
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
            -- But does NOT have Class 1
            AND NOT EXISTS (
                SELECT 1
                FROM sResults.ShowClass sc2
                WHERE sc2.ShowListID = sl.ID
                AND sc2.Class = '1'
            )
            ORDER BY sl.ID
        """)
        
        show_data = [(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]
        cursor.close()
        print(f"[OK] Found {len(show_data)} shows with ShowClass data but missing Class 1")
        return show_data
    except Exception as e:
        print(f"[ERROR] Error getting shows missing Class 1: {e}")
        import traceback
        traceback.print_exc()
        return []


def scrape_class1_for_show(driver, show_list_id, show_guid, year, show_name, conn):
    """Scrape Class 1 summary data for a specific show using the same logic as scrape_class_results.py
    
    Args:
        driver: WebDriver instance
        show_list_id: ID from ShowList table
        show_guid: ShowGUID string
        year: Year string
        show_name: Show name string
        conn: Database connection
    
    Returns: (driver) - just return driver, no results count needed
    """
    print(f"\n{'='*60}")
    print(f"Scraping Class 1 summary for ShowGUID: {show_guid} (Year: {year})")
    print(f"Show: {show_name}")
    print(f"{'='*60}")
    
    try:
        # Navigate to ShowSelector page first (reuse logic from scrape_class_results.py)
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        if 'ShowSelector' not in driver.current_url:
            print("  Navigating to ShowSelector page...")
            driver.get(show_selector_url)
            time.sleep(3)
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(driver):
            print(f"  [WARNING] Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            driver.get(class_results_url)
            time.sleep(3)
        else:
            # Select the year
            if not select_year(driver, year):
                print(f"  [WARNING] Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                driver.get(class_results_url)
                time.sleep(3)
            else:
                # Find and click the show row to navigate to ClassResults
                if not find_and_click_show_row(driver, show_guid, year, show_name):
                    print(f"  [WARNING] Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    driver.get(class_results_url)
                    time.sleep(3)
        
        # Wait for the ClassResults page to load - look for the grid table
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
            )
        except TimeoutException:
            print(f"  [WARNING] Grid table not found after 10 seconds")
        
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
                            print(f"  Found grid using selector: {selector} ({tr_count} rows)")
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
                            print(f"  Found grid using fallback method ({tr_count} rows)")
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
                    print(f"  Found grid using last resort method ({max_data_rows} data rows)")
            except:
                pass
        
        if not grid:
            print(f"  [ERROR] Could not find results grid for ShowGUID: {show_guid}")
            return driver
        
        # Get column mapping for class summary
        class_column_map = get_column_indices_for_class_grid(grid)
        print(f"  Class column mapping: {class_column_map}")
        
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
        
        print(f"  Found {len(class_rows)} class summary rows")
        
        # Extract class summaries and look for Class 1 (reuse PASS 1 logic from scrape_class_results.py)
        print(f"  Extracting class summaries and looking for Class 1...")
        class1_found = False
        
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

                # Check if this is Class 1
                class_value = class_summary.get('Class', '').strip()
                
                # Debug: print first few rows to see what we're getting
                if row_idx <= 5:
                    print(f"    Row {row_idx}: Class='{class_value}', ClassName='{class_summary.get('Class Name', '')[:30]}', Entries='{entries}', Placings='{placings}'")
                
                # If mapped column didn't work, try to find class number in cells directly
                if not class_value or class_value == '#' or class_value == '':
                    # Try searching cells for class number '1'
                    for cell in cells[1:6]:  # Skip first cell (command column), check next 5
                        cell_text = cell.text.strip()
                        if cell_text == '1':
                            class_value = '1'
                            print(f"    Found Class 1 in alternative column: '{cell_text}'")
                            break
                
                if class_value == '1':
                    print(f"    [OK] Found Class 1: Class Name: {class_summary.get('Class Name', 'N/A')[:50]}, Entries: {entries}, Placings: {placings}")
                    
                    # Update class_summary with the found class value
                    class_summary['Class'] = '1'
                    
                    # Save ShowClass to database
                    show_class_id = get_or_create_showclass(conn, show_list_id, class_summary)
                    if show_class_id:
                        print(f"      [OK] Saved Class 1 summary to database (ShowClass ID: {show_class_id})")
                        class1_found = True
                        break  # Found Class 1, we're done
                    else:
                        print(f"      [ERROR] Could not create/get ShowClass for Class 1")
                
            except Exception as e:
                continue
        
        if not class1_found:
            print(f"  [WARNING] Could not find or save Class 1 in this show")
        
        print(f"  [OK] Completed processing Class 1 for ShowGUID {show_guid}")
        return driver
        
    except Exception as e:
        print(f"  [ERROR] Error scraping Class 1 for ShowGUID {show_guid}: {e}")
        import traceback
        traceback.print_exc()
        return driver

def main():
    """Main function"""
    print("\n" + "=" * 60)
    print("Fix Missing Class 1 - Scraper")
    print("=" * 60 + "\n")
    
    driver = None
    conn = None
    
    try:
        # Setup driver
        print("Initializing browser (headless mode)...")
        driver = setup_driver(headless=True)
        print("  [OK] Browser initialized\n")
        
        # Connect to database
        print("Connecting to database...")
        conn = get_db_connection()
        print("[OK] Connected to database\n")
        
        # Get shows missing Class 1
        print("Finding shows with ShowClass data but missing Class 1...")
        show_data_list = get_shows_missing_class1(conn)
        
        if not show_data_list:
            print("[OK] No shows found missing Class 1. All shows with ShowClass data have Class 1.")
            return
        
        print(f"\nFound {len(show_data_list)} shows missing Class 1\n")
        
        # Process each show
        for idx, (show_list_id, show_guid, year, show_name) in enumerate(show_data_list, 1):
            print(f"\nProcessing show {idx}/{len(show_data_list)}...")
            driver = scrape_class1_for_show(driver, show_list_id, show_guid, year, show_name, conn)
            
            # Small delay between shows
            time.sleep(2)
        
        print(f"\n{'='*60}")
        print(f"Processing complete! Processed {len(show_data_list)} shows")
        print(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        print("\n\n[WARNING] Processing interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            try:
                conn.close()
                print("[OK] Database connection closed")
            except:
                pass
        if driver:
            print("\nClosing browser...")
            driver.quit()

if __name__ == '__main__':
    main()

