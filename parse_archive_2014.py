"""
Parse Internet Archive snapshots of horseshowsonline.com from 2014
to extract ShowGUIDs for all 2014 shows
"""

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import csv
from urllib.parse import urlparse, parse_qs

# Archive.org URLs to parse
ARCHIVE_URLS = [
    'https://web.archive.org/web/20141230063824/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20141113161735/http://horseshowsonline.com/ShowSelector.aspx',
    'https://web.archive.org/web/20140707072136/http://horseshowsonline.com/ShowSelector.aspx',
]

def parse_date(date_str):
    """Try to parse various date formats"""
    date_str = date_str.strip()
    
    # Common formats
    formats = [
        '%b %d, %Y',  # Jun 16, 2014
        '%b %d, %Y - %b %d, %Y',  # Jun 16, 2014 - Jun 21, 2014
    ]
    
    for fmt in formats:
        try:
            # If range, take first date
            if ' - ' in date_str:
                date_str = date_str.split(' - ')[0].strip()
            
            dt = datetime.strptime(date_str, '%b %d, %Y')
            return dt
        except:
            continue
    
    return None

def is_2014_show(date_str):
    """Check if show date is in 2014"""
    if not date_str or '2014' not in date_str:
        return False
    
    dt = parse_date(date_str)
    if dt and dt.year == 2014:
        return True
    
    # Fallback: just check for 2014 in string
    return '2014' in date_str

def extract_shows_from_archive(url):
    """Extract show data from archived page"""
    print(f"\nFetching: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        shows = []
        
        # Find all table rows
        # The grid might be in a table with id containing 'grMaster'
        tables = soup.find_all('table')
        
        for table in tables:
            table_id = table.get('id', '')
            if 'grMaster' in table_id or 'grid' in table_id.lower():
                print(f"  Found grid table: {table_id}")
                
                rows = table.find_all('tr')
                print(f"  Processing {len(rows)} rows...")
                
                for i, row in enumerate(rows):
                    cells = row.find_all('td')
                    
                    if len(cells) < 3:
                        continue
                    
                    # Try to extract data
                    # Typical structure: [Entry Icon], Show Date, Show Name, Location, State, Body, End Date, Updated
                    try:
                        # Find show date (usually column 1 or 2)
                        show_date = None
                        show_name = None
                        
                        for cell_idx, cell in enumerate(cells[:5]):  # Check first 5 cells
                            text = cell.get_text(strip=True)
                            
                            # Look for date pattern (MMM DD, YYYY)
                            if re.search(r'[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}', text):
                                show_date = text
                                # Show name is likely next cell
                                if cell_idx + 1 < len(cells):
                                    show_name = cells[cell_idx + 1].get_text(strip=True)
                                break
                        
                        if not show_date or not show_name:
                            continue
                        
                        # Check if 2014 show
                        if not is_2014_show(show_date):
                            continue
                        
                        # Try to find ShowGUID in links
                        show_guid = None
                        
                        # Look for links in the row
                        links = row.find_all('a')
                        for link in links:
                            href = link.get('href', '')
                            
                            # Check if href contains ShowGUID
                            if 'ShowGUID=' in href:
                                # Parse the URL
                                # Handle archive.org wrapped URLs
                                if 'web.archive.org' in href:
                                    # Extract original URL from archive URL
                                    match = re.search(r'https?://[^/]+/\d+/(.*)', href)
                                    if match:
                                        href = match.group(1)
                                
                                # Now parse for ShowGUID
                                if 'ShowGUID=' in href:
                                    try:
                                        parsed = urlparse(href)
                                        params = parse_qs(parsed.query)
                                        if 'ShowGUID' in params:
                                            show_guid = params['ShowGUID'][0]
                                            break
                                    except:
                                        # Try regex
                                        match = re.search(r'ShowGUID=([a-fA-F0-9-]+)', href)
                                        if match:
                                            show_guid = match.group(1)
                                            break
                        
                        if show_guid:
                            shows.append({
                                'ShowGUID': show_guid,
                                'ShowName': show_name,
                                'ShowDate': show_date
                            })
                            print(f"    [{len(shows)}] {show_name} - {show_date}")
                            print(f"        GUID: {show_guid}")
                    
                    except Exception as e:
                        continue
        
        return shows
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        return []

def main():
    print("="*60)
    print("Parse Internet Archive 2014 Shows")
    print("="*60)
    
    all_shows = []
    guids_seen = set()
    
    for url in ARCHIVE_URLS:
        shows = extract_shows_from_archive(url)
        
        # Deduplicate
        for show in shows:
            if show['ShowGUID'] not in guids_seen:
                guids_seen.add(show['ShowGUID'])
                all_shows.append(show)
    
    print(f"\n{'='*60}")
    print(f"Total unique 2014 shows found: {len(all_shows)}")
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
        
        # Display summary
        print(f"\nSample shows:")
        for show in all_shows[:20]:
            print(f"  • {show['ShowName']}")
            print(f"    Date: {show['ShowDate']}")
            print(f"    GUID: {show['ShowGUID']}")
    else:
        print("\nNo shows found. The archived pages may not contain ShowGUID links.")
        print("Recommendation: Use Selenium to interact with archived pages")

if __name__ == '__main__':
    main()
