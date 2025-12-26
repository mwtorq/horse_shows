"""
Scraper to collect horse show data by year (2025-2015)
Captures: Show Date (start/end), Show Name, Location, State/Prov, Governing Body, ShowGUID
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import sys
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import re
import pyodbc

def setup_driver(headless=True):
    """Setup Chrome WebDriver"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        return driver
    except Exception as e:
        print(f"Error setting up driver: {e}")
        if headless:
            print("Retrying without headless mode...")
            return setup_driver(headless=False)
        raise

def activate_shows_by_year_tab(driver):
    """Activate the 'Shows By Year' tab"""
    print("Activating 'Shows By Year' tab...")
    
    try:
        time.sleep(3)
        tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
        
        shows_by_year_tab = None
        for tab in tabs:
            if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                shows_by_year_tab = tab
                break
        
        if not shows_by_year_tab:
            shows_by_year_tab = driver.find_element(By.XPATH, 
                "//li[contains(@class, 'dxtc-tab')]//span[contains(text(), 'Shows By Year')]/ancestor::li[1]")
        
        classes = shows_by_year_tab.get_attribute('class') or ''
        if 'dxtc-activeTab' not in classes:
            link = shows_by_year_tab.find_element(By.CSS_SELECTOR, "a.dxtc-link")
            driver.execute_script("arguments[0].scrollIntoView(true);", link)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", link)
            time.sleep(4)
        
        return True
    except Exception as e:
        print(f"Error activating tab: {e}")
        return False

def select_year(driver, year):
    """Select a specific year in the year picker"""
    print(f"\nSelecting year {year}...")
    
    try:
        time.sleep(2)
        
        # Find the year picker element
        year_element = None
        year_picker_ids = [
            "MainContent_panFilter_ddShowYear_I",
            "MainContent_panFilter_ddShowYear",
            "ddShowYear_I",
            "ddShowYear",
        ]
        
        for picker_id in year_picker_ids:
            try:
                year_element = driver.find_element(By.ID, picker_id)
                break
            except:
                continue
        
        if not year_element:
            print(f"  [ERROR] Could not find year picker for year {year}")
            return False
        
        element_id = year_element.get_attribute('id') or ''
        year_value = str(year)
        
        print(f"  Setting year picker to {year_value}...")
        
        # Set the value using JavaScript
        driver.execute_script(f"arguments[0].value = '{year_value}';", year_element)
        driver.execute_script(f"arguments[0].setAttribute('value', '{year_value}');", year_element)
        
        # Get control ID for DevExpress event
        control_id = element_id
        if element_id.endswith('_I'):
            control_id = element_id[:-2]
        
        # Trigger DevExpress change event
        driver.execute_script(f"""
            var elem = arguments[0];
            elem.dispatchEvent(new Event('input', {{bubbles: true}}));
            elem.dispatchEvent(new Event('change', {{bubbles: true}}));
            elem.dispatchEvent(new Event('blur', {{bubbles: true}}));
            if (typeof ASPx !== 'undefined' && typeof ASPx.ETextChanged === 'function') {{
                ASPx.ETextChanged('{control_id}');
            }}
        """, year_element)
        
        # Wait for grid to update
        time.sleep(3)
        
        # Verify the value was set
        current_value = driver.execute_script("return arguments[0].value;", year_element)
        if str(year) in str(current_value):
            print(f"  [OK] Year {year} selected")
            return True
        else:
            print(f"  [WARNING] Year may not have been set correctly. Current value: {current_value}")
            return True  # Continue anyway
        
    except Exception as e:
        print(f"  [ERROR] Error selecting year {year}: {e}")
        return False

def parse_date_range(date_str):
    """Parse a date range string into start and end dates"""
    if not date_str or not date_str.strip():
        return '', ''
    
    date_str = date_str.strip()
    
    # Handle various date formats
    # Examples: 
    # "1/15/2024 - 1/20/2024"
    # "Jan 15, 2024 - Jan 20, 2024"
    # "Nov 29, 2025 - Nov 30, 2025"
    # "Dec 28, 2025 - Dec 31, 2025"
    
    # Try to split on common separators (try longer separators first to avoid partial matches)
    # Important: try " - " (space-dash-space) first as it's the most common format
    separators = [' - ', ' -', '- ', '-', ' to ', ' through ', ' thru ']
    
    for sep in separators:
        if sep in date_str:
            parts = date_str.split(sep, 1)  # Split only on first occurrence
            if len(parts) == 2:
                start_date = parts[0].strip()
                end_date = parts[1].strip()
                # Return the dates as-is (they're already formatted)
                return start_date, end_date
    
    # If no separator found, assume it's a single date (use as both start and end)
    return date_str, date_str

def get_column_indices(grid):
    """Determine column indices by inspecting header row"""
    column_map = {
        'Show Date': None,
        'Show Name': None,
        'Location': None,
        'State/Prov': None,
        'Governing Body': None,
    }
    
    try:
        # Find header row
        header_rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='HeaderRow'], tr.dxgvHeaderRow")
        if header_rows:
            header_cells = header_rows[0].find_elements(By.TAG_NAME, "th, td")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip().lower()
                # Skip command column (first column is usually buttons/icons)
                if idx == 0 and ('button' in cell_text or cell_text == ''):
                    continue
                # Map based on header text (adjusting for command column offset)
                col_idx = idx
                if 'date' in cell_text and 'show' in cell_text:
                    column_map['Show Date'] = col_idx
                elif 'name' in cell_text and 'show' in cell_text:
                    column_map['Show Name'] = col_idx
                elif 'location' in cell_text:
                    column_map['Location'] = col_idx
                elif 'state' in cell_text or 'prov' in cell_text:
                    column_map['State/Prov'] = col_idx
                elif 'governing' in cell_text or 'body' in cell_text:
                    column_map['Governing Body'] = col_idx
    except:
        pass
    
    # Based on the HTML structure provided: 
    # Column 0 = Command column (skip), 1 = Date, 2 = Name, 3 = Location, 4 = State, 5 = Body
    if all(v is None for v in column_map.values()):
        column_map = {
            'Show Date': 1,
            'Show Name': 2,
            'Location': 3,
            'State/Prov': 4,
            'Governing Body': 5,
        }
    
    return column_map

def save_single_show_to_database(show_data, conn):
    """Save a single show to the database"""
    if not conn or not show_data:
        return
    
    try:
        cursor = conn.cursor()
        
        show_guid = show_data.get('ShowGUID', '')
        year = show_data.get('Year', '')
        show_name = show_data.get('Show Name', '')
        
        # Check if record already exists
        if show_guid:
            cursor.execute("""
                SELECT ID FROM sResults.ShowList 
                WHERE ShowGUID = ? AND Year = ?
            """, show_guid, year)
            existing = cursor.fetchone()
        else:
            cursor.execute("""
                SELECT ID FROM sResults.ShowList 
                WHERE ShowName = ? AND Year = ?
            """, show_name, year)
            existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            cursor.execute("""
                UPDATE sResults.ShowList 
                SET ShowName = ?,
                    StartDate = ?,
                    EndDate = ?,
                    ShowDate = ?,
                    ShowLocation = ?,
                    StateProv = ?,
                    GoverningBody = ?,
                    ShowGUID = ?,
                    UpdatedDate = GETDATE()
                WHERE ID = ?
            """, 
                show_data.get('Show Name', ''),
                show_data.get('Start Date', ''),
                show_data.get('End Date', ''),
                show_data.get('Show Date', ''),
                show_data.get('Show Location', ''),
                show_data.get('State/Prov', ''),
                show_data.get('Governing Body', ''),
                show_guid,
                existing[0]
            )
        else:
            # Insert new record
            cursor.execute("""
                INSERT INTO sResults.ShowList 
                (Year, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody, ShowGUID)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                year,
                show_data.get('Show Name', ''),
                show_data.get('Start Date', ''),
                show_data.get('End Date', ''),
                show_data.get('Show Date', ''),
                show_data.get('Show Location', ''),
                show_data.get('State/Prov', ''),
                show_data.get('Governing Body', ''),
                show_guid
            )
        
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"    [WARNING] Error saving show to database: {e}")
        conn.rollback()

def extract_show_data_from_row(row_element, driver, base_url, column_map, year, conn=None):
    """Extract data from a single grid row and get ShowGUID by clicking the show name"""
    try:
        # Find all cells in the row
        cells = row_element.find_elements(By.TAG_NAME, "td")
        if len(cells) < 3:
            return None
        
        show_data = {}
        
        # Extract data from cells using column mapping
        # Column structure: 0=Command, 1=Date, 2=Name, 3=Location, 4=State, 5=Body
        try:
            show_date_idx = column_map.get('Show Date', 1)
            show_name_idx = column_map.get('Show Name', 2)
            location_idx = column_map.get('Location', 3)
            state_idx = column_map.get('State/Prov', 4)
            body_idx = column_map.get('Governing Body', 5)
            
            # Extract raw text from each cell
            show_data['Show Date'] = cells[show_date_idx].text.strip() if show_date_idx is not None and len(cells) > show_date_idx else ''
            show_data['Show Name'] = cells[show_name_idx].text.strip() if show_name_idx is not None and len(cells) > show_name_idx else ''
            location_text = cells[location_idx].text.strip() if location_idx is not None and len(cells) > location_idx else ''
            state_text = cells[state_idx].text.strip() if state_idx is not None and len(cells) > state_idx else ''
            show_data['Governing Body'] = cells[body_idx].text.strip() if body_idx is not None and len(cells) > body_idx else ''
            
            # Combine Location and State/Prov for Show Location field (e.g., "Katy, TX")
            if location_text and state_text:
                show_data['Show Location'] = f"{location_text}, {state_text}"
            elif location_text:
                show_data['Show Location'] = location_text
            else:
                show_data['Show Location'] = ''
            
            # Store State/Prov separately
            show_data['State/Prov'] = state_text
            
        except Exception as e:
            print(f"    [WARNING] Error extracting cell data: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # Parse start and end dates from Show Date field
        show_date_str = show_data.get('Show Date', '')
        start_date, end_date = parse_date_range(show_date_str)
        # Ensure we have strings (not None)
        show_data['Start Date'] = start_date if start_date else ''
        show_data['End Date'] = end_date if end_date else ''
        
        # Debug output to verify date parsing
        if show_date_str and (not start_date or not end_date or start_date == end_date == show_date_str):
            print(f"    [DEBUG] Date string: '{show_date_str}' -> Start: '{start_date}', End: '{end_date}'")
        
        # Get ShowGUID by clicking on the row to navigate
        show_data['ShowGUID'] = ''
        original_url = driver.current_url  # Store outside try block for exception handler
        try:
            # Click on the row itself (not a specific cell) to navigate
            show_name = show_data.get('Show Name', 'Unknown')
            print(f"    Clicking row for '{show_name}' to get ShowGUID...")
            if conn:
                log_import_activity(conn, 'scrape_shows_by_year.py', action='NAVIGATE_TO_SHOW', 
                                  additional_info=f'Year: {year}, Show: {show_name[:50]}, Extracting ShowGUID')
            
            # Store current URL and window handles
            original_handles = driver.window_handles
            
            # Find a clickable element in the row - try the Show Name cell first
            show_name_idx = column_map.get('Show Name', 2)
            clickable_cell = cells[show_name_idx] if show_name_idx is not None and len(cells) > show_name_idx else cells[2] if len(cells) > 2 else None
            
            # Try to find a link in the row
            link = None
            if clickable_cell:
                try:
                    link = clickable_cell.find_element(By.TAG_NAME, "a")
                except NoSuchElementException:
                    # If no link in Show Name cell, try clicking the row itself
                    pass
            
            # If no link found, try clicking the row
            if not link:
                # Use JavaScript to click the row - DevExpress rows often have onclick handlers
                driver.execute_script("arguments[0].click();", row_element)
            else:
                # Click the link
                driver.execute_script("arguments[0].click();", link)
            
            # Wait for navigation
            time.sleep(3)
            
            # Check if new window/tab opened
            current_handles = driver.window_handles
            if len(current_handles) > len(original_handles):
                # New window opened, switch to it
                new_handle = [h for h in current_handles if h not in original_handles][0]
                driver.switch_to.window(new_handle)
                time.sleep(1)
            
            # Get ShowGUID from current URL
            current_url = driver.current_url
            print(f"    Navigated to: {current_url[:100]}...")
            
            # Extract ShowGUID from URL
            parsed = urlparse(current_url)
            params = parse_qs(parsed.query)
            if 'ShowGUID' in params:
                show_data['ShowGUID'] = params['ShowGUID'][0]
                print(f"    [OK] Extracted ShowGUID: {show_data['ShowGUID']}")
                if conn:
                    log_import_activity(conn, 'scrape_shows_by_year.py', action='SHOWGUID_EXTRACTED', 
                                      additional_info=f'Year: {year}, Show: {show_name[:50]}, ShowGUID: {show_data["ShowGUID"]}')
            else:
                # Try regex pattern
                guid_match = re.search(r'ShowGUID[=:]([a-fA-F0-9-]+)', current_url)
                if guid_match:
                    show_data['ShowGUID'] = guid_match.group(1)
                    print(f"    [OK] Extracted ShowGUID (regex): {show_data['ShowGUID']}")
                    if conn:
                        log_import_activity(conn, 'scrape_shows_by_year.py', action='SHOWGUID_EXTRACTED', 
                                          additional_info=f'Year: {year}, Show: {show_name[:50]}, ShowGUID: {show_data["ShowGUID"]} (regex)')
            
            # Navigate back to ShowSelector page with year selected
            if len(current_handles) > len(original_handles):
                # New window/tab was opened, close it and switch back
                driver.close()
                driver.switch_to.window(original_handles[0])
                time.sleep(1)
            else:
                # Navigate back using browser back button
                driver.back()
                time.sleep(2)
            
            # Always ensure we're on ShowSelector page with Shows By Year tab active and year selected
            # Check current URL
            current_url_after_back = driver.current_url
            if 'ShowSelector' not in current_url_after_back:
                # Not on ShowSelector page, navigate to it
                driver.get(original_url)
                time.sleep(2)
            
            # Ensure Shows By Year tab is active
            try:
                # Check if Shows By Year tab is active
                active_tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-activeTab")
                is_shows_by_year_active = False
                if active_tabs:
                    active_text = active_tabs[0].text.strip()
                    if 'Shows By Year' in active_text or 'By Year' in active_text:
                        is_shows_by_year_active = True
                
                if not is_shows_by_year_active:
                    print(f"    Reactivating 'Shows By Year' tab...")
                    activate_shows_by_year_tab(driver)
            except:
                # If we can't check, just try to activate it
                print(f"    Reactivating 'Shows By Year' tab (fallback)...")
                activate_shows_by_year_tab(driver)
            
            # Ensure the correct year is still selected
            try:
                time.sleep(1)
                year_picker_id = "MainContent_panFilter_ddShowYear_I"
                year_element = driver.find_element(By.ID, year_picker_id)
                current_year_value = driver.execute_script("return arguments[0].value;", year_element)
                
                if str(year) not in str(current_year_value):
                    print(f"    Reselecting year {year}...")
                    select_year(driver, year)
            except Exception as e:
                print(f"    [WARNING] Could not verify/reselect year: {e}")
                # Try to reselect anyway
                select_year(driver, year)
            
        except Exception as e:
            print(f"    [WARNING] Error getting ShowGUID: {e}")
            # Try to get back to the right page
            try:
                # Navigate back to ShowSelector page
                if 'ShowSelector' not in driver.current_url:
                    driver.get(original_url)
                    time.sleep(2)
                
                # Reactivate tab and reselect year
                activate_shows_by_year_tab(driver)
                select_year(driver, year)
            except Exception as e2:
                print(f"    [ERROR] Failed to return to ShowSelector page: {e2}")
                pass
        
        # Add year to show_data before saving
        show_data['Year'] = year
        
        # Save to database immediately after capturing
        if conn:
            try:
                save_single_show_to_database(show_data, conn)
                # Log individual show save
                log_import_activity(conn, 'scrape_shows_by_year.py', target_table='ShowList', 
                                  action='INSERT_OR_UPDATE', row_count=1,
                                  additional_info=f"ShowGUID: {show_data.get('ShowGUID', 'N/A')}, Year: {year}")
            except Exception as e:
                print(f"    [WARNING] Failed to save show to database: {e}")
                log_import_activity(conn, 'scrape_shows_by_year.py', target_table='ShowList', 
                                  action='ERROR', error_detail=str(e),
                                  additional_info=f"Show: {show_data.get('Show Name', 'Unknown')}, Year: {year}")
        
        return show_data
        
    except Exception as e:
        print(f"    [ERROR] Error extracting row data: {e}")
        return None

def scrape_shows_for_year(driver, year, conn=None):
    """Scrape all shows for a given year"""
    print(f"\n{'='*60}")
    print(f"Scraping shows for year {year}")
    print(f"{'='*60}")
    
    # Log year processing start
    if conn:
        log_import_activity(conn, 'scrape_shows_by_year.py', action='PROCESS_YEAR_START', 
                          additional_info=f'Year: {year}')
    
    if not select_year(driver, year):
        print(f"  [ERROR] Failed to select year {year}, skipping...")
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='ERROR', 
                              error_detail=f'Failed to select year {year}')
        return []
    
    shows = []
    
    try:
        # Wait for grid to load
        time.sleep(3)
        
        # Find the grid - DevExpress GridView typically has ID containing 'grMaster'
        grid = None
        grid_selectors = [
            "table[id*='grMaster'][id*='MainTable']",
            "table[id*='grMaster']",
            "table[id*='MainContent'][id*='gr']",
            "table.dxgvTable",
            "table[id*='DXMainTable']",
        ]
        
        for selector in grid_selectors:
            try:
                grids = driver.find_elements(By.CSS_SELECTOR, selector)
                for g in grids:
                    if g.is_displayed():
                        grid = g
                        print(f"  Found grid using selector: {selector}")
                        break
                if grid:
                    break
            except:
                continue
        
        if not grid:
            print(f"  [ERROR] Could not find grid for year {year}")
            # Try to find any table as fallback
            try:
                all_tables = driver.find_elements(By.TAG_NAME, "table")
                for table in all_tables:
                    if table.is_displayed() and len(table.find_elements(By.TAG_NAME, "tr")) > 1:
                        grid = table
                        print(f"  Found grid using fallback method")
                        break
            except:
                pass
        
        if not grid:
            print(f"  [ERROR] Could not find grid for year {year}")
            if conn:
                log_import_activity(conn, 'scrape_shows_by_year.py', action='ERROR', 
                                  error_detail=f'Could not find grid for year {year}')
            return []
        
        print(f"  Found grid, extracting rows...")
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='GRID_FOUND', 
                              additional_info=f'Year: {year}')
        
        # Find all data rows (skip header and filter rows)
        # DevExpress GridView data rows typically have ID containing 'DataRow'
        rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
        
        # Alternative: get all rows and filter out header/filter rows
        if not rows or len(rows) == 0:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            rows = []
            for r in all_rows:
                row_id = r.get_attribute('id') or ''
                row_class = r.get_attribute('class') or ''
                # Include data rows, exclude header/filter rows
                if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                    rows.append(r)
        
        print(f"  Found {len(rows)} data rows")
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='GRID_ROWS_FOUND', 
                              additional_info=f'Year: {year}, Rows found: {len(rows)}')
        
        # Determine column indices from header
        column_map = get_column_indices(grid)
        print(f"  Column mapping: {column_map}")
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='COLUMN_MAPPING', 
                              additional_info=f'Year: {year}, Column mapping: {column_map}')
        
        # Debug: print first row structure if rows found
        if rows and len(rows) > 0:
            try:
                first_row = rows[0]
                first_cells = first_row.find_elements(By.TAG_NAME, "td")
                print(f"  First row has {len(first_cells)} cells")
                for idx, cell in enumerate(first_cells[:6]):  # Print first 6 cells
                    print(f"    Cell {idx}: '{cell.text[:50]}...'")
            except:
                pass
        
        # Extract data from each row
        # Use index-based approach to re-find rows after each navigation
        total_rows = len(rows)
        row_idx = 1  # 1-based index for display
        
        while row_idx <= total_rows:
            try:
                print(f"  Processing row {row_idx}/{total_rows}...")
                
                # Re-find grid and rows before processing each row (rows become stale after navigation)
                try:
                    grid = driver.find_element(By.CSS_SELECTOR, "table[id*='grMaster'][id*='MainTable'], table[id*='grMaster'], table.dxgvTable")
                    rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                    if len(rows) != total_rows:
                        total_rows = len(rows)
                        print(f"    [NOTE] Row count updated to {total_rows}")
                    
                    # Get the current row (convert to 0-based index)
                    if row_idx > len(rows):
                        print(f"    [WARNING] Row {row_idx} exceeds available rows ({len(rows)}), stopping")
                        break
                    
                    row = rows[row_idx - 1]  # Convert to 0-based
                    
                except Exception as e:
                    print(f"    [ERROR] Could not re-find grid/rows: {e}")
                    row_idx += 1
                    continue
                
                show_data = extract_show_data_from_row(row, driver, driver.current_url, column_map, year, conn)
                if show_data:
                    # Year is already set in extract_show_data_from_row before saving
                    shows.append(show_data)
                    
                    # Report the data as we collect it
                    print(f"    [COLLECTED] {show_data.get('Show Name', 'N/A')}")
                    print(f"      Date: {show_data.get('Start Date', 'N/A')} - {show_data.get('End Date', 'N/A')}")
                    print(f"      Location: {show_data.get('Show Location', 'N/A')}")
                    print(f"      Governing Body: {show_data.get('Governing Body', 'N/A')}")
                    print(f"      ShowGUID: {show_data.get('ShowGUID', 'N/A')}")
                    if conn:
                        print(f"      [DB] Saved to database")
                        # Log show extraction (save is already logged in extract_show_data_from_row)
                        log_import_activity(conn, 'scrape_shows_by_year.py', action='EXTRACT_SHOW', 
                                          target_table='ShowList',
                                          additional_info=f'Year: {year}, Show: {show_data.get("Show Name", "N/A")[:50]}, ShowGUID: {show_data.get("ShowGUID", "N/A")}, Row {row_idx}/{total_rows}')
                
                # Move to next row
                row_idx += 1
                
                # Small delay between rows
                time.sleep(0.5)
                
            except StaleElementReferenceException:
                print(f"    [WARNING] Stale element for row {row_idx}, will re-find on next iteration...")
                row_idx += 1  # Move to next row, will re-find on next iteration
                time.sleep(1)
            except Exception as e:
                print(f"    [ERROR] Error processing row {row_idx}: {e}")
                import traceback
                traceback.print_exc()
                row_idx += 1  # Move to next row
                continue
        
        print(f"  [OK] Extracted {len(shows)} shows for year {year}")
        
        # Log year processing completion
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='PROCESS_YEAR_COMPLETE', 
                              target_table='ShowList', row_count=len(shows),
                              additional_info=f'Year: {year}, Shows extracted: {len(shows)}')
        
    except Exception as e:
        print(f"  [ERROR] Error scraping year {year}: {e}")
        import traceback
        traceback.print_exc()
    
    return shows

def get_db_connection():
    """Get SQL Server database connection, creating database if needed"""
    drivers = [
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 18 for SQL Server',
        'SQL Server',
        'SQL Server Native Client 11.0',
    ]
    
    for driver in drivers:
        try:
            # First connect to master to create database if needed
            conn_str_master = f'DRIVER={{{driver}}};SERVER=localhost\\SQLEXPRESS;DATABASE=master;Trusted_Connection=yes;'
            conn_master = pyodbc.connect(conn_str_master)
            cursor = conn_master.cursor()
            
            # Check if HorseShows database exists, create if not
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'HorseShows')
                BEGIN
                    CREATE DATABASE HorseShows
                END
            """)
            conn_master.commit()
            cursor.close()
            conn_master.close()
            
            # Now connect to HorseShows database
            conn_str = f'DRIVER={{{driver}}};SERVER=localhost\\SQLEXPRESS;DATABASE=HorseShows;Trusted_Connection=yes;'
            conn = pyodbc.connect(conn_str)
            print(f"[OK] Connected to HorseShows database using driver: {driver}")
            return conn
        except Exception as e:
            if driver == drivers[-1]:  # Last driver
                print(f"[ERROR] Database connection failed with all drivers: {e}")
                raise
            continue

def create_importlog_table_if_not_exists(conn):
    """Create the ImportLog table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ImportLog'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating sResults.ImportLog table...")
            cursor.execute("""
                CREATE TABLE sResults.ImportLog (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    LogTimestamp DATETIME DEFAULT GETDATE(),
                    OriginatingScript NVARCHAR(200) NOT NULL,
                    TargetTable NVARCHAR(200),
                    Action NVARCHAR(100) NOT NULL,
                    [RowCount] INT,
                    ErrorDetail NVARCHAR(MAX),
                    AdditionalInfo NVARCHAR(MAX)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_ImportLog_Timestamp ON sResults.ImportLog(LogTimestamp)")
            cursor.execute("CREATE INDEX IX_ImportLog_Script ON sResults.ImportLog(OriginatingScript)")
            cursor.execute("CREATE INDEX IX_ImportLog_TargetTable ON sResults.ImportLog(TargetTable)")
            
            conn.commit()
            print("[OK] ImportLog table created successfully")
        else:
            print("[OK] ImportLog table already exists")
        
        cursor.close()
    except Exception as e:
        print(f"[ERROR] Error creating ImportLog table: {e}")
        raise

def log_import_activity(conn, script_name, target_table=None, action='', row_count=None, error_detail=None, additional_info=None):
    """Log import activity to ImportLog table
    
    Args:
        conn: Database connection
        script_name: Name of the originating script (e.g., 'scrape_shows_by_year.py')
        target_table: Target table name (e.g., 'ShowList')
        action: Action description (e.g., 'INSERT', 'UPDATE', 'START', 'COMPLETE', 'ERROR')
        row_count: Number of rows affected
        error_detail: Error message if any
        additional_info: Additional information (JSON string or text)
    """
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sResults.ImportLog 
            (OriginatingScript, TargetTable, Action, [RowCount], ErrorDetail, AdditionalInfo)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            script_name,
            target_table,
            action,
            row_count,
            error_detail,
            additional_info
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        # Don't raise - logging failures shouldn't break the main process
        print(f"[WARNING] Failed to log import activity: {e}")

def create_table_if_not_exists(conn):
    """Create the ShowList table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        
        # Create schema if it doesn't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'sResults')
            BEGIN
                EXEC('CREATE SCHEMA sResults')
            END
        """)
        conn.commit()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowList'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating sResults.ShowList table...")
            cursor.execute("""
                CREATE TABLE sResults.ShowList (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    Year INT NOT NULL,
                    ShowName NVARCHAR(500) NOT NULL,
                    StartDate NVARCHAR(50),
                    EndDate NVARCHAR(50),
                    ShowDate NVARCHAR(100),
                    ShowLocation NVARCHAR(500),
                    StateProv NVARCHAR(50),
                    GoverningBody NVARCHAR(200),
                    ShowGUID NVARCHAR(100),
                    CreatedDate DATETIME DEFAULT GETDATE(),
                    UpdatedDate DATETIME DEFAULT GETDATE()
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_ShowList_Year ON sResults.ShowList(Year)")
            cursor.execute("CREATE INDEX IX_ShowList_ShowGUID ON sResults.ShowList(ShowGUID)")
            cursor.execute("CREATE INDEX IX_ShowList_ShowName ON sResults.ShowList(ShowName)")
            
            conn.commit()
            print("[OK] Table created successfully")
        else:
            print("[OK] Table already exists")
        
        cursor.close()
    except Exception as e:
        print(f"[ERROR] Error creating table: {e}")
        raise

def save_to_database(all_shows, conn):
    """Save all collected show data to SQL Server database"""
    if not all_shows:
        print("No data to save to database.")
        return
    
    try:
        cursor = conn.cursor()
        
        # Clear existing data (optional - comment out if you want to keep existing data)
        # cursor.execute("DELETE FROM sResults.ShowList")
        # conn.commit()
        # print("Cleared existing data from table")
        
        inserted_count = 0
        updated_count = 0
        
        for show in all_shows:
            try:
                # Check if record already exists (by ShowGUID and Year)
                show_guid = show.get('ShowGUID', '')
                year = show.get('Year', '')
                show_name = show.get('Show Name', '')
                
                if show_guid:
                    cursor.execute("""
                        SELECT ID FROM sResults.ShowList 
                        WHERE ShowGUID = ? AND Year = ?
                    """, show_guid, year)
                    existing = cursor.fetchone()
                else:
                    # If no ShowGUID, check by name and year
                    cursor.execute("""
                        SELECT ID FROM sResults.ShowList 
                        WHERE ShowName = ? AND Year = ?
                    """, show_name, year)
                    existing = cursor.fetchone()
                
                if existing:
                    # Update existing record
                    cursor.execute("""
                        UPDATE sResults.ShowList 
                        SET ShowName = ?,
                            StartDate = ?,
                            EndDate = ?,
                            ShowDate = ?,
                            ShowLocation = ?,
                            StateProv = ?,
                            GoverningBody = ?,
                            ShowGUID = ?,
                            UpdatedDate = GETDATE()
                        WHERE ID = ?
                    """, 
                        show.get('Show Name', ''),
                        show.get('Start Date', ''),
                        show.get('End Date', ''),
                        show.get('Show Date', ''),
                        show.get('Show Location', ''),
                        show.get('State/Prov', ''),
                        show.get('Governing Body', ''),
                        show_guid,
                        existing[0]
                    )
                    updated_count += 1
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO sResults.ShowList 
                        (Year, ShowName, StartDate, EndDate, ShowDate, ShowLocation, StateProv, GoverningBody, ShowGUID)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        year,
                        show.get('Show Name', ''),
                        show.get('Start Date', ''),
                        show.get('End Date', ''),
                        show.get('Show Date', ''),
                        show.get('Show Location', ''),
                        show.get('State/Prov', ''),
                        show.get('Governing Body', ''),
                        show_guid
                    )
                    inserted_count += 1
                
            except Exception as e:
                print(f"  [WARNING] Error saving show '{show.get('Show Name', 'Unknown')}': {e}")
                continue
        
        conn.commit()
        cursor.close()
        print(f"\n[OK] Database save complete: {inserted_count} inserted, {updated_count} updated")
        
    except Exception as e:
        print(f"[ERROR] Error saving to database: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise

def parse_years(years_arg):
    """Parse years argument into a list of years
    
    Supports:
    - Single year: 2024
    - Range: 2025-2020 (inclusive, descending)
    - Comma-separated: 2025,2024,2023
    - Range with step: 2025-2020:2 (step of 2)
    
    Returns: List of years (descending order)
    """
    if not years_arg:
        return list(range(2025, 2014, -1))  # Default: 2025 down to 2015
    
    years = []
    
    # Handle comma-separated values
    parts = [p.strip() for p in years_arg.split(',')]
    
    for part in parts:
        if '-' in part:
            # Range format: start-end or start-end:step
            range_parts = part.split(':')
            step = -1  # Default step (descending)
            if len(range_parts) > 1:
                step = -int(range_parts[1])  # Negative for descending
            
            range_values = range_parts[0].split('-')
            if len(range_values) == 2:
                start = int(range_values[0].strip())
                end = int(range_values[1].strip())
                # Ensure descending order
                if start < end:
                    start, end = end, start
                    step = abs(step) if step > 0 else -abs(step)
                years.extend(range(start, end - 1, step))
            else:
                raise ValueError(f"Invalid range format: {part}")
        else:
            # Single year
            years.append(int(part.strip()))
    
    # Remove duplicates, sort descending, and return
    return sorted(set(years), reverse=True)

def main(years_arg=None):
    """Main function
    
    Args:
        years_arg: Optional string specifying years to scrape (e.g., "2025-2020" or "2025,2024,2023")
                   If None, uses default range 2025-2015
    """
    url = 'https://horseshowsonline.com/ShowSelector.aspx'
    
    try:
        years = parse_years(years_arg)
    except ValueError as e:
        print(f"[ERROR] Invalid years format: {e}")
        print("Supported formats:")
        print("  - Single year: 2024")
        print("  - Range: 2025-2020")
        print("  - Comma-separated: 2025,2024,2023")
        print("  - Range with step: 2025-2020:2")
        return
    
    if not years:
        print("[ERROR] No valid years specified")
        return
    
    years_str = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0])
    
    print("\n" + "=" * 60)
    print(f"HorseShowsOnline - Show Scraper (Years: {years_str})")
    print(f"Processing {len(years)} year(s): {', '.join(map(str, years))}")
    print("=" * 60 + "\n")
    
    driver = None
    all_shows = []
    
    try:
        # Setup driver
        print("Initializing browser (headless mode)...")
        driver = setup_driver(headless=True)  # Run in headless mode
        print("  [OK] Browser initialized\n")
        
        # Navigate to page
        print(f"Navigating to: {url}")
        driver.get(url)
        time.sleep(3)
        
        # Connect to database and create table BEFORE scraping starts
        conn = None
        try:
            print("Connecting to database...")
            conn = get_db_connection()
            print("[OK] Connected to database")
            
            print("Ensuring database tables exist...")
            create_importlog_table_if_not_exists(conn)
            create_table_if_not_exists(conn)
            print("[OK] Database tables verified/created")
            
            # Log script start
            log_import_activity(conn, 'scrape_shows_by_year.py', action='START', 
                              additional_info=f'Years: {years_str}, Total years: {len(years)}')
        except Exception as e:
            print(f"[WARNING] Could not connect to database: {e}")
            print("Will save to CSV only")
            import traceback
            traceback.print_exc()
            conn = None
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(driver):
            print("[ERROR] Failed to activate 'Shows By Year' tab")
            if conn:
                conn.close()
            return
        
        # Scrape each year (saves to database as each show is captured)
        for year_idx, year in enumerate(years, 1):
            shows = scrape_shows_for_year(driver, year, conn)
            all_shows.extend(shows)
            
            # Report progress
            print(f"\n[PROGRESS] Total shows collected so far: {len(all_shows)}")
            if conn:
                log_import_activity(conn, 'scrape_shows_by_year.py', action='YEAR_PROGRESS', 
                                  additional_info=f'Year {year_idx}/{len(years)}: {year}, Shows this year: {len(shows)}, Total so far: {len(all_shows)}')
            
            # Small delay between years
            time.sleep(2)
        
        # Close database connection
        if conn:
            try:
                conn.close()
                print("[OK] Database connection closed")
            except:
                pass
        
        # Final summary
        print(f"\n{'='*60}")
        print(f"Scraping complete! Total shows collected: {len(all_shows)}")
        print(f"{'='*60}\n")
        
        # Print summary
        print(f"\nSummary:")
        for year in years:
            count = len([s for s in all_shows if s.get('Year') == year])
            print(f"  Year {year}: {count} shows")
        
        # Log completion
        if conn:
            summary_info = ', '.join([f"{year}: {len([s for s in all_shows if s.get('Year') == year])}" for year in years])
            log_import_activity(conn, 'scrape_shows_by_year.py', action='COMPLETE', 
                              row_count=len(all_shows), additional_info=f'Total shows: {len(all_shows)}, Summary: {summary_info}')
        
    except KeyboardInterrupt:
        print("\n\n[WARNING] Scraping interrupted by user")
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='INTERRUPTED', 
                              error_detail='User interrupted scraping', row_count=len(all_shows) if all_shows else 0)
        if all_shows:
            # Try to save to database
            try:
                conn = get_db_connection()
                create_table_if_not_exists(conn)
                save_to_database(all_shows, conn)
                conn.close()
                print("Partial data saved to database")
            except:
                pass
    except Exception as e:
        print(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        error_trace = traceback.format_exc()
        if conn:
            log_import_activity(conn, 'scrape_shows_by_year.py', action='ERROR', 
                              error_detail=str(e), additional_info=error_trace[:4000], row_count=len(all_shows) if all_shows else 0)
        traceback.print_exc()
        if all_shows:
            # Try to save to database
            try:
                conn = get_db_connection()
                create_table_if_not_exists(conn)
                save_to_database(all_shows, conn)
                conn.close()
                print("Data saved to database before error")
            except:
                pass
    finally:
        if driver:
            print("\nClosing browser...")
            driver.quit()

if __name__ == '__main__':
    import sys
    
    years_arg = None
    
    if len(sys.argv) > 1:
        # Check for help
        if sys.argv[1].lower() in ['--help', '-h', '/?']:
            print("Usage: python scrape_shows_by_year.py [YEARS]")
            print("\nArguments:")
            print("  YEARS: Optional specification of years to scrape")
            print("\nYear formats:")
            print("  - Single year: 2024")
            print("  - Range: 2025-2020 (inclusive, descending)")
            print("  - Comma-separated: 2025,2024,2023")
            print("  - Range with step: 2025-2020:2 (step of 2)")
            print("\nExamples:")
            print("  python scrape_shows_by_year.py                    # Default: 2025-2015")
            print("  python scrape_shows_by_year.py 2024               # Single year")
            print("  python scrape_shows_by_year.py 2025-2020          # Range 2025 to 2020")
            print("  python scrape_shows_by_year.py 2025,2023,2021     # Specific years")
            print("  python scrape_shows_by_year.py 2025-2020:2        # Range with step 2")
            sys.exit(0)
        
        years_arg = sys.argv[1]
        print(f"[INFO] Years argument provided: {years_arg}")
    
    main(years_arg=years_arg)

