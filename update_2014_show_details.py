"""
Update existing 2014 shows with full details scraped from live site
"""

import pyodbc
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By

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
    """Parse date range and return (start_date, end_date, full_text)"""
    if not date_text:
        return None, None, ''
    
    date_pattern = r'([A-Z][a-z]{2})\s+(\d{1,2}),\s+(\d{4})'
    matches = re.findall(date_pattern, date_text)
    
    months = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }
    
    if len(matches) == 2:
        month1, day1, year1 = matches[0]
        month2, day2, year2 = matches[1]
        start_date = f"{year1}-{months.get(month1, 1):02d}-{int(day1):02d}"
        end_date = f"{year2}-{months.get(month2, 1):02d}-{int(day2):02d}"
        return start_date, end_date, date_text.strip()
    elif len(matches) == 1:
        month, day, year = matches[0]
        date_str = f"{year}-{months.get(month, 1):02d}-{int(day):02d}"
        return date_str, date_str, date_text.strip()
    
    return None, None, date_text.strip()

def scrape_show_details(driver, show_guid):
    """Scrape show details from ShowDetails page"""
    url = f'https://horseshowsonline.com/ShowDetails?ShowGUID={show_guid}'
    
    try:
        driver.get(url)
        time.sleep(2)
        
        details = {
            'ShowName': None,
            'StartDate': None,
            'EndDate': None,
            'ShowDate': None,
            'ShowLocation': None,
            'StateProv': None,
            'GoverningBody': None
        }
        
        # Get show name from page title
        title = driver.title
        if title and '- HorseShowsOnline' in title:
            details['ShowName'] = title.replace('- HorseShowsOnline', '').strip()
        
        # Try specific ID selectors
        try:
            name_elem = driver.find_element(By.ID, 'ctl00_MainContent_lblShowName')
            if name_elem.text.strip():
                details['ShowName'] = name_elem.text.strip()
        except:
            pass
        
        # Get show date
        try:
            date_elem = driver.find_element(By.ID, 'ctl00_MainContent_lblShowDate')
            date_text = date_elem.text.strip()
            if date_text:
                start, end, full = parse_date_range(date_text)
                details['StartDate'] = start
                details['EndDate'] = end
                details['ShowDate'] = full
        except:
            # Try finding any text with 2014 dates
            try:
                elements = driver.find_elements(By.XPATH, "//*[contains(text(), '2014')]")
                for elem in elements:
                    text = elem.text.strip()
                    if ',' in text:
                        start, end, full = parse_date_range(text)
                        if start:
                            details['StartDate'] = start
                            details['EndDate'] = end
                            details['ShowDate'] = full
                            break
            except:
                pass
        
        # Get location
        try:
            location_elem = driver.find_element(By.ID, 'ctl00_MainContent_lblLocation')
            location_text = location_elem.text.strip()
            
            if ',' in location_text:
                parts = [p.strip() for p in location_text.split(',')]
                if len(parts) >= 2:
                    details['ShowLocation'] = parts[0]
                    # Last part is usually state
                    state_part = parts[-1]
                    # Extract just the state abbreviation (2 letters)
                    state_match = re.search(r'\b([A-Z]{2})\b', state_part)
                    if state_match:
                        details['StateProv'] = state_match.group(1)
                    else:
                        details['StateProv'] = state_part
            else:
                details['ShowLocation'] = location_text
        except:
            pass
        
        # Get governing body
        page_source = driver.page_source
        for body in ['USEF', 'USHJA', 'USEA', 'USDF', 'NRHA', 'AQHA', 'NSBA']:
            if body in page_source:
                details['GoverningBody'] = body
                break
        
        return details
        
    except Exception as e:
        log(f"    Error: {e}")
        return None

def main():
    log("="*80)
    log("Update 2014 Shows with Full Details")
    log("="*80)
    
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
        
        # Get all 2014 shows that need updating (those with placeholder names)
        log("\nFinding shows to update...")
        cursor.execute("""
            SELECT ID, ShowGUID, ShowName
            FROM sResults.ShowList
            WHERE Year = 2014
            AND (ShowName LIKE '%Archive%' OR ShowName LIKE '2014 Show%')
            ORDER BY ID
        """)
        
        shows_to_update = cursor.fetchall()
        log(f"Found {len(shows_to_update)} shows to update")
        
        if len(shows_to_update) == 0:
            log("No shows need updating!")
            conn.close()
            return
        
        # Set up browser
        log("\nStarting browser...")
        driver = setup_driver()
        
        # Update each show
        log("\nScraping and updating shows...")
        updated = 0
        errors = 0
        
        for i, (show_id, show_guid, current_name) in enumerate(shows_to_update):
            log(f"\n[{i+1}/{len(shows_to_update)}] {show_guid}...")
            log(f"    Current: {current_name}")
            
            # Scrape details
            details = scrape_show_details(driver, show_guid)
            
            if not details or not details['ShowName']:
                log(f"    Failed to scrape")
                errors += 1
                continue
            
            log(f"    New: {details['ShowName']}")
            log(f"    Date: {details['ShowDate']}")
            log(f"    Location: {details['ShowLocation']}, {details['StateProv']}")
            
            try:
                # Update database
                cursor.execute("""
                    UPDATE sResults.ShowList
                    SET ShowName = ?,
                        StartDate = ?,
                        EndDate = ?,
                        ShowDate = ?,
                        ShowLocation = ?,
                        StateProv = ?,
                        GoverningBody = ?
                    WHERE ID = ?
                """,
                    details['ShowName'],
                    details['StartDate'],
                    details['EndDate'],
                    details['ShowDate'],
                    details['ShowLocation'],
                    details['StateProv'],
                    details['GoverningBody'],
                    show_id
                )
                
                updated += 1
                
                # Commit every 10
                if updated % 10 == 0:
                    conn.commit()
                    log(f"  >> Committed {updated} updates")
            
            except Exception as e:
                log(f"    Update error: {e}")
                errors += 1
            
            # Be polite to server
            time.sleep(0.5)
        
        # Final commit
        conn.commit()
        driver.quit()
        
        log(f"\n{'='*80}")
        log(f"COMPLETE")
        log(f"{'='*80}")
        log(f"Shows processed: {len(shows_to_update)}")
        log(f"Successfully updated: {updated}")
        log(f"Errors: {errors}")
        
        conn.close()
    
    except Exception as e:
        log(f"Error: {e}")

if __name__ == '__main__':
    main()
