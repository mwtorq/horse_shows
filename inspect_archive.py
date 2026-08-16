"""
Simple script to inspect what's on the archive.org pages
"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException

def setup_driver():
    """Set up Chrome WebDriver"""
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver

# Just inspect first archive URL
archive_url = 'https://web.archive.org/web/20141230063824/http://horseshowsonline.com/ShowSelector.aspx'

print(f"Inspecting: {archive_url}\n")

driver = setup_driver()

try:
    print("Loading page...")
    driver.get(archive_url)
    time.sleep(5)
    
    print(f"Current URL: {driver.current_url}")
    print(f"Page title: {driver.title}\n")
    
    # Try iframe
    print("Checking for iframe...")
    try:
        iframe = driver.find_element(By.ID, "playback")
        print("Found playback iframe, switching...")
        driver.switch_to.frame(iframe)
        time.sleep(2)
    except NoSuchElementException:
        print("No playback iframe\n")
    
    # Find all tables
    print("Finding tables...")
    tables = driver.find_elements(By.TAG_NAME, 'table')
    print(f"Found {len(tables)} tables\n")
    
    for i, table in enumerate(tables[:15]):
        table_id = table.get_attribute('id') or '(none)'
        table_class = table.get_attribute('class') or '(none)'
        rows = table.find_elements(By.TAG_NAME, 'tr')
        print(f"Table {i+1}:")
        print(f"  ID: {table_id}")
        print(f"  Class: {table_class}")
        print(f"  Rows: {len(rows)}")
        
        if len(rows) > 3:
            # Show first few rows
            for j, row in enumerate(rows[:3]):
                cells = row.find_elements(By.TAG_NAME, 'td')
                if not cells:
                    cells = row.find_elements(By.TAG_NAME, 'th')
                cell_text = [c.text[:30] for c in cells[:5]]
                print(f"    Row {j+1}: {cell_text}")
        print()
    
    # Save full page HTML
    print("Saving page HTML...")
    with open('archive_page.html', 'w', encoding='utf-8') as f:
        f.write(driver.page_source)
    print("Saved to: archive_page.html")
    
finally:
    driver.quit()

print("\nDone!")
