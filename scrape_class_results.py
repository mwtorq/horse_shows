"""
Scraper to collect class results data for each show
Navigates to ClassResults page for each ShowGUID and captures:
- Class summary data (Class, Class Name, Class Type, Division Name, Entries, Placings)
- Expanded entry details (Place, Entry, Horse, Rider, Country, Owner, Trainer, Prize, etc.)
Saves to sResults.ShowResults and sResults.Competitors tables
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import pyodbc

def setup_driver(headless=True):
    """Setup Chrome WebDriver"""
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        return driver
    except Exception as e:
        print(f"Error setting up driver: {e}")
        if headless:
            print("Retrying without headless mode...")
            return setup_driver(headless=False)
        raise

def get_db_connection():
    """Get SQL Server database connection"""
    drivers = [
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 18 for SQL Server',
        'SQL Server',
        'SQL Server Native Client 11.0',
    ]
    
    for driver in drivers:
        try:
            conn_str = f'DRIVER={{{driver}}};SERVER=localhost\\SQLEXPRESS;DATABASE=HorseShows;Trusted_Connection=yes;'
            conn = pyodbc.connect(conn_str)
            print(f"[OK] Connected to HorseShows database using driver: {driver}")
            return conn
        except Exception as e:
            if driver == drivers[-1]:  # Last driver
                print(f"[ERROR] Database connection failed with all drivers: {e}")
                raise
            continue

def reseed_identity_if_empty(conn, schema_name, table_name, identity_column='ID'):
    """Reseed identity column to 0 if table is empty"""
    try:
        cursor = conn.cursor()
        # Check if table is empty
        cursor.execute(f"SELECT COUNT(*) FROM {schema_name}.{table_name}")
        row_count = cursor.fetchone()[0]
        
        if row_count == 0:
            # Reseed identity to 0
            cursor.execute(f"DBCC CHECKIDENT ('{schema_name}.{table_name}', RESEED, 0)")
            conn.commit()
            print(f"  [OK] Reseeded identity column for {schema_name}.{table_name} to 0 (table is empty)")
        cursor.close()
    except Exception as e:
        # Ignore errors - table might not exist yet or might not have identity column
        pass

def create_competitors_table_if_not_exists(conn):
    """Create the Competitors table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        
        # Create schema if it doesn't exist (should already exist)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'sResults')
            BEGIN
                EXEC('CREATE SCHEMA sResults')
            END
        """)
        conn.commit()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'Competitors'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating sResults.Competitors table...")
            cursor.execute("""
                CREATE TABLE sResults.Competitors (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    Rider NVARCHAR(500),
                    Owner NVARCHAR(500),
                    Trainer NVARCHAR(500),
                    CreatedDate DATETIME DEFAULT GETDATE(),
                    UpdatedDate DATETIME DEFAULT GETDATE()
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_Competitors_Rider ON sResults.Competitors(Rider)")
            cursor.execute("CREATE INDEX IX_Competitors_Owner ON sResults.Competitors(Owner)")
            cursor.execute("CREATE INDEX IX_Competitors_Trainer ON sResults.Competitors(Trainer)")
            
            conn.commit()
            print("[OK] Competitors table created successfully")
        else:
            print("[OK] Competitors table already exists")
            # Reseed identity if table is empty
            reseed_identity_if_empty(conn, 'sResults', 'Competitors', 'ID')
        
        cursor.close()
    except Exception as e:
        print(f"[ERROR] Error creating Competitors table: {e}")
        raise

def create_showclass_table_if_not_exists(conn):
    """Create the ShowClass table if it doesn't exist, or migrate if it has old structure"""
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowClass'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating sResults.ShowClass table...")
            cursor.execute("""
                CREATE TABLE sResults.ShowClass (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    ShowListID INT NOT NULL,
                    Class NVARCHAR(200),
                    ClassName NVARCHAR(500),
                    ClassType NVARCHAR(200),
                    DivisionName NVARCHAR(200),
                    Entries INT,
                    Placings INT,
                    CreatedDate DATETIME DEFAULT GETDATE(),
                    UpdatedDate DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (ShowListID) REFERENCES sResults.ShowList(ID)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_ShowClass_ShowListID ON sResults.ShowClass(ShowListID)")
            cursor.execute("CREATE INDEX IX_ShowClass_Class ON sResults.ShowClass(Class)")
            
            conn.commit()
            print("[OK] ShowClass table created successfully")
        else:
            # Check if table has old structure (ShowGUID column)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = 'sResults' 
                AND TABLE_NAME = 'ShowClass' 
                AND COLUMN_NAME = 'ShowGUID'
            """)
            has_old_structure = cursor.fetchone()[0] > 0
            
            if has_old_structure:
                print("[WARNING] ShowClass table has old structure (ShowGUID). Dropping and recreating...")
                print("[NOTE] Existing ShowClass data will be lost and must be re-scraped.")
                
                # Drop foreign key constraints from ShowResults that reference ShowClass
                try:
                    cursor.execute("""
                        SELECT 
                            fk.name AS FK_Name,
                            OBJECT_NAME(fk.parent_object_id) AS Table_Name
                        FROM sys.foreign_keys AS fk
                        INNER JOIN sys.foreign_key_columns AS fkc 
                            ON fk.object_id = fkc.constraint_object_id
                        INNER JOIN sys.tables AS t 
                            ON fkc.referenced_object_id = t.object_id
                        INNER JOIN sys.schemas AS s 
                            ON t.schema_id = s.schema_id
                        WHERE s.name = 'sResults' 
                        AND t.name = 'ShowClass'
                    """)
                    fk_constraints = cursor.fetchall()
                    for fk_row in fk_constraints:
                        fk_name = fk_row[0]
                        table_name = fk_row[1]
                        try:
                            print(f"  Dropping foreign key constraint: {fk_name} from {table_name}")
                            cursor.execute(f"ALTER TABLE sResults.{table_name} DROP CONSTRAINT [{fk_name}]")
                            conn.commit()
                        except Exception as e:
                            print(f"    [WARNING] Could not drop FK constraint {fk_name}: {e}")
                except Exception as e:
                    print(f"  [WARNING] Error finding FK constraints: {e}")
                
                # Drop existing indexes
                try:
                    cursor.execute("DROP INDEX IF EXISTS IX_ShowClass_ShowGUID ON sResults.ShowClass")
                except:
                    pass
                try:
                    cursor.execute("DROP INDEX IF EXISTS IX_ShowClass_ShowListID ON sResults.ShowClass")
                except:
                    pass
                try:
                    cursor.execute("DROP INDEX IF EXISTS IX_ShowClass_Class ON sResults.ShowClass")
                except:
                    pass
                
                # Drop the table
                cursor.execute("DROP TABLE sResults.ShowClass")
                conn.commit()
                
                # Recreate with new structure
                print("Creating sResults.ShowClass table with new structure...")
                cursor.execute("""
                    CREATE TABLE sResults.ShowClass (
                        ID INT IDENTITY(1,1) PRIMARY KEY,
                        ShowListID INT NOT NULL,
                        Class NVARCHAR(200),
                        ClassName NVARCHAR(500),
                        ClassType NVARCHAR(200),
                        DivisionName NVARCHAR(200),
                        Entries INT,
                        Placings INT,
                        CreatedDate DATETIME DEFAULT GETDATE(),
                        UpdatedDate DATETIME DEFAULT GETDATE(),
                        FOREIGN KEY (ShowListID) REFERENCES sResults.ShowList(ID)
                    )
                """)
                
                # Create indexes
                cursor.execute("CREATE INDEX IX_ShowClass_ShowListID ON sResults.ShowClass(ShowListID)")
                cursor.execute("CREATE INDEX IX_ShowClass_Class ON sResults.ShowClass(Class)")
                
                conn.commit()
                print("[OK] ShowClass table recreated with new structure")
            else:
                # Check if it has the new structure
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = 'sResults' 
                    AND TABLE_NAME = 'ShowClass' 
                    AND COLUMN_NAME = 'ShowListID'
                """)
                has_new_structure = cursor.fetchone()[0] > 0
                
                if has_new_structure:
                    print("[OK] ShowClass table already exists with correct structure")
                    # Reseed identity if table is empty
                    reseed_identity_if_empty(conn, 'sResults', 'ShowClass', 'ID')
                else:
                    print("[WARNING] ShowClass table exists but structure is unknown. Please verify manually.")
        
        cursor.close()
    except Exception as e:
        print(f"[ERROR] Error creating/migrating ShowClass table: {e}")
        raise

def create_horse_table_if_not_exists(conn):
    """Create the Horse table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'Horse'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating sResults.Horse table...")
            cursor.execute("""
                CREATE TABLE sResults.Horse (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    HorseName NVARCHAR(500) NOT NULL UNIQUE,
                    OwnerID INT,
                    CreatedDate DATETIME DEFAULT GETDATE(),
                    UpdatedDate DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (OwnerID) REFERENCES sResults.Competitors(ID)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_Horse_HorseName ON sResults.Horse(HorseName)")
            cursor.execute("CREATE INDEX IX_Horse_OwnerID ON sResults.Horse(OwnerID)")
            
            conn.commit()
            print("[OK] Horse table created successfully")
        else:
            print("[OK] Horse table already exists")
            # Reseed identity if table is empty
            reseed_identity_if_empty(conn, 'sResults', 'Horse', 'ID')
        
        cursor.close()
    except Exception as e:
        print(f"[ERROR] Error creating Horse table: {e}")
        raise

def create_showresults_table_if_not_exists(conn):
    """Create the ShowResults table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ShowResults'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print("Creating sResults.ShowResults table...")
            cursor.execute("""
                CREATE TABLE sResults.ShowResults (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    ShowClassID INT NOT NULL,
                    Place INT,
                    Entry NVARCHAR(200),
                    HorseID INT,
                    Country NVARCHAR(50),
                    Prize NVARCHAR(100),
                    AddBack NVARCHAR(100),
                    Start NVARCHAR(100),
                    Score NVARCHAR(100),
                    [Percent] NVARCHAR(100),
                    USEF NVARCHAR(100),
                    EC NVARCHAR(100),
                    RiderID INT,
                    TrainerID INT,
                    CreatedDate DATETIME DEFAULT GETDATE(),
                    UpdatedDate DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (ShowClassID) REFERENCES sResults.ShowClass(ID),
                    FOREIGN KEY (HorseID) REFERENCES sResults.Horse(ID),
                    FOREIGN KEY (RiderID) REFERENCES sResults.Competitors(ID),
                    FOREIGN KEY (TrainerID) REFERENCES sResults.Competitors(ID)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_ShowResults_ShowClassID ON sResults.ShowResults(ShowClassID)")
            cursor.execute("CREATE INDEX IX_ShowResults_HorseID ON sResults.ShowResults(HorseID)")
            cursor.execute("CREATE INDEX IX_ShowResults_RiderID ON sResults.ShowResults(RiderID)")
            cursor.execute("CREATE INDEX IX_ShowResults_TrainerID ON sResults.ShowResults(TrainerID)")
            
            conn.commit()
            print("[OK] ShowResults table created successfully")
        else:
            print("[OK] ShowResults table already exists")
            # Reseed identity if table is empty
            reseed_identity_if_empty(conn, 'sResults', 'ShowResults', 'ID')
        
        cursor.close()
    except Exception as e:
        print(f"[ERROR] Error creating ShowResults table: {e}")
        raise

def get_or_create_competitor_by_role(conn, name, role_type):
    """
    Get existing competitor ID or create new competitor for a specific role
    role_type: 'Rider', 'Owner', or 'Trainer'
    Returns the Competitor ID
    """
    if not name or not name.strip():
        return None
    
    try:
        cursor = conn.cursor()
        name = name.strip()
        
        # Look up existing record by name in the appropriate role column
        # We check if the person exists in any role (Rider, Owner, or Trainer)
        cursor.execute("""
            SELECT ID FROM sResults.Competitors 
            WHERE Rider = ? OR Owner = ? OR Trainer = ?
        """, name, name, name)
        
        existing = cursor.fetchone()
        
        if existing:
            competitor_id = existing[0]
            # Update the appropriate role column if it's currently NULL
            if role_type == 'Rider':
                cursor.execute("""
                    UPDATE sResults.Competitors 
                    SET Rider = ?, UpdatedDate = GETDATE()
                    WHERE ID = ? AND Rider IS NULL
                """, name, competitor_id)
            elif role_type == 'Owner':
                cursor.execute("""
                    UPDATE sResults.Competitors 
                    SET Owner = ?, UpdatedDate = GETDATE()
                    WHERE ID = ? AND Owner IS NULL
                """, name, competitor_id)
            elif role_type == 'Trainer':
                cursor.execute("""
                    UPDATE sResults.Competitors 
                    SET Trainer = ?, UpdatedDate = GETDATE()
                    WHERE ID = ? AND Trainer IS NULL
                """, name, competitor_id)
            
            conn.commit()
            return competitor_id
        else:
            # Insert new competitor with the role filled in
            if role_type == 'Rider':
                cursor.execute("""
                    INSERT INTO sResults.Competitors (Rider, Owner, Trainer)
                    OUTPUT INSERTED.ID
                    VALUES (?, NULL, NULL)
                """, name)
            elif role_type == 'Owner':
                cursor.execute("""
                    INSERT INTO sResults.Competitors (Rider, Owner, Trainer)
                    OUTPUT INSERTED.ID
                    VALUES (NULL, ?, NULL)
                """, name)
            elif role_type == 'Trainer':
                cursor.execute("""
                    INSERT INTO sResults.Competitors (Rider, Owner, Trainer)
                    OUTPUT INSERTED.ID
                    VALUES (NULL, NULL, ?)
                """, name)
            else:
                return None
            
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"      [WARNING] Error getting/creating competitor ({role_type}): {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()

def activate_shows_by_year_tab(driver):
    """Activate the 'Shows By Year' tab"""
    print("Activating 'Shows By Year' tab...")
    
    try:
        time.sleep(3)
        
        # Try multiple methods to find the tab
        shows_by_year_tab = None
        
        # Method 1: Find all tabs and search by text
        try:
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            print(f"  Found {len(tabs)} tabs")
            for tab in tabs:
                tab_text = tab.text.strip()
                print(f"    Tab text: '{tab_text}'")
                if 'Shows By Year' in tab_text or 'By Year' in tab_text:
                    shows_by_year_tab = tab
                    print(f"  [OK] Found 'Shows By Year' tab by text")
                    break
        except Exception as e:
            print(f"  [DEBUG] Method 1 error: {e}")
        
        # Method 2: Try XPath with span
        if not shows_by_year_tab:
            try:
                shows_by_year_tab = driver.find_element(By.XPATH, 
                    "//li[contains(@class, 'dxtc-tab')]//span[contains(text(), 'Shows By Year')]/ancestor::li[1]")
                print(f"  [OK] Found 'Shows By Year' tab by XPath (span)")
            except:
                pass
        
        # Method 3: Try XPath with any text node
        if not shows_by_year_tab:
            try:
                shows_by_year_tab = driver.find_element(By.XPATH, 
                    "//li[contains(@class, 'dxtc-tab')][contains(., 'Shows By Year')]")
                print(f"  [OK] Found 'Shows By Year' tab by XPath (contains)")
            except:
                pass
        
        # Method 4: Try finding by link text
        if not shows_by_year_tab:
            try:
                link = driver.find_element(By.PARTIAL_LINK_TEXT, "Shows By Year")
                shows_by_year_tab = link.find_element(By.XPATH, "./ancestor::li[1]")
                print(f"  [OK] Found 'Shows By Year' tab by link text")
            except:
                pass
        
        if not shows_by_year_tab:
            print("  [ERROR] Could not find 'Shows By Year' tab using any method")
            return False
        
        # Check if already active (re-find to avoid stale element)
        try:
            tab_id = shows_by_year_tab.get_attribute('id') or ''
            tab_text_ref = shows_by_year_tab.text.strip()
            
            # Re-find the tab to avoid stale element
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            shows_by_year_tab_refresh = None
            for tab in tabs:
                if tab.get_attribute('id') == tab_id or tab.text.strip() == tab_text_ref:
                    shows_by_year_tab_refresh = tab
                    break
            
            if shows_by_year_tab_refresh:
                classes = shows_by_year_tab_refresh.get_attribute('class') or ''
                if 'dxtc-activeTab' in classes:
                    print("  [OK] Tab is already active")
                    return True
            else:
                # Fallback: find by text again
                for tab in tabs:
                    if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                        shows_by_year_tab_refresh = tab
                        classes = tab.get_attribute('class') or ''
                        if 'dxtc-activeTab' in classes:
                            print("  [OK] Tab is already active")
                            return True
                        break
        except Exception as e:
            print(f"  [DEBUG] Error checking if tab is active: {e}")
        
        # Click the tab (re-find to avoid stale element)
        try:
            # Re-find tabs and the specific tab before clicking
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            target_tab = None
            for tab in tabs:
                if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                    target_tab = tab
                    break
            
            if not target_tab:
                print("  [ERROR] Could not re-find tab for clicking")
                return False
            
            link = target_tab.find_element(By.CSS_SELECTOR, "a.dxtc-link")
            driver.execute_script("arguments[0].scrollIntoView(true);", link)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", link)
            time.sleep(4)
            
            # Verify it's now active (re-find again)
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            for tab in tabs:
                if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                    classes = tab.get_attribute('class') or ''
                    if 'dxtc-activeTab' in classes:
                        print("  [OK] Tab activated successfully")
                        return True
                    else:
                        print("  [WARNING] Tab clicked but may not be active")
                        return True  # Still return True, might work anyway
            
            return True  # Assume it worked if we can't verify
        except Exception as e:
            print(f"  [ERROR] Error clicking tab: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print(f"  [ERROR] Error activating tab: {e}")
        import traceback
        traceback.print_exc()
        return False

def activate_class_results_tab(driver):
    """Activate the 'Class Results' tab on ShowDetails page"""
    print("  Activating 'Class Results' tab...")
    
    try:
        time.sleep(2)
        tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
        
        class_results_tab = None
        for tab in tabs:
            tab_text = tab.text.strip().lower()
            if 'class results' in tab_text or ('class' in tab_text and 'results' in tab_text):
                class_results_tab = tab
                break
        
        if not class_results_tab:
            # Try XPath method
            try:
                class_results_tab = driver.find_element(By.XPATH, 
                    "//li[contains(@class, 'dxtc-tab')]//span[contains(text(), 'Class Results')]/ancestor::li[1]")
            except:
                # Try finding by href
                try:
                    class_results_link = driver.find_element(By.CSS_SELECTOR, "a[href*='ClassResults']")
                    if class_results_link:
                        driver.execute_script("arguments[0].click();", class_results_link)
                        time.sleep(3)
                        return True
                except:
                    pass
        
        if class_results_tab:
            classes = class_results_tab.get_attribute('class') or ''
            if 'dxtc-activeTab' not in classes:
                link = class_results_tab.find_element(By.CSS_SELECTOR, "a.dxtc-link")
                driver.execute_script("arguments[0].scrollIntoView(true);", link)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", link)
                time.sleep(3)
            return True
        
        return False
    except Exception as e:
        print(f"  [WARNING] Error activating Class Results tab: {e}")
        return False

def select_year(driver, year):
    """Select a specific year in the year picker"""
    print(f"\nSelecting year {year}...")
    
    try:
        time.sleep(2)
        
        # Find the year picker element
        year_element = None
        year_picker_ids = [
            "MainContent_panFilter_ddShowYear_I",
            "MainContent_panFilter_ddShowYear",
            "ddShowYear_I",
            "ddShowYear",
        ]
        
        for picker_id in year_picker_ids:
            try:
                year_element = driver.find_element(By.ID, picker_id)
                break
            except:
                continue
        
        if not year_element:
            print(f"  [ERROR] Could not find year picker for year {year}")
            return False
        
        element_id = year_element.get_attribute('id') or ''
        year_value = str(year)
        
        print(f"  Setting year picker to {year_value}...")
        
        # Set the value using JavaScript
        driver.execute_script(f"arguments[0].value = '{year_value}';", year_element)
        driver.execute_script(f"arguments[0].setAttribute('value', '{year_value}');", year_element)
        
        # Get control ID for DevExpress event
        control_id = element_id
        if element_id.endswith('_I'):
            control_id = element_id[:-2]
        
        # Trigger DevExpress change event
        driver.execute_script(f"""
            var elem = arguments[0];
            elem.dispatchEvent(new Event('input', {{bubbles: true}}));
            elem.dispatchEvent(new Event('change', {{bubbles: true}}));
            elem.dispatchEvent(new Event('blur', {{bubbles: true}}));
            if (typeof ASPx !== 'undefined' && typeof ASPx.ETextChanged === 'function') {{
                ASPx.ETextChanged('{control_id}');
            }}
        """, year_element)
        
        # Wait for grid to update
        time.sleep(3)
        
        # Verify the value was set
        current_value = driver.execute_script("return arguments[0].value;", year_element)
        if str(year) in str(current_value):
            print(f"  [OK] Year {year} selected")
            return True
        else:
            print(f"  [WARNING] Year may not have been set correctly. Current value: {current_value}")
            return True  # Continue anyway
        
    except Exception as e:
        print(f"  [ERROR] Error selecting year {year}: {e}")
        return False

def get_show_data_from_database(conn, skip_processed=True):
    """Get ID, ShowGUID, Year, and ShowName from ShowList table where EndDate < today, ordered by ID
    
    Args:
        conn: Database connection
        skip_processed: If True, skip shows that already have ShowClass or ShowResults data
    """
    try:
        cursor = conn.cursor()
        
        if skip_processed:
            # Get shows that don't have existing ShowClass or ShowResults data
            cursor.execute("""
                SELECT sl.ID, sl.ShowGUID, sl.Year, sl.ShowName 
                FROM sResults.ShowList sl
                WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                AND sl.StartDate IS NOT NULL
                AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
                AND NOT EXISTS (
                    SELECT 1 FROM sResults.ShowClass sc 
                    WHERE sc.ShowListID = sl.ID
                )
                AND NOT EXISTS (
                    SELECT 1 FROM sResults.ShowResults sr
                    INNER JOIN sResults.ShowClass sc2 ON sr.ShowClassID = sc2.ID
                    WHERE sc2.ShowListID = sl.ID
                )
                ORDER BY sl.ID
            """)
            print("[OK] Filtering out shows with existing ShowClass or ShowResults data")
        else:
            # Get all shows regardless of existing data
            cursor.execute("""
                SELECT ID, ShowGUID, Year, ShowName 
                FROM sResults.ShowList 
                WHERE ShowGUID IS NOT NULL AND ShowGUID != ''
                AND StartDate IS NOT NULL
                AND CAST(EndDate AS DATE) < CAST(GETDATE() AS DATE)
                ORDER BY ID
            """)
        
        show_data = [(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]
        cursor.close()
        print(f"[OK] Found {len(show_data)} shows with EndDate < today")
        return show_data
    except Exception as e:
        print(f"[ERROR] Error getting show data from database: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_column_indices_for_class_grid(grid):
    """Determine column indices for class summary grid by inspecting header row"""
    column_map = {
        'Class': None,
        'Class Name': None,
        'Class Type': None,
        'Division Name': None,
        'Entries': None,
        'Placings': None,
    }
    
    try:
        # Find header row
        header_rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='HeaderRow'], tr.dxgvHeaderRow")
        if header_rows:
            header_cells = header_rows[0].find_elements(By.TAG_NAME, "th, td")
            print(f"  [DEBUG] Header row has {len(header_cells)} cells")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip()
                cell_text_lower = cell_text.lower()
                print(f"    Header cell {idx}: '{cell_text}'")
                
                # Skip command column (first column is usually expand/collapse buttons)
                if idx == 0 and ('button' in cell_text_lower or cell_text == ''):
                    continue
                
                col_idx = idx
                if 'class' in cell_text_lower and 'name' not in cell_text_lower and 'type' not in cell_text_lower:
                    column_map['Class'] = col_idx
                    print(f"      -> Mapped to 'Class'")
                elif 'class name' in cell_text_lower or ('name' in cell_text_lower and 'class' in cell_text_lower):
                    column_map['Class Name'] = col_idx
                    print(f"      -> Mapped to 'Class Name'")
                elif 'class type' in cell_text_lower or ('type' in cell_text_lower and 'class' in cell_text_lower):
                    column_map['Class Type'] = col_idx
                    print(f"      -> Mapped to 'Class Type'")
                elif 'division' in cell_text_lower:
                    column_map['Division Name'] = col_idx
                    print(f"      -> Mapped to 'Division Name'")
                elif 'entries' in cell_text_lower:
                    column_map['Entries'] = col_idx
                    print(f"      -> Mapped to 'Entries'")
                elif 'placings' in cell_text_lower:
                    column_map['Placings'] = col_idx
                    print(f"      -> Mapped to 'Placings'")
    except Exception as e:
        print(f"  [WARNING] Error inspecting header: {e}")
        pass
    
    # Default mapping if header inspection failed (based on actual structure from debug output)
    # Cell 0: command column (skip), Cell 1: empty, Cell 2: Class, Cell 3: ClassName, 
    # Cell 4: ClassType, Cell 5: DivisionName, Cell 6: Entries, Cell 7: Placings
    if all(v is None for v in column_map.values()):
        print(f"  [WARNING] Could not map columns from header, using defaults")
        column_map = {
            'Class': 2,
            'Class Name': 3,
            'Class Type': 4,
            'Division Name': 5,
            'Entries': 6,
            'Placings': 7,
        }
    
    return column_map

def get_column_indices_for_entry_grid(detail_grid):
    """Determine column indices for entry detail grid"""
    column_map = {
        'Place': None,
        'Entry': None,
        'Horse': None,
        'Rider': None,
        'Country': None,
        'Owner': None,
        'Trainer': None,
        'Prize': None,
        'AddBack': None,
        'Start': None,
        'Score': None,
        'Percent': None,
        'USEF': None,
        'EC': None,
    }
    
    try:
        # Try multiple methods to find header row
        header_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='HeaderRow'], tr.dxgvHeaderRow")
        
        # If no header rows found, try finding by class
        if not header_rows:
            all_rows = detail_grid.find_elements(By.TAG_NAME, "tr")
            for row in all_rows:
                row_class = row.get_attribute('class') or ''
                row_id = row.get_attribute('id') or ''
                if 'Header' in row_class or 'Header' in row_id:
                    header_rows.append(row)
                    break
        
        # If still no header, use first row as potential header
        if not header_rows:
            all_rows = detail_grid.find_elements(By.TAG_NAME, "tr")
            if all_rows:
                header_rows = [all_rows[0]]
        
        if header_rows:
            header_cells = header_rows[0].find_elements(By.TAG_NAME, "th, td")
            print(f"        [DEBUG] Found {len(header_cells)} header cells")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip().lower()
                col_idx = idx
                if idx < 5:  # Debug first few cells
                    print(f"          Header cell {idx}: '{cell_text}'")
                
                if 'place' in cell_text:
                    column_map['Place'] = col_idx
                elif 'entry' in cell_text:
                    column_map['Entry'] = col_idx
                elif 'horse' in cell_text:
                    column_map['Horse'] = col_idx
                elif 'rider' in cell_text:
                    column_map['Rider'] = col_idx
                elif 'cntry' in cell_text or 'country' in cell_text:
                    column_map['Country'] = col_idx
                elif 'owner' in cell_text:
                    column_map['Owner'] = col_idx
                elif 'trainer' in cell_text:
                    column_map['Trainer'] = col_idx
                elif 'prize' in cell_text:
                    column_map['Prize'] = col_idx
                elif 'addback' in cell_text or 'add back' in cell_text:
                    column_map['AddBack'] = col_idx
                elif 'start' in cell_text:
                    column_map['Start'] = col_idx
                elif 'score' in cell_text:
                    column_map['Score'] = col_idx
                elif 'percent' in cell_text:
                    column_map['Percent'] = col_idx
                elif 'usef' in cell_text:
                    column_map['USEF'] = col_idx
                elif 'ec' in cell_text and 'cntry' not in cell_text:
                    column_map['EC'] = col_idx
        
        # If no mappings found, use default positional mapping based on known structure
        # "Entries That Placed" table structure: Place, Entry, Horse, Rider, Cntry, Owner, Trainer,
        # Prize, AddBack, Start, Score, Percent, USEF, EC
        if not any(column_map.values()):
            print(f"        [DEBUG] No header mappings found, using default positional mapping")
            # Try to determine column count from a data row to verify structure
            try:
                data_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                if data_rows:
                    sample_cells = data_rows[0].find_elements(By.TAG_NAME, "td")
                    cell_count = len(sample_cells)
                    print(f"        [DEBUG] Sample data row has {cell_count} cells")
                    
                    # Use positional mapping based on "Entries That Placed" table structure
                    # Columns: Place, Entry, Horse, Rider, Cntry, Owner, Trainer, Prize, AddBack, Start, Score, Percent, USEF, EC
                    if cell_count >= 14:
                        column_map['Place'] = 0
                        column_map['Entry'] = 1
                        column_map['Horse'] = 2
                        column_map['Rider'] = 3
                        column_map['Country'] = 4  # Maps to Cntry column
                        column_map['Owner'] = 5
                        column_map['Trainer'] = 6
                        column_map['Prize'] = 7
                        column_map['AddBack'] = 8
                        column_map['Start'] = 9
                        column_map['Score'] = 10
                        column_map['Percent'] = 11
                        column_map['USEF'] = 12
                        column_map['EC'] = 13
                        print(f"        [DEBUG] Applied default positional mapping (14 columns)")
                    elif cell_count >= 10:
                        # Fallback for fewer columns
                        column_map['Place'] = 0
                        column_map['Entry'] = 1
                        column_map['Horse'] = 2
                        column_map['Rider'] = 3
                        column_map['Country'] = 4
                        column_map['Owner'] = 5
                        column_map['Trainer'] = 6
                        column_map['Prize'] = 7
                        column_map['AddBack'] = 8
                        column_map['Start'] = 9
                        print(f"        [DEBUG] Applied default positional mapping ({cell_count} columns, partial)")
            except Exception as e:
                print(f"        [DEBUG] Error determining positional mapping: {e}")
    except Exception as e:
        print(f"        [DEBUG] Error in get_column_indices_for_entry_grid: {e}")
        import traceback
        traceback.print_exc()
    
    return column_map

def expand_row(driver, row_element):
    """Expand a row by clicking the expand button/icon"""
    try:
        # DevExpress detail rows: first cell has class dxgvDetailButton_Office2010Blue
        first_cell = row_element.find_element(By.TAG_NAME, "td")
        first_cell_class = first_cell.get_attribute('class') or ''
        
        # Check if this is a detail button cell
        if 'dxgvDetailButton' in first_cell_class:
            # Look for the expand/collapse image
            detail_images = first_cell.find_elements(By.TAG_NAME, "img")
            
            for img in detail_images:
                img_class = img.get_attribute('class') or ''
                img_onclick = img.get_attribute('onclick') or ''
                
                # Check if already expanded (has collapse button with GVHideDetailRow)
                if 'gvDetailExpandedButton' in img_class or 'GVHideDetailRow' in img_onclick:
                    # Already expanded
                    return True
                
                # Check if it's an expand button (GVShowDetailRow)
                if 'GVShowDetailRow' in img_onclick or ('gvDetail' in img_class and 'Expanded' not in img_class):
                    # Click to expand
                    driver.execute_script("arguments[0].click();", img)
                    time.sleep(0.5)
                    return True
            
            # If no specific image found, try clicking the first cell
            driver.execute_script("arguments[0].click();", first_cell)
            time.sleep(0.5)
            return True
        
        # Fallback: Try to find expand button in first cell (older method)
        expand_images = first_cell.find_elements(By.CSS_SELECTOR, 
            "img[src*='Plus'], img[src*='plus'], img[src*='Expand'], img[src*='expand']")
        
        expand_links = first_cell.find_elements(By.CSS_SELECTOR, 
            "a.dxgvCommandColumnItem, a[onclick*='Expand'], a[onclick*='expand']")
        
        expand_buttons = expand_images + expand_links
        
        if expand_buttons:
            driver.execute_script("arguments[0].click();", expand_buttons[0])
            time.sleep(0.5)
            return True
        
        # Try clicking the first cell directly
        driver.execute_script("arguments[0].click();", first_cell)
        time.sleep(0.5)
        return True
    except Exception as e:
        print(f"        [DEBUG] expand_row error: {e}")
        return False

def collapse_row(driver, row_element):
    """Collapse a row by clicking the collapse button/icon"""
    try:
        # Try to find collapse button in first cell
        first_cell = row_element.find_element(By.TAG_NAME, "td")
        collapse_buttons = first_cell.find_elements(By.CSS_SELECTOR, 
            "a.dxgvCommandColumnItem, img[src*='Minus'], img[src*='minus'], .dxgvCommandColumnItem")
        
        if collapse_buttons:
            driver.execute_script("arguments[0].click();", collapse_buttons[0])
            time.sleep(0.5)  # Wait for collapse
            return True
        
        # Try clicking the first cell directly (if already expanded, clicking again should collapse)
        driver.execute_script("arguments[0].click();", first_cell)
        time.sleep(0.5)
        return True
    except:
        return False

def extract_entry_details_from_row(row_element, entry_column_map):
    """Extract entry detail data from a row"""
    try:
        cells = row_element.find_elements(By.TAG_NAME, "td")
        if len(cells) < 3:
            return None
        
        entry_data = {}
        for field, idx in entry_column_map.items():
            if idx is not None and len(cells) > idx:
                entry_data[field] = cells[idx].text.strip()
            else:
                entry_data[field] = ''
        
        return entry_data
    except Exception as e:
        print(f"      [WARNING] Error extracting entry details: {e}")
        return None

def get_or_create_showclass(conn, show_list_id, class_summary):
    """Get existing ShowClass ID or create new ShowClass, return ID"""
    try:
        cursor = conn.cursor()
        
        # Parse numeric values
        entries = None
        placings = None
        
        try:
            entries_str = class_summary.get('Entries', '').strip()
            if entries_str:
                entries = int(entries_str)
        except:
            pass
        
        try:
            placings_str = class_summary.get('Placings', '').strip()
            if placings_str:
                placings = int(placings_str)
        except:
            pass
        
        # Look up existing ShowClass by ShowListID, Class, and ClassName
        cursor.execute("""
            SELECT ID FROM sResults.ShowClass 
            WHERE ShowListID = ? AND Class = ? AND ClassName = ?
        """, 
            show_list_id,
            class_summary.get('Class', ''),
            class_summary.get('Class Name', '')
        )
        
        existing = cursor.fetchone()
        
        if existing:
            return existing[0]
        else:
            # Insert new ShowClass
            cursor.execute("""
                INSERT INTO sResults.ShowClass 
                (ShowListID, Class, ClassName, ClassType, DivisionName, Entries, Placings)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                show_list_id,
                class_summary.get('Class', ''),
                class_summary.get('Class Name', ''),
                class_summary.get('Class Type', ''),
                class_summary.get('Division Name', ''),
                entries,
                placings
            )
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"    [WARNING] Error getting/creating ShowClass: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()

def get_or_create_horse(conn, horse_name, owner_id=None):
    """Get existing horse ID or create new horse, return ID"""
    if not horse_name or not horse_name.strip():
        return None
    
    try:
        cursor = conn.cursor()
        horse_name = horse_name.strip()
        
        # Look up existing horse by name
        cursor.execute("""
            SELECT ID, OwnerID FROM sResults.Horse 
            WHERE HorseName = ?
        """, horse_name)
        
        existing = cursor.fetchone()
        
        if existing:
            horse_id = existing[0]
            existing_owner_id = existing[1]
            
            # Update owner if provided and current owner is NULL
            if owner_id and not existing_owner_id:
                cursor.execute("""
                    UPDATE sResults.Horse 
                    SET OwnerID = ?, UpdatedDate = GETDATE()
                    WHERE ID = ?
                """, owner_id, horse_id)
                conn.commit()
            
            return horse_id
        else:
            # Insert new horse with owner if provided
            cursor.execute("""
                INSERT INTO sResults.Horse (HorseName, OwnerID)
                OUTPUT INSERTED.ID
                VALUES (?, ?)
            """, horse_name, owner_id)
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
    except Exception as e:
        print(f"      [WARNING] Error getting/creating horse: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()

def save_show_result_to_database(conn, show_class_id, entry_details):
    """Save entry detail result to ShowResults table (with duplicate check)"""
    if not entry_details:
        return False
    
    cursor = conn.cursor()
    
    try:
        # Check for duplicate entry in this class
        entry_number = entry_details.get('Entry', '').strip() if entry_details.get('Entry') else None
        place = None
        try:
            place_str = entry_details.get('Place', '').strip()
            if place_str:
                place = int(place_str)
        except:
            pass
        
        # Check if this entry already exists for this class
        if entry_number:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM sResults.ShowResults 
                WHERE ShowClassID = ? AND Entry = ?
            """, show_class_id, entry_number)
        elif place is not None:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM sResults.ShowResults 
                WHERE ShowClassID = ? AND Place = ?
            """, show_class_id, place)
        else:
            # Can't check for duplicates without entry number or place
            pass
        
        if entry_number or place is not None:
            duplicate_count = cursor.fetchone()[0]
            if duplicate_count > 0:
                return False  # Duplicate entry, don't save
        
    except Exception as e:
        # If duplicate check fails, continue anyway
        pass
    
    try:
        # Get or create competitor IDs for Rider and Trainer
        rider_id = None
        trainer_id = None
        
        rider = entry_details.get('Rider', '').strip() if entry_details.get('Rider') else None
        trainer = entry_details.get('Trainer', '').strip() if entry_details.get('Trainer') else None
        
        if rider:
            rider_id = get_or_create_competitor_by_role(conn, rider, 'Rider')
        if trainer:
            trainer_id = get_or_create_competitor_by_role(conn, trainer, 'Trainer')
        
        # Get or create owner ID (for horse)
        owner_id = None
        owner = entry_details.get('Owner', '').strip() if entry_details.get('Owner') else None
        if owner:
            owner_id = get_or_create_competitor_by_role(conn, owner, 'Owner')
        
        # Get or create horse ID (with owner)
        horse_id = None
        horse_name = entry_details.get('Horse', '').strip() if entry_details.get('Horse') else None
        if horse_name:
            horse_id = get_or_create_horse(conn, horse_name, owner_id)
        
        # Parse numeric values
        place = None
        try:
            place_str = entry_details.get('Place', '').strip()
            if place_str:
                place = int(place_str)
        except:
            pass
        
        # Insert into ShowResults
        cursor.execute("""
            INSERT INTO sResults.ShowResults 
            (ShowClassID, Place, Entry, HorseID, Country, Prize, AddBack, Start, Score, [Percent], USEF, EC,
             RiderID, TrainerID)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            show_class_id,
            place,
            entry_details.get('Entry', ''),
            horse_id,
            entry_details.get('Country', ''),
            entry_details.get('Prize', ''),
            entry_details.get('AddBack', ''),
            entry_details.get('Start', ''),
            entry_details.get('Score', ''),
            entry_details.get('Percent', ''),
            entry_details.get('USEF', ''),
            entry_details.get('EC', ''),
            rider_id,
            trainer_id
        )
        
        conn.commit()
        return True
    except Exception as e:
        print(f"      [WARNING] Error saving ShowResult to database: {e}")
        conn.rollback()
        return False
    finally:
        cursor.close()

def find_and_click_show_row(driver, show_guid, year, show_name):
    """Find and click the show row in the ShowSelector grid to navigate to ClassResults"""
    try:
        # Wait for grid to load
        time.sleep(3)
        
        # Find the grid - DevExpress GridView typically has ID containing 'grMaster'
        grid = None
        grid_selectors = [
            "table[id*='grMaster'][id*='MainTable']",
            "table[id*='grMaster']",
            "table[id*='MainContent'][id*='gr']",
            "table.dxgvTable",
            "table[id*='DXMainTable']",
        ]
        
        for selector in grid_selectors:
            try:
                grids = driver.find_elements(By.CSS_SELECTOR, selector)
                for g in grids:
                    if g.is_displayed():
                        grid = g
                        break
                if grid:
                    break
            except:
                continue
        
        if not grid:
            # Try fallback
            try:
                all_tables = driver.find_elements(By.TAG_NAME, "table")
                for table in all_tables:
                    if table.is_displayed() and len(table.find_elements(By.TAG_NAME, "tr")) > 1:
                        grid = table
                        break
            except:
                pass
        
        if not grid:
            print(f"  [ERROR] Could not find grid for year {year}")
            return False
        
        # Find all data rows
        rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
        if not rows:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            rows = []
            for r in all_rows:
                row_id = r.get_attribute('id') or ''
                row_class = r.get_attribute('class') or ''
                if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                    rows.append(r)
        
        # Find the row with matching Show Name
        # Column structure: 0=Command, 1=Date, 2=Name, 3=Location, 4=State, 5=Body
        target_row_index = None
        for idx, row in enumerate(rows):
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 3:
                    # Show Name is typically at index 2
                    show_name_cell = cells[2] if len(cells) > 2 else cells[1]
                    row_show_name = show_name_cell.text.strip()
                    
                    # Match by Show Name (case-insensitive partial match)
                    if show_name and show_name.lower() in row_show_name.lower():
                        target_row_index = idx
                        print(f"  Found matching show row: {row_show_name}")
                        break
            except StaleElementReferenceException:
                # Re-find rows if they become stale
                rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                if not rows:
                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                    rows = []
                    for r in all_rows:
                        row_id = r.get_attribute('id') or ''
                        row_class = r.get_attribute('class') or ''
                        if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                            rows.append(r)
                continue
            except Exception as e:
                continue
        
        if target_row_index is not None:
            try:
                # Re-find the grid and rows to avoid stale elements
                grid = driver.find_element(By.CSS_SELECTOR, 
                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                if not rows:
                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                    rows = []
                    for r in all_rows:
                        row_id = r.get_attribute('id') or ''
                        row_class = r.get_attribute('class') or ''
                        if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                            rows.append(r)
                
                if target_row_index < len(rows):
                    target_row = rows[target_row_index]
                    cells = target_row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:
                        clickable_cell = cells[2]  # Show Name cell
                        driver.execute_script("arguments[0].click();", clickable_cell)
                        time.sleep(3)  # Wait for navigation to ShowDetails page
                        
                        # Now click the ClassResults tab on the ShowDetails page
                        if activate_class_results_tab(driver):
                            print(f"  [OK] Class Results tab activated")
                            return True
                        else:
                            print(f"  [WARNING] Could not activate Class Results tab, trying direct navigation")
                            # Fallback to direct navigation
                            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                            driver.get(class_results_url)
                            time.sleep(3)
                            return True
            except StaleElementReferenceException:
                print(f"  [WARNING] Stale element when clicking, trying direct navigation")
            except Exception as e:
                print(f"  [WARNING] Error clicking show row: {e}")
        
        # If we couldn't find it by name, try direct navigation
        print(f"  [WARNING] Could not find show row by name '{show_name}', navigating directly to ClassResults")
        class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
        driver.get(class_results_url)
        time.sleep(3)
        return True
        
    except Exception as e:
        print(f"  [ERROR] Error finding/clicking show row: {e}")
        # Fallback to direct navigation
        class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
        driver.get(class_results_url)
        time.sleep(3)
        return True

def scrape_class_results_for_show(driver, show_list_id, show_guid, year, show_name, conn):
    """Scrape class results for a single show"""
    print(f"\n{'='*60}")
    print(f"Scraping class results for ShowGUID: {show_guid} (Year: {year})")
    print(f"{'='*60}")
    
    results_count = 0
    
    try:
        # Navigate to ShowSelector page first
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        if 'ShowSelector' not in driver.current_url:
            print("  Navigating to ShowSelector page...")
            driver.get(show_selector_url)
            time.sleep(3)
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(driver):
            print(f"  [WARNING] Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            driver.get(class_results_url)
            time.sleep(3)
        else:
            # Select the year
            if not select_year(driver, year):
                print(f"  [WARNING] Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                driver.get(class_results_url)
                time.sleep(3)
            else:
                # Find and click the show row to navigate to ClassResults
                if not find_and_click_show_row(driver, show_guid, year, show_name):
                    print(f"  [WARNING] Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    driver.get(class_results_url)
                    time.sleep(3)
        
        # Wait for the ClassResults page to load - look for the grid table
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
            )
        except TimeoutException:
            print(f"  [WARNING] Grid table not found after 10 seconds")
        
        time.sleep(2)  # Additional wait for JavaScript to populate grid
        
        # Find the results grid/table
        grid = None
        grid_selectors = [
            "table[id*='grMaster'][id*='DXMainTable']",
            "table[id*='grMaster']",
            "table[id*='DXMainTable']",
            "table.dxgvTable_Office2010Blue",
            "table.dxgvTable",
            "table[id*='MainContent'][id*='gr']",
        ]
        
        for selector in grid_selectors:
            try:
                grids = driver.find_elements(By.CSS_SELECTOR, selector)
                for g in grids:
                    if g.is_displayed():
                        tr_count = len(g.find_elements(By.TAG_NAME, "tr"))
                        if tr_count > 1:
                            grid = g
                            print(f"  Found grid using selector: {selector} ({tr_count} rows)")
                            break
                if grid:
                    break
            except Exception as e:
                continue
        
        if not grid:
            # Try fallback - find any visible table with class dxgvTable
            try:
                all_tables = driver.find_elements(By.CSS_SELECTOR, "table.dxgvTable")
                for table in all_tables:
                    if table.is_displayed():
                        tr_count = len(table.find_elements(By.TAG_NAME, "tr"))
                        # Prefer tables with more rows (more likely to be the main data table)
                        if tr_count > 3:
                            grid = table
                            print(f"  Found grid using fallback method ({tr_count} rows)")
                            break
            except:
                pass
        
        if not grid:
            # Last resort - find table with most data rows (exclude small footer tables)
            try:
                all_tables = driver.find_elements(By.TAG_NAME, "table")
                best_table = None
                max_data_rows = 0
                for table in all_tables:
                    if table.is_displayed():
                        # Count potential data rows (rows with multiple cells, excluding headers)
                        rows = table.find_elements(By.TAG_NAME, "tr")
                        data_row_count = 0
                        for row in rows:
                            cells = row.find_elements(By.TAG_NAME, "td")
                            row_text = row.text.lower()
                            # Count as data row if has cells and not footer/copyright text
                            if len(cells) >= 3 and not any(x in row_text for x in ['copyright', 'privacy policy', 'contact']):
                                data_row_count += 1
                        
                        if data_row_count > max_data_rows:
                            max_data_rows = data_row_count
                            best_table = table
                
                if best_table and max_data_rows > 0:
                    grid = best_table
                    print(f"  Found grid using last resort method ({max_data_rows} data rows)")
            except:
                pass
        
        if not grid:
            print(f"  [WARNING] Could not find results grid for ShowGUID: {show_guid}")
            return 0
        
        # Get column mapping for class summary
        class_column_map = get_column_indices_for_class_grid(grid)
        print(f"  Class column mapping: {class_column_map}")
        
        # Find all class summary rows
        # Try multiple strategies to find data rows
        class_rows = []
        
        # Strategy 1: Look for rows with DataRow in ID
        class_rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
        
        # Strategy 2: Look for rows with dxgvDataRow class
        if not class_rows:
            class_rows = grid.find_elements(By.CSS_SELECTOR, "tr.dxgvDataRow")
        
        # Strategy 3: Get all rows and filter intelligently
        if not class_rows:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            for r in all_rows:
                row_id = r.get_attribute('id') or ''
                row_class = r.get_attribute('class') or ''
                
                # Exclude header, filter, footer, and detail rows
                exclude_patterns = ['HeaderRow', 'FilterRow', 'FooterRow', 'DetailRow', 
                                   'PagerBottomRow', 'GroupRow', 'dxgvHeaderRow', 
                                   'dxgvFilterRow', 'dxgvFooterRow']
                if any(pattern in row_id or pattern in row_class for pattern in exclude_patterns):
                    continue
                
                # Check for data row indicators
                is_data_row = ('DataRow' in row_id or 'dxgvDataRow' in row_class or
                              'dxgv' in row_class.lower() and 'data' in row_class.lower())
                
                # Include rows that have data cells (at least 3 td elements, not th)
                cells = r.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 3:
                    # Additional validation: check if this looks like a real data row
                    # Exclude rows that contain copyright, footer, or navigation text
                    row_text = r.text.lower()
                    exclude_text = ['copyright', 'all rights reserved', 'privacy policy', 
                                   'terms of service', 'contact', 'version', 'security alerts']
                    if any(exclude in row_text for exclude in exclude_text):
                        continue
                    
                    # Check if the row has numeric data (like Entries column should have numbers)
                    # This helps filter out footer/header rows
                    has_numeric = any(cell.text.strip().isdigit() for cell in cells if cell.text.strip())
                    
                    class_rows.append(r)
                elif is_data_row and len(cells) >= 1:
                    # Even if fewer cells, if it's marked as a data row, include it (with same validation)
                    row_text = r.text.lower()
                    exclude_text = ['copyright', 'all rights reserved', 'privacy policy', 
                                   'terms of service', 'contact', 'version', 'security alerts']
                    if not any(exclude in row_text for exclude in exclude_text):
                        class_rows.append(r)
        
        print(f"  Found {len(class_rows)} class summary rows")
        
        # Debug: if no rows found, try to understand the structure
        if len(class_rows) == 0:
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            print(f"  [DEBUG] Total rows in grid: {len(all_rows)}")
            if len(all_rows) > 0:
                # Print first few rows' structure for debugging
                for i, r in enumerate(all_rows[:10]):
                    row_id = r.get_attribute('id') or 'no-id'
                    row_class = r.get_attribute('class') or 'no-class'
                    cells = r.find_elements(By.TAG_NAME, "td, th")
                    cell_text = ''
                    if cells:
                        cell_text = cells[0].text[:30] if cells[0].text else 'empty'
                    print(f"    Row {i+1}: id='{row_id[:60]}', class='{row_class[:60]}', cells={len(cells)}, first_cell='{cell_text}'")
        
        # PASS 1: Extract all class summary data and save to ShowClass table
        print(f"\n  PASS 1: Extracting class summaries...")
        class_data_list = []  # Store (row_index, class_summary, entries) for second pass
        
        for row_idx, class_row in enumerate(class_rows, 1):
            try:
                print(f"  Extracting class row {row_idx}/{len(class_rows)}...")

                # Re-find row to avoid stale element
                try:
                    grid = driver.find_element(By.CSS_SELECTOR, 
                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                    rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                    if not rows:
                        all_rows = grid.find_elements(By.TAG_NAME, "tr")
                        rows = []
                        for r in all_rows:
                            row_id = r.get_attribute('id') or ''
                            row_class = r.get_attribute('class') or ''
                            if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                rows.append(r)
                    
                    if row_idx <= len(rows):
                        class_row = rows[row_idx - 1]
                except:
                    pass

                # Extract class summary data
                cells = class_row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 3:
                    continue

                class_summary = {}
                for field, idx in class_column_map.items():
                    if idx is not None and len(cells) > idx:
                        class_summary[field] = cells[idx].text.strip()
                    else:
                        class_summary[field] = ''

                # Debug: Print first few cells to understand structure
                if row_idx == 1:
                    print(f"    [DEBUG] First row cell contents:")
                    for i, cell in enumerate(cells[:8]):
                        print(f"      Cell {i}: '{cell.text.strip()[:50]}'")

                # Validate that this looks like a real class row (not footer/copyright)
                class_text = class_summary.get('Class', '').lower()
                class_name_text = class_summary.get('Class Name', '').lower()
                combined_text = (class_text + ' ' + class_name_text).lower()

                exclude_text = ['copyright', 'all rights reserved', 'privacy policy', 
                               'terms of service', 'contact', 'version', 'security alerts',
                               'horseshowsonline', 'timeslice']

                if any(exclude in combined_text for exclude in exclude_text):
                    print(f"    Skipping footer row: {class_summary.get('Class', 'N/A')[:50]}")
                    continue

                # Handle Placings - if Cell 7 is empty, assume 0
                placings = class_summary.get('Placings', '').strip()
                if not placings:
                    placings = '0'
                class_summary['Placings'] = placings

                # Validate Entries field - it should be numeric
                entries = class_summary.get('Entries', '').strip()
                entries_is_numeric = entries.isdigit() if entries else False

                # Skip rows that don't have valid class information
                has_class = bool(class_summary.get('Class', '').strip())
                has_class_name = bool(class_summary.get('Class Name', '').strip())

                if not has_class and not has_class_name:
                    print(f"    Skipping non-data row (no class info)")
                    continue

                # Handle entries - allow blank or 0 entries
                entries_int = 0
                if entries and entries_is_numeric:
                    entries_int = int(entries)
                elif not entries or entries.strip() == '':
                    # Blank entries - set to 0
                    entries = '0'
                    entries_int = 0
                    class_summary['Entries'] = '0'  # Update class_summary dictionary
                else:
                    # Non-numeric entries - skip this row (likely a header/group row)
                    print(f"    Skipping row with non-numeric Entries: '{entries}'")
                    continue

                print(f"    Class: {class_summary.get('Class', 'N/A')}, Class Name: {class_summary.get('Class Name', 'N/A')[:30]}, Entries: {entries}, Placings: {placings}")

                # Save ShowClass to database (save all classes, even with 0 entries)
                show_class_id = get_or_create_showclass(conn, show_list_id, class_summary)
                if not show_class_id:
                    print(f"      [WARNING] Could not create/get ShowClass")
                    continue
                
                # Store for second pass (only if has placings > 0)
                # If placings = 0, assume there are no results to acquire (but class is saved to DB)
                placings_int = int(placings) if placings else 0
                if placings_int > 0:
                    class_data_list.append((row_idx, show_class_id, entries))
                else:
                    print(f"      Class saved to database (Placings = 0, will not expand for results)")
                    
            except Exception as e:
                print(f"  [WARNING] Error extracting class row {row_idx}: {e}")
                continue
                    
        print(f"  [OK] PASS 1 complete: {len(class_data_list)} classes with entries to process")

        # PASS 2: Expand each class row and capture entry details
        print(f"\n  PASS 2: Extracting entry details...")
        for pass2_idx, (row_idx, show_class_id, entries) in enumerate(class_data_list, 1):
            try:
                print(f"  Processing entry details {pass2_idx}/{len(class_data_list)} (row {row_idx})...")
                
                # Get class details (Entries and Placings) for validation
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT Entries, Placings 
                        FROM sResults.ShowClass 
                        WHERE ID = ?
                    """, show_class_id)
                    class_row_data = cursor.fetchone()
                    max_entries = class_row_data[0] if class_row_data and class_row_data[0] is not None else None
                    max_placings = class_row_data[1] if class_row_data and class_row_data[1] is not None else None
                    cursor.close()
                except:
                    max_entries = None
                    max_placings = None
                
                # Track unique entries to prevent duplicates
                seen_entries = set()
                saved_count = 0
                
                # Re-find the grid and row
                grid = driver.find_element(By.CSS_SELECTOR, 
                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                if not rows:
                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                    rows = []
                    for r in all_rows:
                        row_id = r.get_attribute('id') or ''
                        row_class = r.get_attribute('class') or ''
                        if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                            rows.append(r)
                
                if row_idx > len(rows):
                    print(f"    [WARNING] Row {row_idx} no longer available")
                    continue
                
                class_row = rows[row_idx - 1]
                
                # Expand and extract entry details
                if entries:
                    try:
                        # Expand the row
                        print(f"      Attempting to expand row {row_idx}...")
                        row_expanded = expand_row(driver, class_row)
                        if row_expanded:
                            time.sleep(2)  # Wait longer for detail rows to load
                            
                            # Re-find the row after expansion (may have changed)
                            try:
                                grid = driver.find_element(By.CSS_SELECTOR,
                                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                rows = []
                                for r in all_rows:
                                    row_id = r.get_attribute('id') or ''
                                    row_class = r.get_attribute('class') or ''
                                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                        rows.append(r)
                                
                                if row_idx <= len(rows):
                                    class_row = rows[row_idx - 1]
                            except:
                                pass
                            
                            # Find detail rows (typically nested table or additional rows after expansion)
                            # Look for detail rows that appear after expansion
                            # DevExpress often uses a pattern like: DataRow -> DetailRow
                            detail_rows = []
                            
                            # Try multiple strategies to find detail rows
                            # Strategy 1: Look for grPlacing grids (nested result grids) following the class row
                            try:
                                class_row_id = class_row.get_attribute('id')
                                if class_row_id:
                                    # Get the grid table
                                    grid = driver.find_element(By.CSS_SELECTOR,
                                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                    all_trs = grid.find_elements(By.TAG_NAME, "tr")
                                    
                                    # Find the class row index
                                    class_row_idx = -1
                                    for i, tr in enumerate(all_trs):
                                        if tr.get_attribute('id') == class_row_id:
                                            class_row_idx = i
                                            break
                                    
                                    if class_row_idx >= 0:
                                        # Look for the next tr(s) that contain grPlacing grids
                                        for i in range(class_row_idx + 1, len(all_trs)):
                                            next_tr = all_trs[i]
                                            next_tr_id = next_tr.get_attribute('id') or ''
                                            next_tr_class = next_tr.get_attribute('class') or ''
                                            
                                            # If this is another class row (has DataRow but not in detail container), stop
                                            if 'DataRow' in next_tr_id and 'dxdt' not in next_tr_id and 'dxgvDetailRow' not in next_tr_class:
                                                # Verify it's actually a class row by checking cell structure
                                                cells = next_tr.find_elements(By.TAG_NAME, "td")
                                                if len(cells) >= 2:
                                                    # Class rows typically have a class number in early cells
                                                    break
                                            
                                            # Look for grPlacing grids (nested result grids) in this row
                                            placing_grids = next_tr.find_elements(By.CSS_SELECTOR, "table[id*='grPlacing']")
                                            for placing_grid in placing_grids:
                                                # Store reference to the grid for column mapping
                                                placing_grid_table = placing_grid
                                                # Find data rows in the placing grid
                                                placing_rows = placing_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                                                for pr in placing_rows:
                                                    pr_id = pr.get_attribute('id') or ''
                                                    pr_cells = pr.find_elements(By.TAG_NAME, "td")
                                                    # Result rows have many columns (Place, Entry, Horse, Rider, Owner, Trainer, etc.)
                                                    if len(pr_cells) >= 10 and 'HeaderRow' not in pr_id and 'FilterRow' not in pr_id:
                                                        # Store tuple of (row, grid_table) for column mapping
                                                        detail_rows.append((pr, placing_grid_table))
                                        
                                        if detail_rows:
                                            print(f"      Strategy 1 found {len(detail_rows)} detail rows in grPlacing grids")
                            except Exception as e:
                                print(f"      Strategy 1 error: {e}")
                            
                            # Strategy 2: Look for nested grid (grPlacing) inside detail container following the class row
                            if not detail_rows:
                                try:
                                    # Re-find grid and all rows
                                    grid = driver.find_element(By.CSS_SELECTOR,
                                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                    
                                    # Find current row index
                                    current_idx = -1
                                    class_row_id = class_row.get_attribute('id') or ''
                                    for i, r in enumerate(all_rows):
                                        if r.get_attribute('id') == class_row_id:
                                            current_idx = i
                                            break
                                    
                                    if current_idx >= 0:
                                        # Look for the detail container row that follows this class row
                                        # Detail containers typically have IDs like dxdt1, dxdt2, etc.
                                        for i in range(current_idx + 1, len(all_rows)):
                                            next_row = all_rows[i]
                                            next_row_id = next_row.get_attribute('id') or ''
                                            next_row_class = next_row.get_attribute('class') or ''
                                            
                                            # If this is another class row, stop
                                            if 'DataRow' in next_row_id and 'dxdt' not in next_row_id and 'Detail' not in next_row_id.lower() and 'dxgvDetailRow' not in next_row_class:
                                                # Check if it's actually a class row by looking for class number in first cells
                                                cells = next_row.find_elements(By.TAG_NAME, "td")
                                                if len(cells) >= 2:
                                                    # Skip detail button cell
                                                    cell_text = cells[1].text.strip() if len(cells) > 1 else ''
                                                    # If it looks like a class number (numeric), it's a new class row
                                                    if cell_text and (cell_text.isdigit() or cell_text == ''):
                                                        break
                                            
                                            # Look for nested grids (grPlacing) inside this row
                                            nested_grids = next_row.find_elements(By.CSS_SELECTOR, "table[id*='grPlacing']")
                                            for nested_grid in nested_grids:
                                                # Store reference to the grid for column mapping
                                                placing_grid_table = nested_grid
                                                # Find data rows in the nested grid
                                                nested_rows = nested_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                                                for nr in nested_rows:
                                                    nr_id = nr.get_attribute('id') or ''
                                                    nr_class = nr.get_attribute('class') or ''
                                                    cells = nr.find_elements(By.TAG_NAME, "td")
                                                    # Result rows have many columns (Place, Entry, Horse, Rider, etc.)
                                                    if len(cells) >= 10 and 'HeaderRow' not in nr_id and 'FilterRow' not in nr_id:
                                                        # Store tuple of (row, grid_table) for column mapping
                                                        detail_rows.append((nr, placing_grid_table))
                                        
                                        print(f"      Strategy 2 found {len(detail_rows)} detail rows (checked {len(all_rows)} total rows, started at index {current_idx})")
                                except Exception as e:
                                    print(f"      Strategy 2 error: {e}")
                            
                            # Strategy 3: Look for nested table within the row
                            if not detail_rows:
                                try:
                                    nested_tables = class_row.find_elements(By.TAG_NAME, "table")
                                    print(f"      Strategy 3: Found {len(nested_tables)} nested tables")
                                    for nested_table in nested_tables:
                                        nested_rows = nested_table.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow, tr")
                                        # Filter out header rows
                                        filtered_rows = []
                                        for nr in nested_rows:
                                            nr_class = nr.get_attribute('class') or ''
                                            nr_id = nr.get_attribute('id') or ''
                                            if 'HeaderRow' not in nr_id and 'FilterRow' not in nr_id:
                                                cells = nr.find_elements(By.TAG_NAME, "td")
                                                if len(cells) >= 3:  # Has enough cells to be a data row
                                                    filtered_rows.append(nr)
                                        if filtered_rows:
                                            detail_rows = filtered_rows
                                            print(f"      Strategy 3 found {len(detail_rows)} detail rows in nested table")
                                            break
                                except Exception as e:
                                    print(f"      Strategy 3 error: {e}")
                            
                            # Strategy 4: Look for detail rows by checking following siblings more broadly
                            if not detail_rows:
                                try:
                                    grid = driver.find_element(By.CSS_SELECTOR,
                                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                    class_row_id = class_row.get_attribute('id') or ''
                                    current_idx = -1
                                    for i, r in enumerate(all_rows):
                                        if r.get_attribute('id') == class_row_id:
                                            current_idx = i
                                            break
                                    
                                    if current_idx >= 0:
                                        # Look for the next 10 rows to find detail rows
                                        for i in range(current_idx + 1, min(current_idx + 11, len(all_rows))):
                                            next_row = all_rows[i]
                                            cells = next_row.find_elements(By.TAG_NAME, "td")
                                            next_row_id = next_row.get_attribute('id') or ''
                                            next_row_class = next_row.get_attribute('class') or ''
                                            
                                            # If this row has many cells (like a data row) and isn't a header
                                            if len(cells) >= 10 and 'HeaderRow' not in next_row_id and 'FilterRow' not in next_row_id:
                                                # Check if this could be a detail row by checking if it has Place/Entry/Horse columns
                                                row_text = next_row.text.lower()
                                                # Detail rows typically don't have class numbers but have placement info
                                                if any(keyword in row_text for keyword in ['place', 'entry', 'horse', 'rider']):
                                                    detail_rows.append(next_row)
                                            # Stop if we hit another class row
                                            elif 'DataRow' in next_row_id and 'Detail' not in next_row_id and current_idx != i:
                                                break
                                        
                                        print(f"      Strategy 4 found {len(detail_rows)} detail rows")
                                except Exception as e:
                                    print(f"      Strategy 4 error: {e}")
                            
                            print(f"      Total found: {len(detail_rows)} entry detail rows")
                            
                            if detail_rows:
                                # Get column mapping for entry details from the grid table
                                # detail_rows now contains tuples of (row_element, grid_table) from Strategy 1 and 2
                                # Strategy 3 and 4 might still have plain row elements
                                grid_table = None
                                if isinstance(detail_rows[0], tuple):
                                    grid_table = detail_rows[0][1]
                                else:
                                    # Fallback: try to find the grid table from the first row
                                    try:
                                        first_row = detail_rows[0] if not isinstance(detail_rows[0], tuple) else detail_rows[0][0]
                                        grid_table = first_row.find_element(By.XPATH, "./ancestor::table[contains(@id, 'grPlacing')][1]")
                                    except:
                                        try:
                                            first_row = detail_rows[0] if not isinstance(detail_rows[0], tuple) else detail_rows[0][0]
                                            grid_table = first_row.find_element(By.XPATH, "./ancestor::table[1]")
                                        except:
                                            print(f"      [WARNING] Could not find grid table for column mapping")
                                
                                if grid_table:
                                    entry_column_map = get_column_indices_for_entry_grid(grid_table)
                                    print(f"      Entry column mapping: {entry_column_map}")
                                else:
                                    print(f"      [WARNING] Cannot extract entry details without grid table")
                                    entry_column_map = {}
                                
                                # Process each entry detail row
                                for detail_row_item in detail_rows:
                                    # Extract row element from tuple if it's a tuple
                                    if isinstance(detail_row_item, tuple):
                                        detail_row = detail_row_item[0]
                                    else:
                                        detail_row = detail_row_item
                                    
                                    if entry_column_map:
                                        entry_details = extract_entry_details_from_row(detail_row, entry_column_map)
                                        if entry_details:
                                            if save_show_result_to_database(conn, show_class_id, entry_details):
                                                results_count += 1
                                                place_val = entry_details.get('Place', '').strip()
                                                horse_val = entry_details.get('Horse', '').strip()
                                                print(f"        Saved entry: Place {place_val if place_val else 'N/A'}, Horse: {horse_val[:30] if horse_val else 'N/A'}")
                                    else:
                                        print(f"        [WARNING] Skipping row (no column mapping)")
                            else:
                                print(f"      [WARNING] No entry detail rows found after expansion")
                            
                            # Collapse row after capturing data
                            try:
                                # Re-find the row to avoid stale element
                                grid = driver.find_element(By.CSS_SELECTOR, 
                                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                if not rows:
                                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                    rows = []
                                    for r in all_rows:
                                        row_id = r.get_attribute('id') or ''
                                        row_class = r.get_attribute('class') or ''
                                        if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                            rows.append(r)
                                
                                if row_idx <= len(rows):
                                    row_to_collapse = rows[row_idx - 1]
                                    collapse_row(driver, row_to_collapse)
                            except Exception as e:
                                print(f"      [WARNING] Could not collapse row: {e}")
                    except Exception as e:
                        print(f"    [WARNING] Error expanding/extracting entry details: {e}")
                        import traceback
                        traceback.print_exc()
                        continue

            except Exception as e:
                print(f"  [WARNING] Error processing entry details for row {row_idx}: {e}")
                continue
        
        print(f"  [OK] Completed scraping for ShowGUID {show_guid}: {results_count} results saved")
        return results_count
        
    except Exception as e:
        print(f"  [ERROR] Error scraping class results for ShowGUID {show_guid}: {e}")
        import traceback
        traceback.print_exc()
        return results_count

def main(skip_processed=True):
    """Main function to scrape class results
    
    Args:
        skip_processed: If True, skip shows that already have ShowClass or ShowResults data (default: True)
    """
    print("\n" + "=" * 60)
    print("HorseShowsOnline - Class Results Scraper")
    print("=" * 60 + "\n")
    
    if skip_processed:
        print("[INFO] Will skip shows with existing ShowClass or ShowResults data\n")
    else:
        print("[INFO] Will process all shows, including those with existing data\n")
    
    driver = None
    conn = None
    
    try:
        # Setup driver
        print("Initializing browser (headless mode)...")
        driver = setup_driver(headless=True)
        print("  [OK] Browser initialized\n")
        
        # Connect to database
        print("Connecting to database...")
        conn = get_db_connection()
        print("[OK] Connected to database")
        
        # Create tables
        print("\nEnsuring database tables exist...")
        create_competitors_table_if_not_exists(conn)
        create_horse_table_if_not_exists(conn)
        create_showclass_table_if_not_exists(conn)
        create_showresults_table_if_not_exists(conn)
        print("[OK] Database tables verified/created\n")
        
        # Get ShowGUIDs, Years, and ShowNames from database
        print("Fetching ShowGUIDs, Years, and ShowNames from ShowList table...")
        show_data_list = get_show_data_from_database(conn, skip_processed=skip_processed)
        print(f"[OK] Found {len(show_data_list)} shows\n")
        
        if not show_data_list:
            print("[WARNING] No ShowGUIDs found in database. Please run scrape_shows_by_year.py first.")
            return
        
        # Scrape results for each show
        total_results = 0
        for idx, (show_list_id, show_guid, year, show_name) in enumerate(show_data_list, 1):
            print(f"\nProcessing show {idx}/{len(show_data_list)}...")
            results_count = scrape_class_results_for_show(driver, show_list_id, show_guid, year, show_name, conn)
            total_results += results_count
            
            # Small delay between shows
            time.sleep(2)
        
        print(f"\n{'='*60}")
        print(f"Scraping complete! Total results collected: {total_results}")
        print(f"{'='*60}\n")
        
    except KeyboardInterrupt:
        print("\n\n[WARNING] Scraping interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            try:
                conn.close()
                print("[OK] Database connection closed")
            except:
                pass
        if driver:
            print("\nClosing browser...")
            driver.quit()

if __name__ == '__main__':
    import sys
    
    # Check for command-line argument to process all shows (including those with existing data)
    skip_processed = True
    if len(sys.argv) > 1:
        if sys.argv[1].lower() in ['--process-all', '-a', '--all']:
            skip_processed = False
            print("[INFO] Command-line argument detected: Will process all shows (including those with existing data)")
        elif sys.argv[1].lower() in ['--help', '-h']:
            print("Usage: python scrape_class_results.py [--process-all]")
            print("  --process-all, -a, --all: Process all shows, including those with existing ShowClass or ShowResults data")
            print("  Default: Skip shows with existing data")
            sys.exit(0)
    
    main(skip_processed=skip_processed)

