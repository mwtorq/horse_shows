"""
Extract ShowGUIDs from archive by parsing links directly
"""

import re
import csv
from selenium import webdriver
from selenium.webdriver.common.by import By
import time

def log(msg):
    print(msg, flush=True)

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
    driver = webdriver.Chrome(options=options)
    return driver

def extract_guid(text):
    """Extract GUID from text"""
    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', text, re.IGNORECASE)
    return match.group(1) if match else None

def scrape_archive(driver, url):
    log(f"\n{'='*80}")
    log(f"Processing: {url}")
    log(f"{'='*80}")
    
    driver.get(url)
    time.sleep(5)
    log(f"Loaded: {driver.title}")
    
    # Get page source and search for GUIDs
    page_source = driver.page_source
    
    # Find all GUIDs in page source
    guid_pattern = r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
    all_guids = re.findall(guid_pattern, page_source, re.IGNORECASE)
    
    log(f"Found {len(all_guids)} GUIDs in page source")
    log(f"Unique GUIDs: {len(set(all_guids))}")
    
    # Try to find grid table and extract show names
    shows = {}
    
    try:
        grid = driver.find_element(By.ID, 'ctl00_MainContent_grMaster_DXMainTable')
        rows = grid.find_elements(By.XPATH, ".//tr[contains(@class, 'dxgvDataRow')]")
        log(f"Found {len(rows)} data rows in grid")
        
        for i, row in enumerate(rows):
            try:
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 3:
                    show_date = cells[0].text.strip()
                    location = cells[1].text.strip()
                    show_name = cells[2].text.strip()
                    
                    # Try to find onclick or other attributes that might contain GUID
                    row_html = row.get_attribute('outerHTML')
                    guid = extract_guid(row_html)
                    
                    if guid:
                        log(f"  Row {i+1}: {show_name[:40]} -> {guid}")
                        shows[guid] = {
                            'ShowGUID': guid,
                            'ShowName': show_name,
                            'ShowDate': show_date,
                            'Location': location
                        }
            except Exception as e:
                continue
    except Exception as e:
        log(f"Error processing grid: {e}")
    
    log(f"Extracted {len(shows)} shows with names and GUIDs")
    
    # Also capture any GUIDs we found that might not have been matched to rows
    unique_guids = set(all_guids)
    if len(shows) < len(unique_guids):
        log(f"Note: {len(unique_guids)} total unique GUIDs found in page, {len(shows)} matched to show names")
        log(f"Saving all {len(unique_guids)} GUIDs found...")
        
        # Add GUIDs without show names
        for guid in unique_guids:
            if guid not in shows:
                shows[guid] = {
                    'ShowGUID': guid,
                    'ShowName': '(unknown)',
                    'ShowDate': '',
                    'Location': ''
                }
    
    return list(shows.values())

def main():
    log("Archive.org 2014 ShowGUID Extractor (Link Parsing)")
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
        
        if unique:
            # Save to CSV
            with open('2014_shows_archive.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['ShowGUID', 'ShowName', 'ShowDate', 'Location'])
                writer.writeheader()
                writer.writerows(unique.values())
            log("Saved to: 2014_shows_archive.csv")
            
            # Save GUIDs only
            with open('2014_showguids_archive.txt', 'w') as f:
                for guid in sorted(unique.keys()):
                    f.write(f"{guid}\n")
            log("Saved GUIDs to: 2014_showguids_archive.txt")
            
            # Print some examples
            log("\nSample shows found:")
            for show in list(unique.values())[:10]:
                log(f"  {show['ShowName']}")
                log(f"    Date: {show['ShowDate']}")
                log(f"    GUID: {show['ShowGUID']}")
                log("")
    
    finally:
        driver.quit()
    
    log("Done!")

if __name__ == '__main__':
    main()
