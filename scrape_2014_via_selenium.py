"""
Advanced script to try accessing 2014 shows through Selenium
Attempts multiple methods:
1. Directly manipulate the year dropdown to add 2014
2. Intercept/modify AJAX requests
3. Direct JavaScript injection to load 2014 data
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
import time
import json
import pyodbc
import re
from urllib.parse import urlparse, parse_qs

def setup_driver():
    """Setup Chrome WebDriver"""
    chrome_options = Options()
    # Run visible to see what's happening
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })
    return driver

def try_inject_2014_option(driver):
    """Try to inject 2014 as an option in the year dropdown"""
    print("\n[METHOD 1] Attempting to inject 2014 into year dropdown...")
    
    try:
        # Find the year dropdown
        year_picker_script = """
        // Find the year dropdown element
        var yearDropdown = document.querySelector('[id*="ddShowYear"]');
        if (!yearDropdown) {
            yearDropdown = document.querySelector('select[id*="Year"]');
        }
        
        if (yearDropdown) {
            // Add 2014 as an option
            var option = document.createElement('option');
            option.value = '2014';
            option.text = '2014';
            yearDropdown.appendChild(option);
            
            // Select it
            yearDropdown.value = '2014';
            
            // Trigger change event
            var event = new Event('change', { bubbles: true });
            yearDropdown.dispatchEvent(event);
            
            return 'SUCCESS: 2014 added and selected';
        } else {
            return 'ERROR: Year dropdown not found';
        }
        """
        
        result = driver.execute_script(year_picker_script)
        print(f"  {result}")
        
        # Wait for grid to reload
        time.sleep(5)
        
        # Check if we got results
        try:
            grid = driver.find_element(By.CSS_SELECTOR, "table[id*='grMaster']")
            rows = grid.find_elements(By.TAG_NAME, "tr")
            print(f"  Found {len(rows)} rows in grid")
            return len(rows) > 2  # More than just header rows
        except:
            print("  No grid found after injection")
            return False
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def try_direct_ajax_call(driver):
    """Try to make direct AJAX call to load 2014 shows"""
    print("\n[METHOD 2] Attempting direct AJAX call for 2014...")
    
    try:
        ajax_script = """
        // Try to find and call the AJAX callback for loading shows
        var callback = window.__doPostBack || window.WebForm_DoPostBack;
        
        if (typeof callback === 'function') {
            // Attempt to trigger postback for year 2014
            callback('ctl00$MainContent$panFilter$ddShowYear', '2014');
            return 'SUCCESS: AJAX callback triggered';
        } else {
            return 'ERROR: AJAX callback not found';
        }
        """
        
        result = driver.execute_script(ajax_script)
        print(f"  {result}")
        
        time.sleep(5)
        return result.startswith('SUCCESS')
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def try_direct_url_with_year_param(driver):
    """Try to access ShowSelector with year=2014 parameter"""
    print("\n[METHOD 3] Attempting direct URL with year parameter...")
    
    urls_to_try = [
        'https://horseshowsonline.com/ShowSelector.aspx?year=2014',
        'https://horseshowsonline.com/ShowSelector.aspx?Year=2014',
        'https://horseshowsonline.com/ShowSelector?year=2014',
        'https://horseshowsonline.com/ShowSelector?Year=2014',
    ]
    
    for url in urls_to_try:
        try:
            print(f"  Trying: {url}")
            driver.get(url)
            time.sleep(3)
            
            # Check if we got a grid with shows
            try:
                grid = driver.find_element(By.CSS_SELECTOR, "table[id*='grMaster']")
                rows = grid.find_elements(By.TAG_NAME, "tr")
                
                # Check if any row contains "2014"
                for row in rows[:10]:  # Check first 10 rows
                    if '2014' in row.text:
                        print(f"  SUCCESS! Found 2014 shows at: {url}")
                        print(f"  Found {len(rows)} total rows")
                        return True, url
            except:
                pass
                
        except Exception as e:
            print(f"    [ERROR] {e}")
    
    print("  No success with URL parameters")
    return False, None

def extract_showguids_from_page(driver):
    """Extract ShowGUIDs from current page by clicking each row"""
    show_data = []
    
    try:
        print("  Extracting show data from grid...")
        
        # Find the grid table
        grid = driver.find_element(By.CSS_SELECTOR, "table[id*='grMaster']")
        rows = grid.find_elements(By.TAG_NAME, "tr")
        
        print(f"  Processing {len(rows)} rows...")
        
        # Store original window handle
        original_window = driver.current_window_handle
        
        # Process each data row (skip header)
        for i, row in enumerate(rows[1:], 1):  # Skip first row (header)
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 3:
                    continue
                
                # Get show name and date from cells
                show_date = cells[1].text.strip() if len(cells) > 1 else ''
                show_name = cells[2].text.strip() if len(cells) > 2 else ''
                
                # Skip if no name
                if not show_name or '2014' not in show_date:
                    continue
                
                print(f"  [{i}] {show_name} - {show_date}")
                
                # Try to find a link in the row
                try:
                    # Look for links in the show name cell
                    link = cells[2].find_element(By.TAG_NAME, "a")
                    href = link.get_attribute('href')
                    
                    if href and 'ShowGUID=' in href:
                        parsed = urlparse(href)
                        params = parse_qs(parsed.query)
                        if 'ShowGUID' in params:
                            guid = params['ShowGUID'][0]
                            print(f"      GUID: {guid}")
                            show_data.append({
                                'ShowGUID': guid,
                                'ShowName': show_name,
                                'ShowDate': show_date
                            })
                            continue
                except:
                    pass
                
                # If no direct link, try clicking the row
                try:
                    driver.execute_script("arguments[0].click();", row)
                    time.sleep(2)
                    
                    # Check if new window opened
                    if len(driver.window_handles) > 1:
                        driver.switch_to.window(driver.window_handles[-1])
                        current_url = driver.current_url
                        driver.close()
                        driver.switch_to.window(original_window)
                    else:
                        current_url = driver.current_url
                        driver.back()
                        time.sleep(1)
                    
                    # Extract GUID from URL
                    if 'ShowGUID=' in current_url:
                        parsed = urlparse(current_url)
                        params = parse_qs(parsed.query)
                        if 'ShowGUID' in params:
                            guid = params['ShowGUID'][0]
                            print(f"      GUID: {guid}")
                            show_data.append({
                                'ShowGUID': guid,
                                'ShowName': show_name,
                                'ShowDate': show_date
                            })
                
                except Exception as e:
                    print(f"      [ERROR] Could not extract GUID: {e}")
                    
            except Exception as e:
                print(f"  [ERROR] Row {i}: {e}")
                continue
        
    except Exception as e:
        print(f"[ERROR] Extracting show data: {e}")
        import traceback
        traceback.print_exc()
    
    return show_data

def main():
    print("="*60)
    print("Advanced 2014 Show Discovery - Selenium Method")
    print("="*60)
    
    driver = None
    try:
        print("\nInitializing browser...")
        driver = setup_driver()
        
        print("Navigating to ShowSelector...")
        driver.get('https://horseshowsonline.com/ShowSelector.aspx')
        time.sleep(3)
        
        # Activate Shows By Year tab first
        print("\nActivating 'Shows By Year' tab...")
        try:
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            for tab in tabs:
                if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                    link = tab.find_element(By.CSS_SELECTOR, "a.dxtc-link")
                    driver.execute_script("arguments[0].click();", link)
                    time.sleep(3)
                    print("  Tab activated")
                    break
        except Exception as e:
            print(f"  [ERROR] {e}")
        
        # Try Method 1: Inject 2014 option
        success = try_inject_2014_option(driver)
        if success:
            print("\n[SUCCESS] Method 1 worked! Extracting show data...")
            show_data = extract_showguids_from_page(driver)
            print(f"\nFound {len(show_data)} shows with GUIDs via injection")
            return show_data
        
        # Try Method 2: Direct AJAX
        success = try_direct_ajax_call(driver)
        if success:
            print("\n[SUCCESS] Method 2 worked! Extracting show data...")
            show_data = extract_showguids_from_page(driver)
            print(f"Found {len(show_data)} shows with GUIDs via AJAX")
            return show_data
        
        # Try Method 3: URL parameters
        success, url = try_direct_url_with_year_param(driver)
        if success:
            print(f"\n[SUCCESS] Method 3 worked! Extracting show data from {url}...")
            show_data = extract_showguids_from_page(driver)
            print(f"Found {len(show_data)} shows with GUIDs via URL parameter")
            return show_data
        
        print("\n[FAILED] All methods failed to access 2014 shows")
        print("\nPossible reasons:")
        print("1. 2014 data is truly unavailable through the web interface")
        print("2. Access requires authentication or special permissions")
        print("3. 2014 data is in a separate archive system")
        print("\nRecommendation: Contact HorseShowsOnline support to request:")
        print("- Direct database export of 2014 ShowGUIDs")
        print("- API access for historical data")
        print("- Archive access permissions")
        
        return []
        
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        return []
        
    finally:
        if driver:
            print("\nClosing browser...")
            time.sleep(2)
            driver.quit()

if __name__ == '__main__':
    show_data = main()
    
    if show_data:
        print(f"\n{'='*60}")
        print(f"SUCCESS! Found {len(show_data)} shows")
        print("="*60)
        
        # Save to CSV
        import csv
        with open('2014_shows_discovered.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['ShowGUID', 'ShowName', 'ShowDate'])
            writer.writeheader()
            writer.writerows(show_data)
        
        print(f"\nSaved to: 2014_shows_discovered.csv")
        
        # Also save just GUIDs for easy importing
        with open('2014_showguids_discovered.txt', 'w') as f:
            for show in show_data:
                f.write(f"{show['ShowGUID']}\n")
        
        print(f"Saved GUIDs to: 2014_showguids_discovered.txt")
        
        # Display summary
        print(f"\nSample shows:")
        for show in show_data[:10]:
            print(f"  • {show['ShowName']}")
            print(f"    Date: {show['ShowDate']}")
            print(f"    GUID: {show['ShowGUID']}")
    else:
        print(f"\n{'='*60}")
        print("No shows discovered")
        print("="*60)
