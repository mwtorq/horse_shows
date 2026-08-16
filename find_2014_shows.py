"""
Script to search for 2014 horse shows on horseshowsonline.com
Since 2014 is not in the year dropdown, we use alternative methods:
1. Google Custom Search API (if available)
2. Web scraping of known show pages to find related shows
3. Systematic GUID testing (if patterns exist)
"""

import requests
from bs4 import BeautifulSoup
import re
import pyodbc
from datetime import datetime
import time

# Known 2014 ShowGUIDs to start with
KNOWN_2014_GUIDS = [
    '671d6c9e-750e-491f-8ab8-80637b119410',  # ROANOKE VALLEY
    '5f918c54-175b-4a79-bd56-87eb283e4afa',  # WARRENTON
    'a109ee9b-c043-4548-99ca-ed9dea199903',  # VHSA ASSOCIATES
    'eafce8f9-ad9f-48b3-a496-c01ff9a7fe53',  # VERMONT SUMMER
    'c756326a-8448-4475-abdd-418335bdacbe',  # KEMPER KNOLL FARMS
    'b66187c3-032e-457f-bd0f-4f1da655e805',  # TRYON SUMMER CLASSIC
    'f79f89bb-48ed-40d7-9de0-7f133007d147',  # ST. LOUIS NATIONAL
    'fcd94099-1872-45ff-8700-2307318d65ff',  # QUENTIN RIDING CLUB
]

def get_db_connection():
    """Create database connection"""
    conn_str = (
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=localhost;'
        'DATABASE=HorseShows;'
        'Trusted_Connection=yes;'
    )
    return pyodbc.connect(conn_str)

def extract_show_info_from_page(show_guid):
    """Extract show information from ShowDetails page"""
    url = f'https://horseshowsonline.com/ShowDetails?ShowGUID={show_guid}'
    print(f"  Fetching: {url}")
    
    # Use headers to mimic a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"  [SKIP] Status code: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract show name from title or h1
        show_name = None
        title = soup.find('title')
        if title:
            show_name = title.text.replace('- HorseShowsOnline', '').strip()
        
        # Extract show dates
        show_date_pattern = r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+2014'
        date_matches = re.findall(show_date_pattern, response.text)
        
        # Check if this is actually a 2014 show
        if '2014' not in response.text:
            print(f"  [SKIP] Not a 2014 show")
            return None
        
        show_info = {
            'ShowGUID': show_guid,
            'ShowName': show_name,
            'Year': 2014,
            'HasResults': 'Class Results' in response.text or 'ClassResults' in response.text
        }
        
        print(f"  [OK] Found: {show_name}")
        return show_info
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

def search_google_for_2014_shows():
    """Use Google to search for 2014 shows"""
    print("\n" + "="*60)
    print("Searching Google for 2014 shows...")
    print("="*60)
    
    # Search terms to try
    search_terms = [
        'site:horseshowsonline.com "2014" ShowGUID',
        'site:horseshowsonline.com "Jan 2014" ShowDetails',
        'site:horseshowsonline.com "Feb 2014" ShowDetails',
        'site:horseshowsonline.com "Mar 2014" ShowDetails',
        'site:horseshowsonline.com "Apr 2014" ShowDetails',
        'site:horseshowsonline.com "May 2014" ShowDetails',
        'site:horseshowsonline.com "Jun 2014" ShowDetails',
        'site:horseshowsonline.com "Jul 2014" ShowDetails',
        'site:horseshowsonline.com "Aug 2014" ShowDetails',
        'site:horseshowsonline.com "Sep 2014" ShowDetails',
        'site:horseshowsonline.com "Oct 2014" ShowDetails',
        'site:horseshowsonline.com "Nov 2014" ShowDetails',
        'site:horseshowsonline.com "Dec 2014" ShowDetails',
    ]
    
    found_guids = set()
    
    for term in search_terms:
        print(f"\nSearching: {term}")
        
        # Use Google Custom Search (requires API key) or manual
        # For now, print instructions for manual search
        print(f"  Manual search: https://www.google.com/search?q={term.replace(' ', '+')}")
        
        # Extract ShowGUIDs from search results would require:
        # - Google Custom Search API key
        # - Or Selenium to scrape Google results
        # - Or manual copy/paste of results
        
    return list(found_guids)

def verify_known_guids():
    """Verify and extract full info for known GUIDs"""
    print("\n" + "="*60)
    print("Verifying known 2014 ShowGUIDs...")
    print("="*60)
    
    shows = []
    for guid in KNOWN_2014_GUIDS:
        print(f"\nChecking {guid}...")
        show_info = extract_show_info_from_page(guid)
        if show_info:
            shows.append(show_info)
        time.sleep(1)  # Be polite to the server
    
    return shows

def save_shows_to_db(shows):
    """Save found shows to database"""
    if not shows:
        print("\nNo shows to save.")
        return
    
    print(f"\n" + "="*60)
    print(f"Saving {len(shows)} shows to database...")
    print("="*60)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        for show in shows:
            # Check if exists
            cursor.execute("""
                SELECT ShowListID FROM sResults.ShowList 
                WHERE ShowGUID = ?
            """, show['ShowGUID'])
            
            if cursor.fetchone():
                print(f"  [EXISTS] {show['ShowName']}")
            else:
                cursor.execute("""
                    INSERT INTO sResults.ShowList 
                    (Year, ShowGUID, ShowName)
                    VALUES (?, ?, ?)
                """, show['Year'], show['ShowGUID'], show['ShowName'])
                print(f"  [INSERTED] {show['ShowName']}")
        
        conn.commit()
        cursor.close()
        conn.close()
        print("\n[OK] Database updated successfully")
        
    except Exception as e:
        print(f"\n[ERROR] Database error: {e}")

def main():
    print("="*60)
    print("HorseShowsOnline - 2014 Show Finder")
    print("="*60)
    print()
    print("Known 2014 shows to verify:", len(KNOWN_2014_GUIDS))
    print()
    
    # Verify known GUIDs and extract full info
    shows = verify_known_guids()
    
    print(f"\n" + "="*60)
    print(f"Summary: Found {len(shows)} valid 2014 shows")
    print("="*60)
    
    for show in shows:
        print(f"  • {show['ShowName']}")
        print(f"    GUID: {show['ShowGUID']}")
        print(f"    Has Results: {show['HasResults']}")
    
    # Save to database
    response = input("\nSave these shows to database? (y/n): ")
    if response.lower() == 'y':
        save_shows_to_db(shows)
    
    print("\n" + "="*60)
    print("Next steps:")
    print("="*60)
    print("1. Run: python scrape_class_results.py --year 2014 --direct-url")
    print("2. To find more 2014 shows, search Google manually:")
    print("   https://www.google.com/search?q=site:horseshowsonline.com+2014+ShowGUID")
    print("3. Add any new ShowGUIDs to KNOWN_2014_GUIDS in this script")

if __name__ == '__main__':
    main()
