"""
Insert archive.org discovered ShowGUIDs with full details scraped from live site
"""

import pyodbc
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def log(msg):
    """Print with timestamp"""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {msg}", flush=True)

def setup_driver():
    """Set up Chrome WebDriver"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

def parse_date_range(date_text):
    """
    Parse date range like 'Jun 16, 2014 - Jun 21, 2014' or 'May 10, 2014'
    Returns (start_date, end_date, full_text)
    """
    if not date_text:
        return None, None, ''
    
    # Pattern: "Month DD, YYYY - Month DD, YYYY" or "Month DD, YYYY"
    date_pattern = r'([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})'
    matches = re.findall(date_pattern, date_text)
    
    if len(matches) == 2:
        # Date range
        month1, day1, year1 = matches[0]
        month2, day2, year2 = matches[1]
        start_date = f"{year1}-{month_to_num(month1):02d}-{int(day1):02d}"
        end_date = f"{year2}-{month_to_num(month2):02d}-{int(day2):02d}"
        return start_date, end_date, date_text.strip()
    elif len(matches) == 1:
        # Single date
        month, day, year = matches[0]
        date_str = f"{year}-{month_to_num(month):02d}-{int(day):02d}"
        return date_str, date_str, date_text.strip()
    else:
        return None, None, date_text.strip()

def month_to_num(month_abbr):
    """Convert month abbreviation to number"""
    months = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    return months.get(month_abbr, 1)

def scrape_show_details(driver, show_guid):
    """
    Navigate to ShowDetails page and extract show information
    Returns dict with show details or None if failed
    """
    url = f'https://horseshowsonline.com/ShowDetails?ShowGUID={show_guid}'
    
    try:
        driver.get(url)
        time.sleep(2)  # Wait for page load
        
        # Initialize details
        details = {
            'ShowGUID': show_guid,
            'ShowName': None,
            'StartDate': None,
            'EndDate': None,
            'ShowDate': None,
            'ShowLocation': None,
            'StateProv': None,
            'GoverningBody': None
        }
        
        # Try to find show name (usually in a header or title element)
        try:
            # Common patterns for show name
            name_selectors = [
                "//span[@id='ctl00_MainContent_lblShowName']",
                "//h1[contains(@class, 'show-name')]",
                "//div[@class='show-header']//h1",
                "//*[contains(@id, 'ShowName')]",
            ]
            
            for selector in name_selectors:
                try:
                    element = driver.find_element(By.XPATH, selector)
                    if element.text.strip():
                        details['ShowName'] = element.text.strip()
                        break
                except:
                    continue
            
            # If still no name, check page title
            if not details['ShowName']:
                title = driver.title
                if title and title != 'Show Details- HorseShowsOnline':
                    # Remove common suffixes
                    details['ShowName'] = title.replace('- HorseShowsOnline', '').strip()
        except:
            pass
        
        # Try to find show date
        try:
            date_selectors = [
                "//span[@id='ctl00_MainContent_lblShowDate']",
                "//span[contains(@id, 'ShowDate')]",
                "//*[contains(text(), '2014')]",
            ]
            
            for selector in date_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text.strip()
                        if '2014' in text and (',' in text or '-' in text):
                            start, end, full = parse_date_range(text)
                            if start:
                                details['StartDate'] = start
                                details['EndDate'] = end
                                details['ShowDate'] = full
                                break
                    if details['ShowDate']:
                        break
                except:
                    continue
        except:
            pass
        
        # Try to find location and state
        try:
            location_selectors = [
                "//span[@id='ctl00_MainContent_lblLocation']",
                "//span[contains(@id, 'Location')]",
            ]
            
            for selector in location_selectors:
                try:
                    element = driver.find_element(By.XPATH, selector)
                    location_text = element.text.strip()
                    
                    # Parse "CITY, STATE" format
                    if ',' in location_text:
                        parts = location_text.split(',')
                        if len(parts) >= 2:
                            details['ShowLocation'] = parts[0].strip()
                            details['StateProv'] = parts[-1].strip()
                    else:
                        details['ShowLocation'] = location_text
                    break
                except:
                    continue
        except:
            pass
        
        # Try to find governing body (usually USEF, USHJA, etc.)
        try:
            # Look for text containing common governing bodies
            page_text = driver.page_source
            
            for body in ['USEF', 'USHJA', 'USEA', 'USDF', 'NRHA', 'AQHA']:
                if body in page_text:
                    details['GoverningBody'] = body
                    break
        except:
            pass
        
        # Ensure we at least got a name
        if not details['ShowName']:
            details['ShowName'] = f'2014 Show - {show_guid[:8]}'
        
        return details
        
    except Exception as e:
        log(f"    Error scraping {show_guid}: {e}")
        return None

def main():
    log("="*80)
    log("Insert Archive GUIDs with Full Details")
    log("="*80)
    
    # Read all GUIDs from file
    with open('2014_showguids_archive.txt', 'r') as f:
        guids = [line.strip() for line in f if line.strip()]
    
    log(f"Loaded {len(guids)} GUIDs from file")
    
    # Connect to database
    try:
        conn = pyodbc.connect(
            'DRIVER={SQL Server};'
            'SERVER=localhost;'
            'DATABASE=HorseShows;'
            'Trusted_Connection=yes;'
            'TrustServerCertificate=yes'
        )
        cursor = conn.cursor()
        log("Connected to database")
        
        # Check which GUIDs already exist
        log("\nChecking for existing GUIDs...")
        cursor.execute("""
            SELECT ShowGUID 
            FROM sResults.ShowList 
            WHERE Year = 2014
        """)
        existing_guids = set(row[0].lower() for row in cursor.fetchall())
        log(f"Found {len(existing_guids)} existing 2014 shows in database")
        
        # Filter to new GUIDs only
        new_guids = [g for g in guids if g.lower() not in existing_guids]
        log(f"\n{len(new_guids)} new GUIDs to process")
        
        if len(new_guids) == 0:
            log("All GUIDs already exist in database!")
            conn.close()
            return
        
        # Set up Selenium driver
        log("\nStarting browser...")
        driver = setup_driver()
        
        # Process each GUID
        log("\nScraping show details and inserting...")
        inserted = 0
        skipped = 0
        errors = 0
        
        for i, guid in enumerate(new_guids):
            log(f"\n[{i+1}/{len(new_guids)}] Processing {guid}...")
            
            # Scrape details from live site
            details = scrape_show_details(driver, guid)
            
            if not details:
                log(f"    Failed to scrape details")
                errors += 1
                continue
            
            log(f"    Name: {details['ShowName']}")
            log(f"    Date: {details['ShowDate']}")
            log(f"    Location: {details['ShowLocation']}, {details['StateProv']}")
            log(f"    Governing Body: {details['GoverningBody']}")
            
            try:
                # Insert into database
                cursor.execute("""
                    INSERT INTO sResults.ShowList 
                    (Year, ShowGUID, ShowName, StartDate, EndDate, ShowDate, 
                     ShowLocation, StateProv, GoverningBody)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, 
                    2014,
                    details['ShowGUID'],
                    details['ShowName'],
                    details['StartDate'],
                    details['EndDate'],
                    details['ShowDate'],
                    details['ShowLocation'],
                    details['StateProv'],
                    details['GoverningBody']
                )
                
                inserted += 1
                log(f"    ✓ Inserted")
                
                # Commit every 10 shows
                if inserted % 10 == 0:
                    conn.commit()
                    log(f"  >> Committed {inserted} shows")
            
            except Exception as e:
                log(f"    Error inserting: {e}")
                skipped += 1
            
            # Small delay to be polite to the server
            time.sleep(0.5)
        
        # Final commit
        conn.commit()
        driver.quit()
        
        log(f"\n{'='*80}")
        log(f"COMPLETE")
        log(f"{'='*80}")
        log(f"Total GUIDs processed: {len(new_guids)}")
        log(f"Successfully inserted: {inserted}")
        log(f"Skipped/errors: {skipped + errors}")
        
        # Show final count
        cursor.execute("SELECT COUNT(*) FROM sResults.ShowList WHERE Year = 2014")
        total_2014 = cursor.fetchone()[0]
        log(f"\nTotal 2014 shows in database: {total_2014}")
        
        conn.close()
        log("\nDatabase connection closed")
    
    except pyodbc.Error as e:
        log(f"Database error: {e}")

if __name__ == '__main__':
    main()
