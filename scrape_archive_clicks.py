"""
Scrape 2014 ShowGUIDs from archive.org by clicking grid rows
This script navigates to archived ShowSelector pages and clicks each grid row
to capture the ShowGUID from the resulting navigation URL.
"""

import time
import re
import csv
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

# Archive.org URLs to scrape
ARCHIVE_URLS = [
    'https://web.archive.org/web/20141230063824/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20141113161735/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20140707072136/http://horseshowsonline.com/ShowSelector.aspx'
]

def setup_driver(headless=False):
    """Set up Chrome WebDriver"""
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver

def extract_showguid_from_url(url):
    """Extract ShowGUID from URL"""
    match = re.search(r'ShowGUID=([a-f0-9\-]+)', url, re.IGNORECASE)
    if match:
        return match.group(1)
    return None

def parse_show_date(date_text):
    """Parse show date from grid cell text"""
    if not date_text:
        return None
    
    # Look for date patterns like "Jun 16, 2014" or "Jun 16, 2014 - Jun 21, 2014"
    date_match = re.search(r'([A-Z][a-z]{2}\s+\d{1,2},\s+2014)', date_text)
    if date_match:
        return date_match.group(1)
    return date_text.strip()

def extract_showguids_from_archive_page(driver, archive_url):
    """
    Navigate to archive page and extract ShowGUIDs by clicking each grid row
    Returns list of dicts with show info
    """
    print(f"\n{'='*80}")
    print(f"Processing: {archive_url}")
    print(f"{'='*80}")
    
    try:
        driver.get(archive_url)
        print("Waiting for archive.org to load...")
        time.sleep(5)  # Wait for archive.org to load
        
        # Check current URL and page title
        print(f"Current URL: {driver.current_url}")
        print(f"Page title: {driver.title}")
        
        # Try to switch to the main content iframe if archive.org uses one
        try:
            # Archive.org sometimes uses an iframe for the archived content
            iframe = driver.find_element(By.ID, "playback")
            driver.switch_to.frame(iframe)
            print("Switched to playback iframe")
            time.sleep(2)
        except NoSuchElementException:
            print("No playback iframe, using main page")
        
        # Try to find the grid table
        print("Looking for grid table...")
        
        # Common table IDs/classes for ShowSelector
        # Archive.org uses DevExpress grids
        possible_selectors = [
            "//table[@id='ctl00_MainContent_grMaster_DXMainTable']",
            "//table[@id='ctl00_MainContent_grMaster']",
            "//table[@id='grMaster']",
            "//table[contains(@class, 'dxgvTable')]",
            "//table[contains(@class, 'Grid')]",
            "//table[@id='ContentPlaceHolder1_grMaster']",
            "//div[@class='GridPager']//ancestor::table[1]",
            "//table[.//tr[contains(@class, 'GridHeader')]]"
        ]
        
        grid_table = None
        for selector in possible_selectors:
            try:
                grid_table = driver.find_element(By.XPATH, selector)
                print(f"  Found grid using selector: {selector}")
                break
            except NoSuchElementException:
                continue
        
        if not grid_table:
            print("  ERROR: Could not find grid table with known selectors")
            
            # Debug: List all tables on the page
            all_tables = driver.find_elements(By.TAG_NAME, 'table')
            print(f"\n  Found {len(all_tables)} tables on page:")
            for idx, table in enumerate(all_tables[:10]):  # Show first 10
                table_id = table.get_attribute('id') or '(no id)'
                table_class = table.get_attribute('class') or '(no class)'
                rows = table.find_elements(By.TAG_NAME, 'tr')
                print(f"    Table {idx+1}: id='{table_id}', class='{table_class}', rows={len(rows)}")
            
            # Try to find ANY table with multiple rows
            for table in all_tables:
                rows = table.find_elements(By.TAG_NAME, 'tr')
                if len(rows) > 5:  # Likely a data table
                    print(f"\n  Trying table with {len(rows)} rows...")
                    grid_table = table
                    break
            
            if not grid_table:
                print("  ERROR: No suitable grid table found")
                return []
        
        # Find all data rows (skip header)
        # DevExpress grids use dxgvDataRow class for data rows
        rows = grid_table.find_elements(By.XPATH, ".//tr[contains(@class, 'dxgvDataRow')]")
        
        if len(rows) == 0:
            # Fallback to generic row finding
            rows = grid_table.find_elements(By.XPATH, ".//tr[td and not(contains(@class, 'dxgvHeader')) and not(contains(@class, 'dxgvFilterRow'))]")
        
        print(f"  Found {len(rows)} data rows in grid")
        
        if len(rows) == 0:
            print("  WARNING: No data rows found in grid")
            return []
        
        shows = []
        total_rows = len(rows)
        
        # Process each row by index (refetch to avoid stale elements)
        i = 0
        while i < total_rows:
            try:
                # Re-fetch all rows to avoid stale element references
                rows = grid_table.find_elements(By.XPATH, ".//tr[contains(@class, 'dxgvDataRow')]")
                if len(rows) == 0:
                    rows = grid_table.find_elements(By.XPATH, ".//tr[td and not(contains(@class, 'dxgvHeader')) and not(contains(@class, 'dxgvFilterRow'))]")
                
                if i >= len(rows):
                    break
                
                row = rows[i]
                
                # Get cells
                cells = row.find_elements(By.TAG_NAME, 'td')
                
                if len(cells) < 3:
                    print(f"  Row {i+1}/{total_rows}: Skipping (not enough cells: {len(cells)})")
                    i += 1
                    continue
                
                # Extract show info from visible cells
                # Typical columns: [ShowDate, Location, ShowName, ...]
                show_date_text = cells[0].text.strip() if len(cells) > 0 else ""
                location_text = cells[1].text.strip() if len(cells) > 1 else ""
                show_name_text = cells[2].text.strip() if len(cells) > 2 else ""
                
                print(f"\n  Row {i+1}/{total_rows}: {show_name_text[:50]}")
                print(f"    Date: {show_date_text}")
                print(f"    Location: {location_text}")
                
                # Try to find a clickable element (link or row itself)
                clickable = None
                
                # First try to find a link in the show name cell
                try:
                    clickable = cells[2].find_element(By.TAG_NAME, 'a')
                    print(f"    Found link in show name cell")
                except NoSuchElementException:
                    # Try clicking the row itself
                    clickable = row
                    print(f"    Will click entire row")
                
                # Store current URL to detect navigation
                original_url = driver.current_url
                current_window = driver.current_window_handle
                all_windows_before = driver.window_handles
                
                try:
                    # Click the element
                    driver.execute_script("arguments[0].scrollIntoView(true);", clickable)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", clickable)
                    time.sleep(2)  # Wait for navigation or new window
                    
                    # Check if a new window/tab opened
                    all_windows_after = driver.window_handles
                    
                    show_guid = None
                    
                    if len(all_windows_after) > len(all_windows_before):
                        # New window opened
                        new_window = [w for w in all_windows_after if w not in all_windows_before][0]
                        driver.switch_to.window(new_window)
                        show_guid = extract_showguid_from_url(driver.current_url)
                        print(f"    New window URL: {driver.current_url}")
                        driver.close()
                        driver.switch_to.window(current_window)
                    elif driver.current_url != original_url:
                        # Navigation in same window
                        show_guid = extract_showguid_from_url(driver.current_url)
                        print(f"    Navigated to: {driver.current_url}")
                        driver.back()
                        time.sleep(2)  # Wait for grid to reload
                        
                        # Re-find the grid table after navigation
                        for selector in possible_selectors:
                            try:
                                grid_table = driver.find_element(By.XPATH, selector)
                                break
                            except NoSuchElementException:
                                continue
                        
                        # Re-find all rows
                        rows = grid_table.find_elements(By.XPATH, ".//tr[position() > 1 and (contains(@class, 'GridItem') or contains(@class, 'GridAltItem') or td)]")
                    else:
                        print(f"    No navigation detected")
                    
                    if show_guid:
                        print(f"    [OK] GUID: {show_guid}")
                        shows.append({
                            'ShowGUID': show_guid,
                            'ShowName': show_name_text,
                            'ShowDate': show_date_text,
                            'Location': location_text,
                            'ArchiveURL': archive_url
                        })
                    else:
                        print(f"    [FAIL] No GUID found")
                
                except Exception as e:
                    print(f"    ERROR clicking row: {e}")
                    # Try to recover by going back to the original state
                    try:
                        if driver.current_url != original_url:
                            driver.back()
                            time.sleep(2)
                    except:
                        pass
                
                # Move to next row
                i += 1
            
            except StaleElementReferenceException:
                print(f"  Row {i+1}/{total_rows}: Stale element, retrying...")
                # Don't increment i, just retry this row
                continue
            except Exception as e:
                print(f"  Row {i+1}/{total_rows}: Error processing row: {e}")
                # Skip this row
                i += 1
                continue
        
        print(f"\n  Extracted {len(shows)} shows with GUIDs from this archive page")
        return shows
    
    except Exception as e:
        print(f"ERROR processing archive page: {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    print("="*80)
    print("Archive.org 2014 ShowGUID Extractor (Click-Based)")
    print("="*80)
    
    driver = setup_driver(headless=False)  # Use visible browser for debugging
    all_shows = []
    
    try:
        for archive_url in ARCHIVE_URLS:
            shows = extract_showguids_from_archive_page(driver, archive_url)
            all_shows.extend(shows)
            
            # Small delay between archive pages
            time.sleep(2)
        
        print(f"\n{'='*80}")
        print(f"FINAL RESULTS")
        print(f"{'='*80}")
        print(f"Total shows found: {len(all_shows)}")
        
        # Remove duplicates based on ShowGUID
        unique_shows = {}
        for show in all_shows:
            guid = show['ShowGUID']
            if guid not in unique_shows:
                unique_shows[guid] = show
        
        print(f"Unique shows: {len(unique_shows)}")
        
        if unique_shows:
            # Save to CSV
            csv_file = '2014_shows_archive.csv'
            with open(csv_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['ShowGUID', 'ShowName', 'ShowDate', 'Location', 'ArchiveURL'])
                writer.writeheader()
                for show in unique_shows.values():
                    writer.writerow(show)
            print(f"\nSaved to: {csv_file}")
            
            # Save GUIDs to text file
            txt_file = '2014_showguids_archive.txt'
            with open(txt_file, 'w') as f:
                for guid in sorted(unique_shows.keys()):
                    f.write(f"{guid}\n")
            print(f"Saved GUIDs to: {txt_file}")
            
            # Print summary
            print(f"\n{'='*80}")
            print("SHOWS FOUND:")
            print(f"{'='*80}")
            for show in sorted(unique_shows.values(), key=lambda x: x['ShowDate']):
                print(f"\n{show['ShowName']}")
                print(f"  Date: {show['ShowDate']}")
                print(f"  Location: {show['Location']}")
                print(f"  GUID: {show['ShowGUID']}")
                print(f"  Source: {show['ArchiveURL']}")
    
    finally:
        driver.quit()

if __name__ == '__main__':
    main()
