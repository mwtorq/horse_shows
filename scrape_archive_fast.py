"""
Fast archive scraper with real-time output
"""

import sys
import time
import re
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def log(msg):
    """Print with immediate flush"""
    print(msg, flush=True)

# Archive URLs
ARCHIVE_URLS = [
    'https://web.archive.org/web/20141230063824/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20141113161735/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20140707072136/http://horseshowsonline.com/ShowSelector.aspx'
]

def setup_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(options=options)
    return driver

def extract_showguid(url):
    match = re.search(r'ShowGUID=([a-f0-9\-]+)', url, re.IGNORECASE)
    return match.group(1) if match else None

def scrape_archive(driver, url):
    log(f"\n{'='*80}")
    log(f"Processing: {url}")
    log(f"{'='*80}")
    
    driver.get(url)
    time.sleep(5)
    log(f"Loaded: {driver.title}")
    
    # Find grid initial
    grid = driver.find_element(By.ID, 'ctl00_MainContent_grMaster_DXMainTable')
    log("Found grid table")
    
    # Get initial row count
    rows = grid.find_elements(By.XPATH, ".//tr[contains(@class, 'dxgvDataRow')]")
    total_rows = len(rows)
    log(f"Total rows to process: {total_rows}")
    
    shows = []
    i = 0
    
    while i < total_rows:
        # Wait for grid to be present and re-fetch (to avoid stale elements)
        try:
            grid = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, 'ctl00_MainContent_grMaster_DXMainTable'))
            )
            rows = grid.find_elements(By.XPATH, ".//tr[contains(@class, 'dxgvDataRow')]")
        except:
            log(f"    [ERROR] Grid not found after navigation, stopping")
            break
        
        if i >= len(rows):
            break
        
        row = rows[i]
        
        try:
            cells = row.find_elements(By.TAG_NAME, 'td')
            if len(cells) < 3:
                i += 1
                continue
            
            show_name = cells[2].text.strip()[:50]
            log(f"  Row {i+1}/{len(rows)}: {show_name}")
            
            # Click row
            driver.execute_script("arguments[0].click();", row)
            time.sleep(2)
            
            # Extract GUID
            guid = extract_showguid(driver.current_url)
            
            if guid:
                log(f"    [OK] {guid}")
                shows.append({
                    'ShowGUID': guid,
                    'ShowName': cells[2].text.strip(),
                    'ShowDate': cells[0].text.strip(),
                    'Location': cells[1].text.strip()
                })
            else:
                log(f"    [SKIP] No GUID")
            
            # Go back
            driver.back()
            time.sleep(2)
            
            i += 1
            
        except Exception as e:
            log(f"    [ERROR] {str(e)[:100]}")
            i += 1
    
    log(f"Extracted {len(shows)} shows from this page")
    return shows

def main():
    log("Archive.org 2014 ShowGUID Extractor")
    log("="*80)
    
    driver = setup_driver()
    all_shows = []
    
    try:
        for url in ARCHIVE_URLS:
            shows = scrape_archive(driver, url)
            all_shows.extend(shows)
        
        # Remove duplicates
        unique = {}
        for s in all_shows:
            unique[s['ShowGUID']] = s
        
        log(f"\n{'='*80}")
        log(f"TOTAL: {len(unique)} unique shows")
        log(f"{'='*80}")
        
        # Save to CSV
        if unique:
            with open('2014_shows_archive.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['ShowGUID', 'ShowName', 'ShowDate', 'Location'])
                writer.writeheader()
                writer.writerows(unique.values())
            log("Saved to: 2014_shows_archive.csv")
            
            # Save GUIDs
            with open('2014_showguids_archive.txt', 'w') as f:
                for guid in sorted(unique.keys()):
                    f.write(f"{guid}\n")
            log("Saved to: 2014_showguids_archive.txt")
            
            # Print summary
            for show in sorted(unique.values(), key=lambda x: x['ShowDate']):
                log(f"\n{show['ShowName']}")
                log(f"  Date: {show['ShowDate']}")
                log(f"  GUID: {show['ShowGUID']}")
    
    finally:
        driver.quit()
    
    log("\nDone!")

if __name__ == '__main__':
    main()
