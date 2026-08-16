"""
Use Selenium to extract ShowGUIDs from Internet Archive snapshots
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re
from urllib.parse import urlparse, parse_qs
import csv

ARCHIVE_URLS = [
    'https://web.archive.org/web/20140707072136/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20141113161735/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20141230063824/http://horseshowsonline.com/ShowSelector.aspx',
]

def setup_driver():
    """Setup Chrome WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def extract_showguids_from_archived_page(driver, url):
    """Extract ShowGUIDs from archived page"""
    print(f"\nProcessing: {url}")
    
    try:
        driver.get(url)
        time.sleep(5)  # Let page load
        
        shows = []
        guids_seen = set()
        
        # Find all links that might contain ShowGUID
        links = driver.find_elements(By.TAG_NAME, "a")
        
        print(f"  Found {len(links)} links, scanning for ShowGUIDs...")
        
        for link in links:
            try:
                href = link.get_attribute('href')
                
                if not href or 'ShowGUID=' not in href:
                    continue
                
                # Extract ShowGUID from archived URL
                # Format: https://web.archive.org/web/TIMESTAMP/http://horseshowsonline.com/ShowDetails?ShowGUID=xxx
                match = re.search(r'ShowGUID=([a-fA-F0-9-]+)', href)
                if match:
                    guid = match.group(1)
                    
                    if guid in guids_seen:
                        continue
                    
                    guids_seen.add(guid)
                    
                    # Get show name from link text
                    show_name = link.text.strip()
                    
                    # Try to find parent row to get date
                    show_date = ''
                    try:
                        row = link.find_element(By.XPATH, "./ancestor::tr[1]")
                        cells = row.find_elements(By.TAG_NAME, "td")
                        
                        # Look for date in cells
                        for cell in cells:
                            text = cell.text.strip()
                            if re.search(r'[A-Z][a-z]{2}\s+\d{1,2},\s+2014', text):
                                show_date = text
                                break
                    except:
                        pass
                    
                    # Only include if it's a 2014 show
                    if '2014' in show_date or not show_date:  # Include if no date found
                        shows.append({
                            'ShowGUID': guid,
                            'ShowName': show_name,
                            'ShowDate': show_date
                        })
                        print(f"    [{len(shows)}] {show_name}")
                        print(f"        Date: {show_date}")
                        print(f"        GUID: {guid}")
            
            except Exception as e:
                continue
        
        return shows
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    print("="*60)
    print("Extract ShowGUIDs from Internet Archive")
    print("="*60)
    
    driver = None
    all_shows = []
    guids_seen = set()
    
    try:
        driver = setup_driver()
        
        for url in ARCHIVE_URLS:
            shows = extract_showguids_from_archived_page(driver, url)
            
            # Deduplicate
            for show in shows:
                if show['ShowGUID'] not in guids_seen:
                    guids_seen.add(show['ShowGUID'])
                    all_shows.append(show)
            
            time.sleep(2)  # Be nice to archive.org
        
        print(f"\n{'='*60}")
        print(f"Total unique shows found: {len(all_shows)}")
        print("="*60)
        
        if all_shows:
            # Save to CSV
            with open('2014_shows_from_archive.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['ShowGUID', 'ShowName', 'ShowDate'])
                writer.writeheader()
                writer.writerows(all_shows)
            
            print(f"\nSaved to: 2014_shows_from_archive.csv")
            
            # Save just GUIDs
            with open('2014_showguids_from_archive.txt', 'w') as f:
                for show in all_shows:
                    f.write(f"{show['ShowGUID']}\n")
            
            print(f"Saved GUIDs to: 2014_showguids_from_archive.txt")
            
            print(f"\nFirst 20 shows:")
            for show in all_shows[:20]:
                print(f"  • {show['ShowName']} - {show['ShowDate']}")
                print(f"    {show['ShowGUID']}")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    main()
