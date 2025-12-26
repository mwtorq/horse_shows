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
from datetime import datetime

def print_with_timestamp(message, end='\n'):
    """Print message with timestamp prefix
    
    Handles leading newlines by printing them first, then the timestamp and message.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # Handle leading newlines - print them first, then timestamp and message
    if message.startswith('\n'):
        # Count leading newlines
        leading_newlines = 0
        for char in message:
            if char == '\n':
                leading_newlines += 1
            else:
                break
        # Print leading newlines
        print('\n' * leading_newlines, end='')
        # Print timestamp and remaining message (without leading newlines)
        remaining_message = message[leading_newlines:]
        print(f"[{timestamp}] {remaining_message}", end=end)
    else:
        print(f"[{timestamp}] {message}", end=end)
def reconnect_browser_and_navigate(driver, show_guid, year, show_name, current_url_hint=None, sleep_short=2, sleep_medium=3, sleep_long=5):
    """Reconnect browser and navigate back to ClassResults page
    
    Args:
        driver: Current WebDriver instance (will be quit and replaced)
        show_guid: ShowGUID to navigate to
        year: Year for navigation context
        show_name: Show name for navigation context
        current_url_hint: Optional hint about what URL we were on
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
        sleep_long: Long sleep duration in seconds (default: 5)
    
    Returns:
        New WebDriver instance, or None if reconnection failed
    """
    try:
        print_with_timestamp(f"      [RECONNECT] Disconnecting browser due to stale element errors...")
        
        # Close current browser
        try:
            driver.quit()
        except:
            pass
        
        # Wait a moment
        time.sleep(sleep_short)
        
        # Create new browser instance
        print_with_timestamp(f"      [RECONNECT] Creating new browser connection...")
        new_driver = setup_driver(headless=True)
        
        # Navigate back to ClassResults page using the same flow as find_and_click_show_row
        print_with_timestamp(f"      [RECONNECT] Navigating to ClassResults page...")
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        new_driver.get(show_selector_url)
        time.sleep(sleep_medium)
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(new_driver):
            print_with_timestamp(f"      [RECONNECT] Warning: Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            new_driver.get(class_results_url)
            time.sleep(sleep_long)
        else:
            # Select the year
            if not select_year(new_driver, year):
                print_with_timestamp(f"      [RECONNECT] Warning: Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                new_driver.get(class_results_url)
                time.sleep(sleep_long)
            else:
                # Find and click the show row to navigate to ClassResults (same as normal flow)
                if not find_and_click_show_row(new_driver, show_guid, year, show_name):
                    print_with_timestamp(f"      [RECONNECT] Warning: Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    new_driver.get(class_results_url)
                    time.sleep(sleep_long)
        
        # Wait for grid to load with longer timeout
        try:
            WebDriverWait(new_driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']"))
            )
            print_with_timestamp(f"      [RECONNECT] Grid table found")
        except TimeoutException:
            print_with_timestamp(f"      [RECONNECT] Warning: Grid table not found after 15 seconds, but continuing...")
            # Try one more time with a direct navigation
            try:
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                new_driver.get(class_results_url)
                time.sleep(sleep_long)
                WebDriverWait(new_driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']"))
                )
                print_with_timestamp(f"      [RECONNECT] Grid table found after direct navigation")
            except:
                print_with_timestamp(f"      [RECONNECT] Warning: Grid table still not found after direct navigation")
        
        time.sleep(sleep_short)  # Additional wait for JavaScript
        
        print_with_timestamp(f"      [RECONNECT] Browser reconnected successfully")
        return new_driver
        
    except Exception as e:
        print_with_timestamp(f"      [RECONNECT] Error reconnecting browser: {e}")
        import traceback
        traceback.print_exc()
        return None

def retry_on_stale_element(operation_func, max_retries=3, delay=0.5, reconnect_func=None, *args, **kwargs):
    """Helper function to retry an operation on StaleElementReferenceException
    
    Args:
        operation_func: Function to execute that may throw StaleElementReferenceException
        max_retries: Maximum number of retry attempts (default: 3)
        delay: Delay between retries in seconds (default: 0.5)
        reconnect_func: Optional function to reconnect browser. If provided and stale element persists,
                       will call this function before final retry attempts. Function should return new driver or None.
        *args, **kwargs: Arguments to pass to operation_func
    
    Returns:
        Result of operation_func, or None if all retries failed
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            return operation_func(*args, **kwargs)
        except StaleElementReferenceException as e:
            last_exception = e
            if attempt < max_retries - 1:
                # If we're more than halfway through retries and have reconnect_func, try reconnecting
                if reconnect_func and attempt >= (max_retries // 2) and attempt < max_retries - 1:
                    print_with_timestamp(f"      [RETRY] Stale element on attempt {attempt + 1}/{max_retries}, attempting browser reconnection...")
                    new_driver = reconnect_func()
                    if new_driver:
                        # Update driver in kwargs if present
                        if 'driver' in kwargs:
                            kwargs['driver'] = new_driver
                        # Also check if operation_func's closure has driver
                        time.sleep(delay * 2)  # Longer delay after reconnect
                        continue
                else:
                    time.sleep(delay)
                    continue
            else:
                # Last attempt failed, return None or re-raise based on context
                return None
        except Exception as e:
            # Don't retry on other exceptions, re-raise immediately
            raise
    
    return None

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
        print_with_timestamp(f"Error setting up driver: {e}")
        if headless:
            print_with_timestamp("Retrying without headless mode...")
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
            print_with_timestamp(f"[OK] Connected to HorseShows database using driver: {driver}")
            return conn
        except Exception as e:
            if driver == drivers[-1]:  # Last driver
                print_with_timestamp(f"[ERROR] Database connection failed with all drivers: {e}")
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
            # Note: DBCC CHECKIDENT needs to be executed without parameterization
            full_table_name = f"{schema_name}.{table_name}"
            cursor.execute(f"DBCC CHECKIDENT ('{full_table_name}', RESEED, 0) WITH NO_INFOMSGS")
            conn.commit()
            print_with_timestamp(f"  [OK] Reseeded identity column for {full_table_name} to 0 (table is empty)")
        cursor.close()
    except Exception as e:
        # Ignore errors - table might not exist yet or might not have identity column
        # DBCC CHECKIDENT might not work through pyodbc in all cases
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
            print_with_timestamp("Creating sResults.Competitors table...")
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
            print_with_timestamp("[OK] Competitors table created successfully")
        else:
            print_with_timestamp("[OK] Competitors table already exists")
            # Reseed identity if table is empty
            reseed_identity_if_empty(conn, 'sResults', 'Competitors', 'ID')
        
        cursor.close()
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error creating Competitors table: {e}")
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
            print_with_timestamp("Creating sResults.ShowClass table...")
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
                    NonPlacingComplete BIT DEFAULT 0,
                    CreatedDate DATETIME DEFAULT GETDATE(),
                    UpdatedDate DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (ShowListID) REFERENCES sResults.ShowList(ID)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_ShowClass_ShowListID ON sResults.ShowClass(ShowListID)")
            cursor.execute("CREATE INDEX IX_ShowClass_Class ON sResults.ShowClass(Class)")
            
            conn.commit()
            print_with_timestamp("[OK] ShowClass table created successfully")
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
                print_with_timestamp("[WARNING] ShowClass table has old structure (ShowGUID). Dropping and recreating...")
                print_with_timestamp("[NOTE] Existing ShowClass data will be lost and must be re-scraped.")
                
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
                            print_with_timestamp(f"  Dropping foreign key constraint: {fk_name} from {table_name}")
                            cursor.execute(f"ALTER TABLE sResults.{table_name} DROP CONSTRAINT [{fk_name}]")
                            conn.commit()
                        except Exception as e:
                            print_with_timestamp(f"    [WARNING] Could not drop FK constraint {fk_name}: {e}")
                except Exception as e:
                    print_with_timestamp(f"  [WARNING] Error finding FK constraints: {e}")
                
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
                print_with_timestamp("Creating sResults.ShowClass table with new structure...")
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
                        NonPlacingComplete BIT DEFAULT 0,
                        CreatedDate DATETIME DEFAULT GETDATE(),
                        UpdatedDate DATETIME DEFAULT GETDATE(),
                        FOREIGN KEY (ShowListID) REFERENCES sResults.ShowList(ID)
                    )
                """)
                
                # Create indexes
                cursor.execute("CREATE INDEX IX_ShowClass_ShowListID ON sResults.ShowClass(ShowListID)")
                cursor.execute("CREATE INDEX IX_ShowClass_Class ON sResults.ShowClass(Class)")
                
                conn.commit()
                print_with_timestamp("[OK] ShowClass table recreated with new structure")
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
                    print_with_timestamp("[OK] ShowClass table already exists with correct structure")
                    # Check if NonPlacingComplete column exists, add it if not
                    cursor.execute("""
                        SELECT COUNT(*) 
                        FROM INFORMATION_SCHEMA.COLUMNS 
                        WHERE TABLE_SCHEMA = 'sResults' 
                        AND TABLE_NAME = 'ShowClass' 
                        AND COLUMN_NAME = 'NonPlacingComplete'
                    """)
                    has_nonplacing_complete = cursor.fetchone()[0] > 0
                    
                    if not has_nonplacing_complete:
                        print_with_timestamp("Adding NonPlacingComplete column to ShowClass table...")
                        try:
                            cursor.execute("""
                                ALTER TABLE sResults.ShowClass 
                                ADD NonPlacingComplete BIT DEFAULT 0
                            """)
                            conn.commit()
                            print_with_timestamp("[OK] NonPlacingComplete column added successfully")
                        except Exception as e:
                            print_with_timestamp(f"[WARNING] Error adding NonPlacingComplete column: {e}")
                    # Reseed identity if table is empty
                    reseed_identity_if_empty(conn, 'sResults', 'ShowClass', 'ID')
                else:
                    print_with_timestamp("[WARNING] ShowClass table exists but structure is unknown. Please verify manually.")
        
        cursor.close()
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error creating/migrating ShowClass table: {e}")
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
            print_with_timestamp("Creating sResults.Horse table...")
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
            print_with_timestamp("[OK] Horse table created successfully")
        else:
            print_with_timestamp("[OK] Horse table already exists")
            # Reseed identity if table is empty
            reseed_identity_if_empty(conn, 'sResults', 'Horse', 'ID')
        
        cursor.close()
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error creating Horse table: {e}")
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
            print_with_timestamp("Creating sResults.ShowResults table...")
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
            print_with_timestamp("[OK] ShowResults table created successfully")
        else:
            print_with_timestamp("[OK] ShowResults table already exists")
            # Reseed identity if table is empty
            reseed_identity_if_empty(conn, 'sResults', 'ShowResults', 'ID')
        
        cursor.close()
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error creating ShowResults table: {e}")
        raise

def create_importlog_table_if_not_exists(conn):
    """Create the ImportLog table if it doesn't exist"""
    try:
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_SCHEMA = 'sResults' AND TABLE_NAME = 'ImportLog'
        """)
        table_exists = cursor.fetchone()[0] > 0
        
        if not table_exists:
            print_with_timestamp("Creating sResults.ImportLog table...")
            cursor.execute("""
                CREATE TABLE sResults.ImportLog (
                    ID INT IDENTITY(1,1) PRIMARY KEY,
                    LogTimestamp DATETIME DEFAULT GETDATE(),
                    OriginatingScript NVARCHAR(200) NOT NULL,
                    TargetTable NVARCHAR(200),
                    Action NVARCHAR(100) NOT NULL,
                    [RowCount] INT,
                    ErrorDetail NVARCHAR(MAX),
                    AdditionalInfo NVARCHAR(MAX)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IX_ImportLog_Timestamp ON sResults.ImportLog(LogTimestamp)")
            cursor.execute("CREATE INDEX IX_ImportLog_Script ON sResults.ImportLog(OriginatingScript)")
            cursor.execute("CREATE INDEX IX_ImportLog_TargetTable ON sResults.ImportLog(TargetTable)")
            
            conn.commit()
            print_with_timestamp("[OK] ImportLog table created successfully")
        else:
            print_with_timestamp("[OK] ImportLog table already exists")
        
        cursor.close()
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error creating ImportLog table: {e}")
        raise

def log_import_activity(conn, script_name, target_table=None, action='', row_count=None, error_detail=None, additional_info=None):
    """Log import activity to ImportLog table
    
    Args:
        conn: Database connection
        script_name: Name of the originating script (e.g., 'scrape_class_results.py')
        target_table: Target table name (e.g., 'ShowResults', 'ShowClass')
        action: Action description (e.g., 'INSERT', 'UPDATE', 'START', 'COMPLETE', 'ERROR')
        row_count: Number of rows affected
        error_detail: Error message if any
        additional_info: Additional information (JSON string or text)
    """
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sResults.ImportLog 
            (OriginatingScript, TargetTable, Action, [RowCount], ErrorDetail, AdditionalInfo)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            script_name,
            target_table,
            action,
            row_count,
            error_detail,
            additional_info
        )
        conn.commit()
        cursor.close()
    except Exception as e:
        # Don't raise - logging failures shouldn't break the main process
        print_with_timestamp(f"[WARNING] Failed to log import activity: {e}")

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
        print_with_timestamp(f"      [WARNING] Error getting/creating competitor ({role_type}): {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()

def activate_shows_by_year_tab(driver, sleep_medium=3, sleep_short=0.5):
    """Activate the 'Shows By Year' tab
    
    Args:
        driver: WebDriver instance
        sleep_medium: Medium sleep duration in seconds (default: 3)
        sleep_short: Short sleep duration in seconds (default: 0.5)
    """
    print_with_timestamp("Activating 'Shows By Year' tab...")
    
    try:
        time.sleep(sleep_medium)
        
        # Try multiple methods to find the tab
        shows_by_year_tab = None
        
        # Method 1: Find all tabs and search by text
        try:
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            print_with_timestamp(f"  Found {len(tabs)} tabs")
            for tab in tabs:
                tab_text = tab.text.strip()
                print_with_timestamp(f"    Tab text: '{tab_text}'")
                if 'Shows By Year' in tab_text or 'By Year' in tab_text:
                    shows_by_year_tab = tab
                    print_with_timestamp(f"  [OK] Found 'Shows By Year' tab by text")
                    break
        except Exception as e:
            print_with_timestamp(f"  [DEBUG] Method 1 error: {e}")
        
        # Method 2: Try XPath with span
        if not shows_by_year_tab:
            try:
                shows_by_year_tab = driver.find_element(By.XPATH, 
                    "//li[contains(@class, 'dxtc-tab')]//span[contains(text(), 'Shows By Year')]/ancestor::li[1]")
                print_with_timestamp(f"  [OK] Found 'Shows By Year' tab by XPath (span)")
            except:
                pass
        
        # Method 3: Try XPath with any text node
        if not shows_by_year_tab:
            try:
                shows_by_year_tab = driver.find_element(By.XPATH, 
                    "//li[contains(@class, 'dxtc-tab')][contains(., 'Shows By Year')]")
                print_with_timestamp(f"  [OK] Found 'Shows By Year' tab by XPath (contains)")
            except:
                pass
        
        # Method 4: Try finding by link text
        if not shows_by_year_tab:
            try:
                link = driver.find_element(By.PARTIAL_LINK_TEXT, "Shows By Year")
                shows_by_year_tab = link.find_element(By.XPATH, "./ancestor::li[1]")
                print_with_timestamp(f"  [OK] Found 'Shows By Year' tab by link text")
            except:
                pass
        
        if not shows_by_year_tab:
            print_with_timestamp("  [ERROR] Could not find 'Shows By Year' tab using any method")
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
                    print_with_timestamp("  [OK] Tab is already active")
                    return True
            else:
                # Fallback: find by text again
                for tab in tabs:
                    if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                        shows_by_year_tab_refresh = tab
                        classes = tab.get_attribute('class') or ''
                        if 'dxtc-activeTab' in classes:
                            print_with_timestamp("  [OK] Tab is already active")
                            return True
                        break
        except Exception as e:
            print_with_timestamp(f"  [DEBUG] Error checking if tab is active: {e}")
        
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
                print_with_timestamp("  [ERROR] Could not re-find tab for clicking")
                return False
            
            link = target_tab.find_element(By.CSS_SELECTOR, "a.dxtc-link")
            driver.execute_script("arguments[0].scrollIntoView(true);", link)
            time.sleep(sleep_short)
            driver.execute_script("arguments[0].click();", link)
            time.sleep(sleep_medium)
            
            # Verify it's now active (re-find again)
            tabs = driver.find_elements(By.CSS_SELECTOR, "li.dxtc-tab")
            for tab in tabs:
                if 'Shows By Year' in tab.text or 'By Year' in tab.text:
                    classes = tab.get_attribute('class') or ''
                    if 'dxtc-activeTab' in classes:
                        print_with_timestamp("  [OK] Tab activated successfully")
                        return True
                    else:
                        print_with_timestamp("  [WARNING] Tab clicked but may not be active")
                        return True  # Still return True, might work anyway
            
            return True  # Assume it worked if we can't verify
        except Exception as e:
            print_with_timestamp(f"  [ERROR] Error clicking tab: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error activating tab: {e}")
        import traceback
        traceback.print_exc()
        return False

def activate_class_results_tab(driver, sleep_short=2, sleep_medium=3):
    """Activate the 'Class Results' tab on ShowDetails page
    
    Args:
        driver: WebDriver instance
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    """
    print_with_timestamp("  Activating 'Class Results' tab...")
    
    try:
        time.sleep(sleep_short)
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
                        time.sleep(sleep_medium)
                        return True
                except:
                    pass
        
        if class_results_tab:
            classes = class_results_tab.get_attribute('class') or ''
            if 'dxtc-activeTab' not in classes:
                link = class_results_tab.find_element(By.CSS_SELECTOR, "a.dxtc-link")
                driver.execute_script("arguments[0].scrollIntoView(true);", link)
                time.sleep(sleep_short / 4)  # Very short wait
                driver.execute_script("arguments[0].click();", link)
                time.sleep(sleep_medium)
            return True
        
        return False
    except Exception as e:
        print_with_timestamp(f"  [WARNING] Error activating Class Results tab: {e}")
        return False

def select_year(driver, year, sleep_short=2, sleep_medium=3):
    """Select a specific year in the year picker
    
    Args:
        driver: WebDriver instance
        year: Year to select
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    """
    print_with_timestamp(f"\nSelecting year {year}...")
    
    try:
        time.sleep(sleep_short)
        
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
            print_with_timestamp(f"  [ERROR] Could not find year picker for year {year}")
            return False
        
        element_id = year_element.get_attribute('id') or ''
        year_value = str(year)
        
        print_with_timestamp(f"  Setting year picker to {year_value}...")
        
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
        time.sleep(sleep_medium)
        
        # Verify the value was set
        current_value = driver.execute_script("return arguments[0].value;", year_element)
        if str(year) in str(current_value):
            print_with_timestamp(f"  [OK] Year {year} selected")
            return True
        else:
            print_with_timestamp(f"  [WARNING] Year may not have been set correctly. Current value: {current_value}")
            return True  # Continue anyway
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error selecting year {year}: {e}")
        return False

def get_show_list_id_from_guid(conn, show_guid):
    """Get ShowListID from ShowGUID"""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ID 
            FROM sResults.ShowList 
            WHERE ShowGUID = ?
        """, show_guid)
        result = cursor.fetchone()
        cursor.close()
        if result:
            return result[0]
        return None
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error getting ShowListID from ShowGUID {show_guid}: {e}")
        return None

def get_show_data_from_database(conn, skip_processed=True, start_from_show_guid=None):
    """Get ID, ShowGUID, Year, and ShowName from ShowList table where EndDate < today, ordered by ID
    
    Args:
        conn: Database connection
        skip_processed: If True, skip shows that already have ShowClass or ShowResults data
        start_from_show_guid: Optional ShowGUID to start from (only processes ShowListID >= that ShowGUID's ID)
    """
    try:
        cursor = conn.cursor()
        
        # Get starting ShowListID if ShowGUID provided
        start_from_id = None
        if start_from_show_guid:
            start_from_id = get_show_list_id_from_guid(conn, start_from_show_guid)
            if start_from_id:
                print_with_timestamp(f"[INFO] Starting from ShowGUID {start_from_show_guid} (ShowListID: {start_from_id})")
            else:
                print_with_timestamp(f"[WARNING] ShowGUID {start_from_show_guid} not found, ignoring --start-from parameter")
        
        if skip_processed:
            # Get shows that don't have existing ShowClass or ShowResults data
            if start_from_id:
                cursor.execute("""
                    SELECT sl.ID, sl.ShowGUID, sl.Year, sl.ShowName 
                    FROM sResults.ShowList sl
                    WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                    AND sl.StartDate IS NOT NULL
                    AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
                    AND sl.ID >= ?
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
                """, start_from_id)
            else:
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
            print_with_timestamp("[OK] Filtering out shows with existing ShowClass or ShowResults data")
        else:
            # Get all shows regardless of existing data
            if start_from_id:
                cursor.execute("""
                    SELECT ID, ShowGUID, Year, ShowName 
                    FROM sResults.ShowList 
                    WHERE ShowGUID IS NOT NULL AND ShowGUID != ''
                    AND StartDate IS NOT NULL
                    AND CAST(EndDate AS DATE) < CAST(GETDATE() AS DATE)
                    AND ID >= ?
                    ORDER BY ID
                """, start_from_id)
            else:
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
        print_with_timestamp(f"[OK] Found {len(show_data)} shows with EndDate < today")
        return show_data
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error getting show data from database: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_shows_with_missing_classes(conn, start_from_show_guid=None):
    """Get shows that have ShowClass rows with Placings > 0 that don't have corresponding ShowResults
    
    Args:
        conn: Database connection
        start_from_show_guid: Optional ShowGUID to start from (only processes ShowListID >= that ShowGUID's ID)
    
    Returns: List of tuples (show_list_id, show_guid, year, show_name, list of ShowClass IDs to process)
    """
    try:
        cursor = conn.cursor()
        
        # Get starting ShowListID if ShowGUID provided
        start_from_id = None
        if start_from_show_guid:
            start_from_id = get_show_list_id_from_guid(conn, start_from_show_guid)
            if start_from_id:
                print_with_timestamp(f"[INFO] Starting from ShowGUID {start_from_show_guid} (ShowListID: {start_from_id})")
            else:
                print_with_timestamp(f"[WARNING] ShowGUID {start_from_show_guid} not found, ignoring --start-from parameter")
        
        # Find shows that have ShowClass rows with Placings > 0 that don't have ShowResults
        if start_from_id:
            cursor.execute("""
                SELECT DISTINCT
                    sl.ID,
                    sl.ShowGUID,
                    sl.Year,
                    sl.ShowName
                FROM sResults.ShowList sl
                WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                AND sl.StartDate IS NOT NULL
                AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
                AND sl.ID >= ?
                -- Has ShowClass rows with Placings > 0 that don't have ShowResults
                AND EXISTS (
                    SELECT 1
                    FROM sResults.ShowClass sc
                    WHERE sc.ShowListID = sl.ID
                    AND sc.Placings > 0
                    AND NOT EXISTS (
                        SELECT 1 
                        FROM sResults.ShowResults sr
                        WHERE sr.ShowClassID = sc.ID
                    )
                )
                ORDER BY sl.ID
            """, start_from_id)
        else:
            cursor.execute("""
                SELECT DISTINCT
                    sl.ID,
                    sl.ShowGUID,
                    sl.Year,
                    sl.ShowName
                FROM sResults.ShowList sl
                WHERE sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                AND sl.StartDate IS NOT NULL
                AND CAST(sl.EndDate AS DATE) < CAST(GETDATE() AS DATE)
                -- Has ShowClass rows with Placings > 0 that don't have ShowResults
                AND EXISTS (
                    SELECT 1
                    FROM sResults.ShowClass sc
                    WHERE sc.ShowListID = sl.ID
                    AND sc.Placings > 0
                    AND NOT EXISTS (
                        SELECT 1 
                        FROM sResults.ShowResults sr
                        WHERE sr.ShowClassID = sc.ID
                    )
                )
                ORDER BY sl.ID
            """)
        
        show_data = cursor.fetchall()
        result = []
        
        # For each show, get the specific ShowClass IDs that need processing
        for row in show_data:
            show_list_id = row[0]
            show_guid = row[1]
            year = row[2]
            show_name = row[3]
            
            # Get ShowClass IDs with Placings > 0 that don't have ShowResults
            cursor.execute("""
                SELECT sc.ID
                FROM sResults.ShowClass sc
                WHERE sc.ShowListID = ?
                AND sc.Placings > 0
                AND NOT EXISTS (
                    SELECT 1
                    FROM sResults.ShowResults sr
                    WHERE sr.ShowClassID = sc.ID
                )
                ORDER BY sc.ID
            """, show_list_id)
            
            missing_class_ids = [r[0] for r in cursor.fetchall()]
            
            if missing_class_ids:
                result.append((show_list_id, show_guid, year, show_name, missing_class_ids))
        
        cursor.close()
        print_with_timestamp(f"[OK] Found {len(result)} shows with missing class results")
        total_missing = sum(len(ids) for _, _, _, _, ids in result)
        print_with_timestamp(f"[OK] Total missing classes to process: {total_missing}")
        return result
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error getting shows with missing classes: {e}")
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
            print_with_timestamp(f"  [DEBUG] Header row has {len(header_cells)} cells")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip()
                cell_text_lower = cell_text.lower()
                print_with_timestamp(f"    Header cell {idx}: '{cell_text}'")
                
                # Skip command column (first column is usually expand/collapse buttons)
                if idx == 0 and ('button' in cell_text_lower or cell_text == ''):
                    continue
                
                col_idx = idx
                if 'class' in cell_text_lower and 'name' not in cell_text_lower and 'type' not in cell_text_lower:
                    column_map['Class'] = col_idx
                    print_with_timestamp(f"      -> Mapped to 'Class'")
                elif 'class name' in cell_text_lower or ('name' in cell_text_lower and 'class' in cell_text_lower):
                    column_map['Class Name'] = col_idx
                    print_with_timestamp(f"      -> Mapped to 'Class Name'")
                elif 'class type' in cell_text_lower or ('type' in cell_text_lower and 'class' in cell_text_lower):
                    column_map['Class Type'] = col_idx
                    print_with_timestamp(f"      -> Mapped to 'Class Type'")
                elif 'division' in cell_text_lower:
                    column_map['Division Name'] = col_idx
                    print_with_timestamp(f"      -> Mapped to 'Division Name'")
                elif 'entries' in cell_text_lower:
                    column_map['Entries'] = col_idx
                    print_with_timestamp(f"      -> Mapped to 'Entries'")
                elif 'placings' in cell_text_lower:
                    column_map['Placings'] = col_idx
                    print_with_timestamp(f"      -> Mapped to 'Placings'")
    except Exception as e:
        print_with_timestamp(f"  [WARNING] Error inspecting header: {e}")
        pass
    
    # Default mapping if header inspection failed (based on actual structure from debug output)
    # Cell 0: command column (skip), Cell 1: empty, Cell 2: Class, Cell 3: ClassName, 
    # Cell 4: ClassType, Cell 5: DivisionName, Cell 6: Entries, Cell 7: Placings
    if all(v is None for v in column_map.values()):
        print_with_timestamp(f"  [WARNING] Could not map columns from header, using defaults")
        column_map = {
            'Class': 2,
            'Class Name': 3,
            'Class Type': 4,
            'Division Name': 5,
            'Entries': 6,
            'Placings': 7,
        }
    
    return column_map

def get_column_indices_for_nonplacing_grid(detail_grid):
    """Determine column indices for non-placing entries grid
    
    Non-placing grid columns:
    Entry, Horse, Rider, Cntry (Country), Owner, Trainer, Prize, Start, Score, Percent, USEF, EC
    
    Returns column map (Place and AddBack will be set to defaults: 0 and '$0.00')
    """
    column_map = {
        'Entry': None,
        'Horse': None,
        'Rider': None,
        'Country': None,  # Maps from Cntry column
        'Owner': None,
        'Trainer': None,
        'Prize': None,
        'Start': None,
        'Score': None,
        'Percent': None,
        'USEF': None,
        'EC': None,
        'Place': None,  # Will be set to 0
        'AddBack': None,  # Will be set to '$0.00'
    }
    
    try:
        # Try to find header row
        header_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='HeaderRow'], tr.dxgvHeaderRow")
        
        if header_rows:
            header_cells = header_rows[0].find_elements(By.TAG_NAME, "th, td")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip().lower()
                
                if 'entry' in cell_text:
                    column_map['Entry'] = idx
                elif 'horse' in cell_text:
                    column_map['Horse'] = idx
                elif 'rider' in cell_text:
                    column_map['Rider'] = idx
                elif 'cntry' in cell_text or 'country' in cell_text:
                    column_map['Country'] = idx
                elif 'owner' in cell_text:
                    column_map['Owner'] = idx
                elif 'trainer' in cell_text:
                    column_map['Trainer'] = idx
                elif 'prize' in cell_text:
                    column_map['Prize'] = idx
                elif 'start' in cell_text:
                    column_map['Start'] = idx
                elif 'score' in cell_text:
                    column_map['Score'] = idx
                elif 'percent' in cell_text:
                    column_map['Percent'] = idx
                elif 'usef' in cell_text:
                    column_map['USEF'] = idx
                elif 'ec' in cell_text and 'cntry' not in cell_text:
                    column_map['EC'] = idx
    except Exception as e:
        pass
    
    # If no mappings found, use default positional mapping based on provided structure:
    # Entry=0, Horse=1, Rider=2, Cntry=3, Owner=4, Trainer=5, Prize=6, Start=7, Score=8, Percent=9, USEF=10, EC=11
    if not any(column_map[k] is not None for k in ['Entry', 'Horse', 'Rider', 'Country', 'Owner', 'Trainer']):
        try:
            data_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
            if data_rows:
                sample_cells = data_rows[0].find_elements(By.TAG_NAME, "td")
                cell_count = len(sample_cells)
                
                # Apply default positional mapping for non-placing entries (12 columns)
                if cell_count >= 12:
                    column_map['Entry'] = 0
                    column_map['Horse'] = 1
                    column_map['Rider'] = 2
                    column_map['Country'] = 3  # Cntry maps to Country
                    column_map['Owner'] = 4
                    column_map['Trainer'] = 5
                    column_map['Prize'] = 6
                    column_map['Start'] = 7
                    column_map['Score'] = 8
                    column_map['Percent'] = 9
                    column_map['USEF'] = 10
                    column_map['EC'] = 11
        except:
            pass
    
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
            print_with_timestamp(f"        [DEBUG] Found {len(header_cells)} header cells")
            for idx, cell in enumerate(header_cells):
                cell_text = cell.text.strip().lower()
                col_idx = idx
                if idx < 5:  # Debug first few cells
                    print_with_timestamp(f"          Header cell {idx}: '{cell_text}'")
                
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
            print_with_timestamp(f"        [DEBUG] No header mappings found, using default positional mapping")
            # Try to determine column count from a data row to verify structure
            try:
                data_rows = detail_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                if data_rows:
                    sample_cells = data_rows[0].find_elements(By.TAG_NAME, "td")
                    cell_count = len(sample_cells)
                    print_with_timestamp(f"        [DEBUG] Sample data row has {cell_count} cells")
                    
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
                        print_with_timestamp(f"        [DEBUG] Applied default positional mapping (14 columns)")
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
                        print_with_timestamp(f"        [DEBUG] Applied default positional mapping ({cell_count} columns, partial)")
            except Exception as e:
                print_with_timestamp(f"        [DEBUG] Error determining positional mapping: {e}")
    except Exception as e:
        print_with_timestamp(f"        [DEBUG] Error in get_column_indices_for_entry_grid: {e}")
        import traceback
        traceback.print_exc()
    
    return column_map

def expand_row(driver, row_id, reconnect_func=None, sleep_short=0.3, sleep_very_short=0.2):
    """Expand a row by clicking the expand button/icon using row ID
    
    Args:
        driver: WebDriver instance
        row_id: Row ID string to find the row element
        reconnect_func: Optional function to reconnect browser on stale element
        sleep_short: Short sleep duration in seconds (default: 0.3)
        sleep_very_short: Very short sleep duration in seconds (default: 0.2)
    """
    try:
        if not row_id:
            return False
        
        # Re-find the row element by ID with retry
        def find_row():
            return driver.find_element(By.ID, row_id)
        
        row_element = retry_on_stale_element(find_row, max_retries=3, delay=sleep_short, reconnect_func=reconnect_func)
        if not row_element:
            return False
        
        # DevExpress detail rows: first cell has class dxgvDetailButton_Office2010Blue
        def get_first_cell():
            cell = row_element.find_element(By.TAG_NAME, "td")
            return cell, cell.get_attribute('class') or ''
        
        result = retry_on_stale_element(get_first_cell, max_retries=3, delay=sleep_short)
        if result:
            first_cell, first_cell_class = result
        else:
            # If retry failed, try one more time to re-find row
            row_element = retry_on_stale_element(find_row, max_retries=2, delay=sleep_short)
            if not row_element:
                return False
            result = retry_on_stale_element(get_first_cell, max_retries=2, delay=sleep_short)
            if not result:
                return False
            first_cell, first_cell_class = result
        
        # Check if this is a detail button cell
        if 'dxgvDetailButton' in first_cell_class:
            # Look for the expand/collapse image with retry
            def get_detail_images():
                return first_cell.find_elements(By.TAG_NAME, "img")
            
            detail_images = retry_on_stale_element(get_detail_images, max_retries=3, delay=sleep_short)
            if detail_images:
                for img in detail_images:
                    try:
                        img_class = retry_on_stale_element(lambda: img.get_attribute('class') or '', max_retries=2, delay=sleep_very_short)
                        img_onclick = retry_on_stale_element(lambda: img.get_attribute('onclick') or '', max_retries=2, delay=sleep_very_short)
                        
                        # Check if already expanded (has collapse button with GVHideDetailRow)
                        if img_class and ('gvDetailExpandedButton' in img_class or 'GVHideDetailRow' in (img_onclick or '')):
                            # Already expanded
                            return True
                        
                        # Check if it's an expand button (GVShowDetailRow)
                        if img_onclick and ('GVShowDetailRow' in img_onclick or (img_class and 'gvDetail' in img_class and 'Expanded' not in img_class)):
                            # Click to expand
                            driver.execute_script("arguments[0].click();", img)
                            return True
                    except:
                        continue
            
            # If no specific image found, try clicking the first cell
            driver.execute_script("arguments[0].click();", first_cell)
            return True
        
        # Fallback: Try to find expand button in first cell (older method)
        def get_expand_buttons():
            expand_images = first_cell.find_elements(By.CSS_SELECTOR, 
                "img[src*='Plus'], img[src*='plus'], img[src*='Expand'], img[src*='expand']")
            expand_links = first_cell.find_elements(By.CSS_SELECTOR, 
                "a.dxgvCommandColumnItem, a[onclick*='Expand'], a[onclick*='expand']")
            return expand_images + expand_links
        
        expand_buttons = retry_on_stale_element(get_expand_buttons, max_retries=3, delay=sleep_short)
        if expand_buttons:
            driver.execute_script("arguments[0].click();", expand_buttons[0])
            time.sleep(sleep_short / 4)
            return True
        
        # Try clicking the first cell directly
        driver.execute_script("arguments[0].click();", first_cell)
        time.sleep(sleep_short / 4)
        return True
    except Exception as e:
        print_with_timestamp(f"        [DEBUG] expand_row error: {e}")
        return False

def collapse_row(driver, row_id, reconnect_func=None, sleep_short=0.3):
    """Collapse a row by clicking the collapse button/icon using row ID
    
    Args:
        driver: WebDriver instance
        row_id: Row ID string to find the row element
        reconnect_func: Optional function to reconnect browser on stale element
        sleep_short: Short sleep duration in seconds (default: 0.3)
    """
    try:
        if not row_id:
            return False
        
        # Re-find the row element by ID with retry and reconnection support
        def find_row():
            return driver.find_element(By.ID, row_id)
        
        row_element = retry_on_stale_element(find_row, max_retries=3, delay=sleep_short, reconnect_func=reconnect_func)
        if not row_element:
            return False
        
        # Try to find collapse button in first cell
        try:
            first_cell = row_element.find_element(By.TAG_NAME, "td")
            collapse_buttons = first_cell.find_elements(By.CSS_SELECTOR, 
                "a.dxgvCommandColumnItem, img[src*='Minus'], img[src*='minus'], .dxgvCommandColumnItem")
            
            if collapse_buttons:
                driver.execute_script("arguments[0].click();", collapse_buttons[0])
                return True
            
            # Try clicking the first cell directly
            driver.execute_script("arguments[0].click();", first_cell)
            return True
        except StaleElementReferenceException:
            # Re-find and try again
            try:
                row_element = driver.find_element(By.ID, row_id)
                first_cell = row_element.find_element(By.TAG_NAME, "td")
                driver.execute_script("arguments[0].click();", first_cell)
                return True
            except:
                return False
    except:
        return False

def extract_entry_details_from_row(row_element, entry_column_map, reconnect_func=None, sleep_short=0.3):
    """Extract entry detail data from a row
    
    Args:
        row_element: Row element to extract from
        entry_column_map: Column mapping dictionary
        reconnect_func: Optional function to reconnect browser on stale element
        sleep_short: Short sleep duration in seconds (default: 0.3)
    """
    def extract_cells():
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
    
    try:
        result = retry_on_stale_element(extract_cells, max_retries=3, delay=sleep_short, reconnect_func=reconnect_func)
        return result
    except Exception as e:
        print_with_timestamp(f"      [WARNING] Error extracting entry details: {e}")
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
        print_with_timestamp(f"    [WARNING] Error getting/creating ShowClass: {e}")
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
        print_with_timestamp(f"      [WARNING] Error getting/creating horse: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()

def save_show_result_to_database(conn, show_class_id, entry_details, cursor=None, commit=True):
    """Save entry detail result to ShowResults table (with duplicate check)
    
    Args:
        conn: Database connection
        show_class_id: ShowClass ID
        entry_details: Dictionary with entry details
        cursor: Optional cursor to reuse (for batch operations). If None, creates new cursor.
        commit: Whether to commit after insert (default: True). Set False for batch operations.
    """
    if not entry_details:
        return False

    use_external_cursor = cursor is not None
    if not use_external_cursor:
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

        # Parse numeric values (re-parse since we need it for insert)
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

        if commit:
            conn.commit()
        return True
    except Exception as e:
        print_with_timestamp(f"      [WARNING] Error saving ShowResult to database: {e}")
        if commit:
            conn.rollback()
        return False
    finally:
        if not use_external_cursor:
            cursor.close()

def find_and_click_show_row(driver, show_guid, year, show_name, sleep_medium=3):
    """Find and click the show row in the ShowSelector grid to navigate to ClassResults
    
    Args:
        driver: WebDriver instance
        show_guid: ShowGUID to navigate to
        year: Year for navigation context
        show_name: Show name for navigation context
        sleep_medium: Medium sleep duration in seconds (default: 3)
    """
    try:
        # Wait for grid to load
        time.sleep(sleep_medium)
        
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
            print_with_timestamp(f"  [ERROR] Could not find grid for year {year}")
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
                        print_with_timestamp(f"  Found matching show row: {row_show_name}")
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
                        time.sleep(sleep_medium)  # Wait for navigation to ShowDetails page
                        
                        # Now click the ClassResults tab on the ShowDetails page
                        if activate_class_results_tab(driver):
                            print_with_timestamp(f"  [OK] Class Results tab activated")
                            return True
                        else:
                            print_with_timestamp(f"  [WARNING] Could not activate Class Results tab, trying direct navigation")
                            # Fallback to direct navigation
                            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                            driver.get(class_results_url)
                            time.sleep(sleep_medium)
                            return True
            except StaleElementReferenceException:
                print_with_timestamp(f"  [WARNING] Stale element when clicking, trying direct navigation")
            except Exception as e:
                print_with_timestamp(f"  [WARNING] Error clicking show row: {e}")
        
        # If we couldn't find it by name, try direct navigation
        print_with_timestamp(f"  [WARNING] Could not find show row by name '{show_name}', navigating directly to ClassResults")
        class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
        driver.get(class_results_url)
        time.sleep(sleep_medium)
        return True
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error finding/clicking show row: {e}")
        # Fallback to direct navigation
        class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
        driver.get(class_results_url)
        time.sleep(sleep_medium)
        return True

def scrape_class_results_for_show(driver, show_list_id, show_guid, year, show_name, conn, show_class_ids=None, sleep_short=0.5, sleep_medium=1, sleep_long=3):
    """Scrape class results for a single show
    
    Args:
        driver: WebDriver instance
        show_list_id: ID from ShowList table
        show_guid: ShowGUID string
        year: Year string
        show_name: Show name string
        conn: Database connection
        show_class_ids: Optional list of ShowClass IDs to process. If None, processes all classes.
        sleep_short: Short sleep duration in seconds (default: 0.5)
        sleep_medium: Medium sleep duration in seconds (default: 1)
        sleep_long: Long sleep duration in seconds (default: 3)
    """
    print_with_timestamp(f"\n{'='*60}")
    print_with_timestamp(f"Scraping class results for ShowGUID: {show_guid} (Year: {year})")
    if show_class_ids:
        print_with_timestamp(f"  Processing {len(show_class_ids)} specific classes only")
    print_with_timestamp(f"{'='*60}")
    
    # Log show processing start
    log_import_activity(conn, 'scrape_class_results.py', action='PROCESS_SHOW_START', 
                      additional_info=f'ShowGUID: {show_guid}, Year: {year}, ShowName: {show_name}, ShowListID: {show_list_id}, Specific classes: {len(show_class_ids) if show_class_ids else 0}')
    
    results_count = 0
    
    try:
        # Navigate to ShowSelector page first
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        if 'ShowSelector' not in driver.current_url:
            print_with_timestamp("  Navigating to ShowSelector page...")
            driver.get(show_selector_url)
            time.sleep(sleep_long)
            log_import_activity(conn, 'scrape_class_results.py', action='NAVIGATE', 
                              additional_info=f'Navigated to ShowSelector page for ShowGUID: {show_guid}')
        
        # Activate Shows By Year tab
        if not activate_shows_by_year_tab(driver):
            print_with_timestamp(f"  [WARNING] Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            driver.get(class_results_url)
            time.sleep(sleep_long)
        else:
            # Select the year
            if not select_year(driver, year):
                print_with_timestamp(f"  [WARNING] Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                driver.get(class_results_url)
                time.sleep(sleep_long)
            else:
                # Find and click the show row to navigate to ClassResults
                if not find_and_click_show_row(driver, show_guid, year, show_name):
                    print_with_timestamp(f"  [WARNING] Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    driver.get(class_results_url)
                    time.sleep(sleep_long)
        
        # Wait for the ClassResults page to load - look for the grid table
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
            )
        except TimeoutException:
            print_with_timestamp(f"  [WARNING] Grid table not found after 10 seconds")
        
        time.sleep(sleep_medium)  # Additional wait for JavaScript to populate grid
        
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
                            print_with_timestamp(f"  Found grid using selector: {selector} ({tr_count} rows)")
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
                            print_with_timestamp(f"  Found grid using fallback method ({tr_count} rows)")
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
                    print_with_timestamp(f"  Found grid using last resort method ({max_data_rows} data rows)")
            except:
                pass
        
        if not grid:
            print_with_timestamp(f"  [WARNING] Could not find results grid for ShowGUID: {show_guid}")
            log_import_activity(conn, 'scrape_class_results.py', action='ERROR', 
                              error_detail='Could not find results grid',
                              additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}')
            return 0, driver
        
        # Get column mapping for class summary
        class_column_map = get_column_indices_for_class_grid(grid)
        print_with_timestamp(f"  Class column mapping: {class_column_map}")
        log_import_activity(conn, 'scrape_class_results.py', action='GRID_FOUND', 
                          additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}, Column mapping: {class_column_map}')
        
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
        
        print_with_timestamp(f"  Found {len(class_rows)} class summary rows")
        log_import_activity(conn, 'scrape_class_results.py', action='GRID_ROWS_FOUND', 
                          additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}, Rows found: {len(class_rows)}')
        
        # If show_class_ids is provided, skip PASS 1 and query database for class info
        if show_class_ids:
            print_with_timestamp(f"\n  Skipping PASS 1 (class summaries already in database)")
            print_with_timestamp(f"  Building lookup map from grid rows...")
            
            # Build a lookup map: (Class, ClassName) -> row_index (case-insensitive keys)
            grid_lookup = {}  # Key: (class.lower(), class_name.lower()), Value: row_index (1-based)
            
            for idx, class_row in enumerate(class_rows, 1):
                def extract_class_info():
                    cells = class_row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 3:
                        return None, None
                    
                    # Get Class and ClassName from grid row
                    class_col_idx = class_column_map.get('Class')
                    class_name_col_idx = class_column_map.get('Class Name')
                    
                    if class_col_idx is not None and len(cells) > class_col_idx:
                        grid_class = cells[class_col_idx].text.strip()
                    else:
                        grid_class = ''
                    
                    if class_name_col_idx is not None and len(cells) > class_name_col_idx:
                        grid_class_name = cells[class_name_col_idx].text.strip()
                    else:
                        grid_class_name = ''
                    
                    return grid_class, grid_class_name
                
                try:
                    result = retry_on_stale_element(extract_class_info, max_retries=3, delay=sleep_short)
                    if result and result[0] is not None:
                        grid_class, grid_class_name = result
                        # Use case-insensitive keys for lookup
                        lookup_key = (grid_class.lower(), grid_class_name.lower())
                        grid_lookup[lookup_key] = idx
                except:
                    continue
            
            print_with_timestamp(f"  Built lookup map with {len(grid_lookup)} entries")
            print_with_timestamp(f"  Loading class information from database for {len(show_class_ids)} classes...")
            
            # Query database to get Class and ClassName for each ShowClass ID
            class_data_list = []  # Store (row_index, show_class_id, entries) for second pass
            cursor = conn.cursor()
            try:
                for show_class_id in show_class_ids:
                    cursor.execute("""
                        SELECT Class, ClassName, Entries, Placings 
                        FROM sResults.ShowClass 
                        WHERE ID = ?
                    """, show_class_id)
                    class_row_data = cursor.fetchone()
                    if class_row_data:
                        class_num = class_row_data[0] or ''
                        class_name = class_row_data[1] or ''
                        entries = class_row_data[2] if class_row_data[2] is not None else 0
                        placings = class_row_data[3] if class_row_data[3] is not None else 0
                        
                        # Look up the matching row in the grid using the lookup map
                        lookup_key = (str(class_num).strip().lower(), class_name.strip().lower())
                        row_index = grid_lookup.get(lookup_key)
                        
                        if row_index:
                            class_data_list.append((row_index, show_class_id, entries))
                            print_with_timestamp(f"    Found row {row_index} for Class {class_num}: {class_name[:50]}")
                        else:
                            print_with_timestamp(f"    [WARNING] Could not find grid row for Class {class_num}: {class_name[:50]}")
                    else:
                        print_with_timestamp(f"    [WARNING] ShowClass ID {show_class_id} not found in database")
            finally:
                cursor.close()
            
            print_with_timestamp(f"  [OK] Found {len(class_data_list)} matching classes in grid")
        else:
            # Debug: if no rows found, try to understand the structure
            if len(class_rows) == 0:
                all_rows = grid.find_elements(By.TAG_NAME, "tr")
                print_with_timestamp(f"  [DEBUG] Total rows in grid: {len(all_rows)}")
                if len(all_rows) > 0:
                    # Print first few rows' structure for debugging
                    for i, r in enumerate(all_rows[:10]):
                        row_id = r.get_attribute('id') or 'no-id'
                        row_class = r.get_attribute('class') or 'no-class'
                        cells = r.find_elements(By.TAG_NAME, "td, th")
                        cell_text = ''
                        if cells:
                            cell_text = cells[0].text[:50] if cells[0].text else 'empty'
                        print_with_timestamp(f"    Row {i+1}: id='{row_id[:60]}', class='{row_class[:60]}', cells={len(cells)}, first_cell='{cell_text}'")
            
            # PASS 1: Extract all class summary data and save to ShowClass table
            print_with_timestamp(f"\n  PASS 1: Extracting class summaries...")
            class_data_list = []  # Store (row_index, show_class_id, entries) for second pass
            showclass_count = 0  # Track ShowClass records created
            
            for row_idx, class_row in enumerate(class_rows, 1):
                try:
                    print_with_timestamp(f"  Extracting class row {row_idx}/{len(class_rows)}...")

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

                    # Extract class summary data with retry on stale element
                    def get_cells_and_extract():
                        cells = class_row.find_elements(By.TAG_NAME, "td")
                        if len(cells) < 3:
                            return None, None
                        class_summary = {}
                        for field, idx in class_column_map.items():
                            if idx is not None and len(cells) > idx:
                                class_summary[field] = cells[idx].text.strip()
                            else:
                                class_summary[field] = ''
                        return class_summary, cells
                    
                    result = retry_on_stale_element(get_cells_and_extract, max_retries=3, delay=sleep_short)
                    if not result or result[0] is None:
                        continue
                    
                    class_summary, cells = result

                    # Debug: Print first few cells to understand structure
                    if row_idx == 1 and cells:
                        print_with_timestamp(f"    [DEBUG] First row cell contents:")
                        for i, cell in enumerate(cells[:8]):
                            print_with_timestamp(f"      Cell {i}: '{cell.text.strip()[:50]}'")

                    # Validate that this looks like a real class row (not footer/copyright)
                    class_text = class_summary.get('Class', '').lower()
                    class_name_text = class_summary.get('Class Name', '').lower()
                    combined_text = (class_text + ' ' + class_name_text).lower()

                    exclude_text = ['copyright', 'all rights reserved', 'privacy policy', 
                                   'terms of service', 'contact', 'version', 'security alerts',
                                   'horseshowsonline', 'timeslice']

                    if any(exclude in combined_text for exclude in exclude_text):
                        print_with_timestamp(f"    Skipping footer row: {class_summary.get('Class', 'N/A')[:50]}")
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
                        print_with_timestamp(f"    Skipping non-data row (no class info)")
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
                        print_with_timestamp(f"    Skipping row with non-numeric Entries: '{entries}'")
                        continue

                    print_with_timestamp(f"    Class: {class_summary.get('Class', 'N/A')}, Class Name: {class_summary.get('Class Name', 'N/A')[:50]}, Entries: {entries}, Placings: {placings}")

                    # Save ShowClass to database (save all classes, even with 0 entries)
                    show_class_id = get_or_create_showclass(conn, show_list_id, class_summary)
                    if not show_class_id:
                        print_with_timestamp(f"      [WARNING] Could not create/get ShowClass")
                        continue
                    else:
                        showclass_count += 1

                    # Store for second pass (only if has placings > 0)
                    # If placings = 0, assume there are no results to acquire (but class is saved to DB)
                    placings_int = int(placings) if placings else 0
                    if placings_int > 0:
                        class_data_list.append((row_idx, show_class_id, entries))
                    else:
                        print_with_timestamp(f"      Class saved to database (Placings = 0, will not expand for results)")
                    
                except Exception as e:
                    print_with_timestamp(f"  [WARNING] Error extracting class row {row_idx}: {e}")
                    continue
            
            print_with_timestamp(f"  [OK] PASS 1 complete: {len(class_data_list)} classes with entries to process")
            # Log ShowClass saves
            if showclass_count > 0:
                log_import_activity(conn, 'scrape_class_results.py', target_table='ShowClass', 
                                  action='INSERT', row_count=showclass_count,
                                  additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}, Classes with entries: {len(class_data_list)}, Total classes: {showclass_count}')

        # PASS 2: Expand each class row and capture entry details
        print_with_timestamp(f"\n  PASS 2: Extracting entry details...")
        log_import_activity(conn, 'scrape_class_results.py', action='PASS2_START', 
                          additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}, Classes to process: {len(class_data_list)}')
        
        # Create reconnect function for this show context (closure that captures show context)
        # Note: driver is accessed from outer scope when called, not captured at definition time
        def create_reconnect_func():
            nonlocal driver  # Allow access to outer scope driver variable
            return reconnect_browser_and_navigate(driver, show_guid, year, show_name)
        
        for pass2_idx, (row_idx, show_class_id, entries) in enumerate(class_data_list, 1):
            try:
                print_with_timestamp(f"  Processing entry details {pass2_idx}/{len(class_data_list)} (row {row_idx})...")
                # Log class processing start
                log_import_activity(conn, 'scrape_class_results.py', action='PROCESS_CLASS_START', 
                                  target_table='ShowResults',
                                  additional_info=f'ShowClassID: {show_class_id}, RowIdx: {row_idx}, Class {pass2_idx}/{len(class_data_list)}')
                
                # Get class details (Entries, Placings, and NonPlacingComplete) for validation
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT Entries, Placings, ISNULL(NonPlacingComplete, 0) 
                        FROM sResults.ShowClass 
                        WHERE ID = ?
                    """, show_class_id)
                    class_row_data = cursor.fetchone()
                    max_entries = class_row_data[0] if class_row_data and class_row_data[0] is not None else None
                    max_placings = class_row_data[1] if class_row_data and class_row_data[1] is not None else None
                    nonplacing_complete = class_row_data[2] if class_row_data and class_row_data[2] is not None else 0
                    cursor.close()
                except:
                    max_entries = None
                    max_placings = None
                    nonplacing_complete = 0
                
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
                    print_with_timestamp(f"    [WARNING] Row {row_idx} no longer available")
                    continue
                
                class_row = rows[row_idx - 1]
                # Store row ID immediately while element is fresh
                class_row_id = ''
                try:
                    class_row_id = class_row.get_attribute('id') or ''
                except:
                    pass

                # Expand and extract entry details
                if entries:
                    try:
                        # Expand the row - re-find it first to avoid stale element
                        print_with_timestamp(f"      Attempting to expand row {row_idx}...")
                        # Always re-find the row right before expanding to avoid stale element
                        try:
                            grid = driver.find_element(By.CSS_SELECTOR,
                                "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                            all_rows = grid.find_elements(By.TAG_NAME, "tr")
                            rows_refresh = []
                            for r in all_rows:
                                try:
                                    row_id = r.get_attribute('id') or ''
                                    row_class = r.get_attribute('class') or ''
                                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                        rows_refresh.append(r)
                                except StaleElementReferenceException:
                                    continue
                            
                            # Try to find by index first, then by ID
                            if row_idx <= len(rows_refresh):
                                class_row = rows_refresh[row_idx - 1]
                                # Update class_row_id after finding row by index
                                try:
                                    class_row_id = class_row.get_attribute('id') or ''
                                except:
                                    pass
                            elif class_row_id:
                                # Try to find by ID
                                for r in rows_refresh:
                                    try:
                                        if r.get_attribute('id') == class_row_id:
                                            class_row = r
                                            break
                                    except StaleElementReferenceException:
                                        continue
                        except Exception as e:
                            print_with_timestamp(f"        [DEBUG] Error re-finding row before expand: {e}")
                            # Try to continue with original row, expand_row will handle stale elements
                        
                        # Check if we have a valid row ID before attempting expansion
                        if not class_row_id:
                            print_with_timestamp(f"      [ERROR] Could not get row ID for row {row_idx} after refresh, attempting to get from current row element...")
                            # Last attempt: try to get ID from current class_row element
                            try:
                                if 'class_row' in locals() and class_row:
                                    class_row_id = class_row.get_attribute('id') or ''
                                    if class_row_id:
                                        print_with_timestamp(f"      [OK] Retrieved row ID: {class_row_id}")
                                    else:
                                        print_with_timestamp(f"      [ERROR] Row element exists but has no ID, skipping row {row_idx}")
                                        continue
                                else:
                                    print_with_timestamp(f"      [ERROR] Row element not available, skipping row {row_idx}")
                                    continue
                            except Exception as e2:
                                print_with_timestamp(f"      [ERROR] Exception getting row ID: {e2}, skipping row {row_idx}")
                                continue
                        
                        row_expanded = expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                        if row_expanded:
                            log_import_activity(conn, 'scrape_class_results.py', action='ROW_EXPANDED', 
                                              additional_info=f'ShowClassID: {show_class_id}, RowID: {class_row_id}')
                            # Use WebDriverWait instead of fixed sleep for better performance
                            try:
                                WebDriverWait(driver, 3).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grPlacing']"))
                                )
                            except:
                                time.sleep(sleep_short)  # Fallback to short sleep if wait fails
                            
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
                            
                            # Try multiple strategies to find detail rows (with retry on stale element and reconnection)
                            max_strategy_retries = 3
                            strategy_retry_delay = 0.5
                            strategy_success = False
                            driver_reconnected = False
                            
                            for strategy_attempt in range(max_strategy_retries):
                                if strategy_success:
                                    break
                                
                                try:
                                    # On second retry or later, try reconnecting browser if stale elements persist
                                    if strategy_attempt > 0 and not driver_reconnected:
                                        print_with_timestamp(f"      [RETRY] Attempting browser reconnection before retry {strategy_attempt + 1}/{max_strategy_retries}...")
                                        new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                        if new_driver:
                                            driver = new_driver
                                            driver_reconnected = True
                                            # Re-find grid and rows after reconnection
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
                                                class_row_id = class_row.get_attribute('id') or ''
                                                # Re-expand the row after reconnection
                                                print_with_timestamp(f"      [RECONNECT] Re-expanding row after browser reconnection...")
                                                expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                time.sleep(sleep_medium)
                                    
                                    # Strategy 1: Look for grPlacing grids (nested result grids) following the class row
                                    # Always re-find grid and class_row to avoid stale elements - rebuild all references from scratch
                                    try:
                                        grid = driver.find_element(By.CSS_SELECTOR,
                                            "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                        all_trs = grid.find_elements(By.TAG_NAME, "tr")
                                        
                                        # Re-find class_row by row_idx to get fresh reference
                                        rows_refresh = []
                                        for r in all_trs:
                                            try:
                                                row_id_refresh = r.get_attribute('id') or ''
                                                row_class_refresh = r.get_attribute('class') or ''
                                                if ('DataRow' in row_id_refresh or 'dxgvDataRow' in row_class_refresh) and 'HeaderRow' not in row_id_refresh and 'FilterRow' not in row_id_refresh:
                                                    rows_refresh.append(r)
                                            except StaleElementReferenceException:
                                                continue
                                        
                                        if row_idx <= len(rows_refresh):
                                            class_row_refresh = rows_refresh[row_idx - 1]
                                            current_class_row_id = class_row_refresh.get_attribute('id') or ''
                                            # Update class_row reference for consistency
                                            class_row = class_row_refresh
                                        else:
                                            print_with_timestamp(f"      Strategy 1: Row index {row_idx} out of range (found {len(rows_refresh)} rows)")
                                            current_class_row_id = None
                                    except Exception as e:
                                        print_with_timestamp(f"      Strategy 1 error re-finding elements: {e}")
                                        current_class_row_id = None
                                    
                                    if not current_class_row_id:
                                        print_with_timestamp(f"      Strategy 1: Could not find class row, skipping this attempt...")
                                        # Don't continue - let it fall through to Strategy 2
                                        pass
                                    else:
                                    
                                        # Find the class row index in all_trs
                                        class_row_idx = -1
                                        for i, tr in enumerate(all_trs):
                                            try:
                                                tr_id = tr.get_attribute('id') or ''
                                                if tr_id == current_class_row_id:
                                                    class_row_idx = i
                                                    break
                                            except StaleElementReferenceException:
                                                continue
                                            except Exception:
                                                continue
                                        
                                        if class_row_idx >= 0:
                                            # Look for the next tr(s) that contain grPlacing grids
                                            for i in range(class_row_idx + 1, len(all_trs)):
                                                try:
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
                                                except StaleElementReferenceException:
                                                    # Skip this row if it becomes stale
                                                    continue
                                                except Exception:
                                                    # Skip this row on other errors
                                                    continue
                                            
                                            if detail_rows:
                                                print_with_timestamp(f"      Strategy 1 found {len(detail_rows)} detail rows in grPlacing grids")
                                                strategy_success = True
                                                break
                                except StaleElementReferenceException as e:
                                    if strategy_attempt < max_strategy_retries - 1:
                                        print_with_timestamp(f"      Strategy 1 stale element (attempt {strategy_attempt + 1}/{max_strategy_retries}), attempting browser reconnection...")
                                        
                                        # Immediately attempt browser reconnection on stale element
                                        if not driver_reconnected:
                                            try:
                                                new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                                if new_driver:
                                                    driver = new_driver
                                                    driver_reconnected = True
                                                    
                                                    # Re-find ALL elements from scratch after reconnection
                                                    print_with_timestamp(f"      [RECONNECT] Re-establishing context after browser reconnection...")
                                                    grid = driver.find_element(By.CSS_SELECTOR,
                                                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                                    all_rows_reconnect = grid.find_elements(By.TAG_NAME, "tr")
                                                    rows_reconnect = []
                                                    for r in all_rows_reconnect:
                                                        row_id_reconnect = r.get_attribute('id') or ''
                                                        row_class_reconnect = r.get_attribute('class') or ''
                                                        if ('DataRow' in row_id_reconnect or 'dxgvDataRow' in row_class_reconnect) and 'HeaderRow' not in row_id_reconnect and 'FilterRow' not in row_id_reconnect:
                                                            rows_reconnect.append(r)
                                                    
                                                    if row_idx <= len(rows_reconnect):
                                                        class_row = rows_reconnect[row_idx - 1]  # Fresh reference
                                                        class_row_id = class_row.get_attribute('id') or ''
                                                        # Re-expand the row after reconnection
                                                        print_with_timestamp(f"      [RECONNECT] Re-expanding row {row_idx} after browser reconnection...")
                                                        expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                        time.sleep(sleep_long)  # Longer wait after reconnection
                                                        print_with_timestamp(f"      Retrying Strategy 1 after reconnection...")
                                                        detail_rows = []  # Reset for retry
                                                        continue  # Continue to next iteration with fresh elements
                                                    else:
                                                        print_with_timestamp(f"      [ERROR] Row {row_idx} no longer available after reconnection")
                                                        break
                                                else:
                                                    print_with_timestamp(f"      [WARNING] Browser reconnection failed, retrying without reconnection...")
                                                    time.sleep(strategy_retry_delay)
                                                    detail_rows = []  # Reset for retry
                                                    continue
                                            except Exception as reconnect_error:
                                                print_with_timestamp(f"      [WARNING] Error during browser reconnection: {reconnect_error}")
                                                time.sleep(strategy_retry_delay)
                                                detail_rows = []  # Reset for retry
                                                continue
                                        else:
                                            # Already reconnected, but still getting stale elements - try to refresh elements one more time
                                            print_with_timestamp(f"      Browser already reconnected, refreshing element references...")
                                            try:
                                                grid = driver.find_element(By.CSS_SELECTOR,
                                                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                                all_rows_refresh = grid.find_elements(By.TAG_NAME, "tr")
                                                rows_refresh = []
                                                for r in all_rows_refresh:
                                                    row_id_refresh = r.get_attribute('id') or ''
                                                    row_class_refresh = r.get_attribute('class') or ''
                                                    if ('DataRow' in row_id_refresh or 'dxgvDataRow' in row_class_refresh) and 'HeaderRow' not in row_id_refresh and 'FilterRow' not in row_id_refresh:
                                                        rows_refresh.append(r)
                                                
                                                if row_idx <= len(rows_refresh):
                                                    class_row = rows_refresh[row_idx - 1]  # Fresh reference
                                                    class_row_id = class_row.get_attribute('id') or ''
                                                    # Re-expand to ensure row is expanded
                                                    expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                    time.sleep(sleep_medium)
                                            except Exception as refresh_error:
                                                print_with_timestamp(f"      [WARNING] Error refreshing elements: {refresh_error}")
                                            
                                            time.sleep(strategy_retry_delay)
                                            detail_rows = []  # Reset for retry
                                            continue  # Continue to next iteration
                                    else:
                                        print_with_timestamp(f"      Strategy 1 error (final attempt): {e}")
                                        break  # Break out of loop on final attempt
                                except Exception as e:
                                    print_with_timestamp(f"      Strategy 1 error: {e}")
                                
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
                                                
                                                if detail_rows:
                                                    print_with_timestamp(f"      Strategy 2 found {len(detail_rows)} detail rows (checked {len(all_rows)} total rows, started at index {current_idx})")
                                                    strategy_success = True
                                                    break
                                        except StaleElementReferenceException as e:
                                            if strategy_attempt < max_strategy_retries - 1:
                                                print_with_timestamp(f"      Strategy 2 stale element (attempt {strategy_attempt + 1}/{max_strategy_retries}), attempting browser reconnection...")
                                                
                                                # Immediately attempt browser reconnection on stale element
                                                if not driver_reconnected:
                                                    try:
                                                        new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                                        if new_driver:
                                                            driver = new_driver
                                                            driver_reconnected = True
                                                            # Re-find grid and rows after reconnection
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
                                                                class_row_id = class_row.get_attribute('id') or ''
                                                                # Re-expand the row after reconnection
                                                                print_with_timestamp(f"      [RECONNECT] Re-expanding row after browser reconnection...")
                                                                expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                                time.sleep(sleep_medium)
                                                                print_with_timestamp(f"      Retrying Strategy 2 after reconnection...")
                                                            else:
                                                                print_with_timestamp(f"      [ERROR] Row {row_idx} no longer available after reconnection")
                                                                break
                                                        else:
                                                            print_with_timestamp(f"      [WARNING] Browser reconnection failed, retrying without reconnection...")
                                                            time.sleep(strategy_retry_delay)
                                                    except Exception as reconnect_error:
                                                        print_with_timestamp(f"      [WARNING] Error during browser reconnection: {reconnect_error}")
                                                        time.sleep(strategy_retry_delay)
                                                else:
                                                    print_with_timestamp(f"      Browser already reconnected, retrying...")
                                                    time.sleep(strategy_retry_delay)
                                                
                                                detail_rows = []  # Reset for retry
                                                continue  # Continue to next iteration instead of raising
                                            else:
                                                print_with_timestamp(f"      Strategy 2 error (final attempt): {e}")
                                                break  # Break out of loop on final attempt
                                        except Exception as e:
                                            print_with_timestamp(f"      Strategy 2 error: {e}")
                                
                                    # Strategy 3: Look for nested table within the row
                                    if not detail_rows:
                                        try:
                                            nested_tables = class_row.find_elements(By.TAG_NAME, "table")
                                            print_with_timestamp(f"      Strategy 3: Found {len(nested_tables)} nested tables")
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
                                                    print_with_timestamp(f"      Strategy 3 found {len(detail_rows)} detail rows in nested table")
                                                    strategy_success = True
                                                    break
                                        except StaleElementReferenceException as e:
                                            if strategy_attempt < max_strategy_retries - 1:
                                                print_with_timestamp(f"      Strategy 3 stale element (attempt {strategy_attempt + 1}/{max_strategy_retries}), attempting browser reconnection...")
                                                
                                                # Immediately attempt browser reconnection on stale element
                                                if not driver_reconnected:
                                                    try:
                                                        new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                                        if new_driver:
                                                            driver = new_driver
                                                            driver_reconnected = True
                                                            # Re-find grid and rows after reconnection
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
                                                                class_row_id = class_row.get_attribute('id') or ''
                                                                # Re-expand the row after reconnection
                                                                print_with_timestamp(f"      [RECONNECT] Re-expanding row after browser reconnection...")
                                                                expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                                time.sleep(sleep_medium)
                                                                print_with_timestamp(f"      Retrying Strategy 3 after reconnection...")
                                                            else:
                                                                print_with_timestamp(f"      [ERROR] Row {row_idx} no longer available after reconnection")
                                                                break
                                                        else:
                                                            print_with_timestamp(f"      [WARNING] Browser reconnection failed, retrying without reconnection...")
                                                            time.sleep(strategy_retry_delay)
                                                    except Exception as reconnect_error:
                                                        print_with_timestamp(f"      [WARNING] Error during browser reconnection: {reconnect_error}")
                                                        time.sleep(strategy_retry_delay)
                                                else:
                                                    print_with_timestamp(f"      Browser already reconnected, retrying...")
                                                    time.sleep(strategy_retry_delay)
                                                
                                                detail_rows = []  # Reset for retry
                                                continue  # Continue to next iteration instead of raising
                                            else:
                                                print_with_timestamp(f"      Strategy 3 error (final attempt): {e}")
                                                break  # Break out of loop on final attempt
                                        except Exception as e:
                                            print_with_timestamp(f"      Strategy 3 error: {e}")
                                
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
                                                
                                                if detail_rows:
                                                    print_with_timestamp(f"      Strategy 4 found {len(detail_rows)} detail rows")
                                                    strategy_success = True
                                                    break
                                        except StaleElementReferenceException as e:
                                            if strategy_attempt < max_strategy_retries - 1:
                                                print_with_timestamp(f"      Strategy 4 stale element (attempt {strategy_attempt + 1}/{max_strategy_retries}), attempting browser reconnection...")
                                                
                                                # Immediately attempt browser reconnection on stale element
                                                if not driver_reconnected:
                                                    try:
                                                        new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                                        if new_driver:
                                                            driver = new_driver
                                                            driver_reconnected = True
                                                            # Re-find grid and rows after reconnection
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
                                                                class_row_id = class_row.get_attribute('id') or ''
                                                                # Re-expand the row after reconnection
                                                                print_with_timestamp(f"      [RECONNECT] Re-expanding row after browser reconnection...")
                                                                expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                                time.sleep(sleep_medium)
                                                                print_with_timestamp(f"      Retrying Strategy 4 after reconnection...")
                                                            else:
                                                                print_with_timestamp(f"      [ERROR] Row {row_idx} no longer available after reconnection")
                                                                break
                                                        else:
                                                            print_with_timestamp(f"      [WARNING] Browser reconnection failed, retrying without reconnection...")
                                                            time.sleep(strategy_retry_delay)
                                                    except Exception as reconnect_error:
                                                        print_with_timestamp(f"      [WARNING] Error during browser reconnection: {reconnect_error}")
                                                        time.sleep(strategy_retry_delay)
                                                else:
                                                    print_with_timestamp(f"      Browser already reconnected, retrying...")
                                                    time.sleep(strategy_retry_delay)
                                                
                                                detail_rows = []  # Reset for retry
                                                continue  # Continue to next iteration instead of raising
                                            else:
                                                print_with_timestamp(f"      Strategy 4 error (final attempt): {e}")
                                                break  # Break out of loop on final attempt
                                        except Exception as e:
                                            print_with_timestamp(f"      Strategy 4 error: {e}")
                                
                                except StaleElementReferenceException as e:
                                    # Outer catch for any stale element in strategies 1-4
                                    if strategy_attempt < max_strategy_retries - 1:
                                        print_with_timestamp(f"      Stale element in strategies (attempt {strategy_attempt + 1}/{max_strategy_retries}), attempting browser reconnection...")
                                        
                                        # Immediately attempt browser reconnection on stale element
                                        if not driver_reconnected:
                                            try:
                                                new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                                if new_driver:
                                                    driver = new_driver
                                                    driver_reconnected = True
                                                    # Re-find grid and rows after reconnection
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
                                                        class_row_id = class_row.get_attribute('id') or ''
                                                        # Re-expand the row after reconnection
                                                        print_with_timestamp(f"      [RECONNECT] Re-expanding row after browser reconnection...")
                                                        expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                                                        time.sleep(sleep_medium)
                                                        print_with_timestamp(f"      Retrying strategies after reconnection...")
                                                    else:
                                                        print_with_timestamp(f"      [ERROR] Row {row_idx} no longer available after reconnection")
                                                        break
                                                else:
                                                    print_with_timestamp(f"      [WARNING] Browser reconnection failed, retrying without reconnection...")
                                                    time.sleep(strategy_retry_delay)
                                            except Exception as reconnect_error:
                                                print_with_timestamp(f"      [WARNING] Error during browser reconnection: {reconnect_error}")
                                                time.sleep(strategy_retry_delay)
                                        else:
                                            print_with_timestamp(f"      Browser already reconnected, retrying...")
                                            time.sleep(strategy_retry_delay)
                                        
                                        detail_rows = []  # Reset for retry
                                        continue  # Continue to next iteration
                                    else:
                                        print_with_timestamp(f"      Strategies failed after {max_strategy_retries} attempts: {e}")
                                        break  # Break out of loop on final attempt
                            
                            print_with_timestamp(f"      Total found: {len(detail_rows)} entry detail rows")
                            
                            # Log extraction
                            if detail_rows:
                                log_import_activity(conn, 'scrape_class_results.py', action='EXTRACT_DATA', 
                                                  additional_info=f'ShowClassID: {show_class_id}, Entry detail rows found: {len(detail_rows)}')
                            
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
                                            print_with_timestamp(f"      [WARNING] Could not find grid table for column mapping")
                                
                                if grid_table:
                                    entry_column_map = get_column_indices_for_entry_grid(grid_table)
                                    print_with_timestamp(f"      Entry column mapping: {entry_column_map}")
                                else:
                                    print_with_timestamp(f"      [WARNING] Cannot extract entry details without grid table")
                                    entry_column_map = {}
                                
                                # Extract all entry details first (batch extraction for better performance)
                                all_entry_details = []
                                for detail_row_item in detail_rows:
                                    # Extract row element from tuple if it's a tuple
                                    if isinstance(detail_row_item, tuple):
                                        detail_row = detail_row_item[0]
                                    else:
                                        detail_row = detail_row_item
                                    
                                    if entry_column_map:
                                        # Direct extraction without retry overhead (rows should be fresh)
                                        try:
                                            cells = detail_row.find_elements(By.TAG_NAME, "td")
                                            if len(cells) >= 3:
                                                entry_data = {}
                                                for field, idx in entry_column_map.items():
                                                    if idx is not None and len(cells) > idx:
                                                        entry_data[field] = cells[idx].text.strip()
                                                    else:
                                                        entry_data[field] = ''
                                                if entry_data:
                                                    all_entry_details.append(entry_data)
                                        except StaleElementReferenceException:
                                            # Fallback to retry function if stale (with reconnection support)
                                            entry_details = extract_entry_details_from_row(detail_row, entry_column_map, reconnect_func=create_reconnect_func)
                                            if entry_details:
                                                all_entry_details.append(entry_details)
                                        except Exception as e:
                                            pass  # Skip this row
                                
                                # Batch save to database (use single transaction for better performance)
                                if all_entry_details:
                                    print_with_timestamp(f"      Extracted {len(all_entry_details)} entry details, saving to database...")
                                    saved_entries = 0
                                    cursor = conn.cursor()
                                    try:
                                        for entry_details in all_entry_details:
                                            # Use batch mode (no commit per entry)
                                            if save_show_result_to_database(conn, show_class_id, entry_details, cursor=cursor, commit=False):
                                                saved_entries += 1
                                                results_count += 1
                                        # Commit all entries at once
                                        conn.commit()
                                        print_with_timestamp(f"      Saved {saved_entries}/{len(all_entry_details)} entries")
                                        # Log batch save
                                        log_import_activity(conn, 'scrape_class_results.py', target_table='ShowResults', 
                                                          action='INSERT', row_count=saved_entries,
                                                          additional_info=f'ShowClassID: {show_class_id}, Batch size: {len(all_entry_details)}')
                                    except Exception as e:
                                        conn.rollback()
                                        print_with_timestamp(f"      [WARNING] Error in batch save, rolling back: {e}")
                                        log_import_activity(conn, 'scrape_class_results.py', target_table='ShowResults', 
                                                          action='ERROR', error_detail=str(e),
                                                          additional_info=f'ShowClassID: {show_class_id}, Batch size: {len(all_entry_details)}')
                                    finally:
                                        cursor.close()
                                elif entry_column_map:
                                    print_with_timestamp(f"      [WARNING] No entry details extracted from {len(detail_rows)} rows")
                            else:
                                print_with_timestamp(f"      [WARNING] No entry detail rows found after expansion")
                            
                            # Check if there are non-placing entries to capture (Entries > Placings)
                            # Skip if already marked as complete
                            if max_entries and max_placings and max_entries > max_placings and not nonplacing_complete:
                                nonplacing_count = max_entries - max_placings
                                print_with_timestamp(f"      Checking for non-placing entries ({nonplacing_count} expected)...")
                            elif nonplacing_complete:
                                print_with_timestamp(f"      Skipping non-placing entries (already marked as complete)")
                                
                                # Find non-placing entries grid (tables that are NOT grPlacing)
                                nonplacing_detail_rows = []
                                max_nonplacing_retries = 3
                                nonplacing_success = False
                                
                                for nonplacing_attempt in range(max_nonplacing_retries):
                                    if nonplacing_success:
                                        break
                                    
                                    try:
                                        # Re-find grid and rows to avoid stale elements
                                        grid_nonplacing = driver.find_element(By.CSS_SELECTOR,
                                            "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                        all_trs_nonplacing = grid_nonplacing.find_elements(By.TAG_NAME, "tr")
                                        
                                        # Find the class row index again
                                        class_row_idx_nonplacing = -1
                                        for i, tr in enumerate(all_trs_nonplacing):
                                            try:
                                                tr_id = tr.get_attribute('id') or ''
                                                if tr_id == class_row_id:
                                                    class_row_idx_nonplacing = i
                                                    break
                                            except StaleElementReferenceException:
                                                continue
                                        
                                        if class_row_idx_nonplacing >= 0:
                                            # Look for rows following the class row that contain non-placing entry grids (NOT grPlacing)
                                            for i in range(class_row_idx_nonplacing + 1, len(all_trs_nonplacing)):
                                                try:
                                                    next_tr = all_trs_nonplacing[i]
                                                    next_tr_id = next_tr.get_attribute('id') or ''
                                                    next_tr_class = next_tr.get_attribute('class') or ''
                                                    
                                                    # If this is another class row, stop
                                                    if 'DataRow' in next_tr_id and 'dxdt' not in next_tr_id and 'dxgvDetailRow' not in next_tr_class:
                                                        cells = next_tr.find_elements(By.TAG_NAME, "td")
                                                        if len(cells) >= 2:
                                                            break
                                                    
                                                    # Look for tables that are NOT grPlacing (those are the placing entries)
                                                    nested_tables = next_tr.find_elements(By.TAG_NAME, "table")
                                                    for nested_table in nested_tables:
                                                        table_id = nested_table.get_attribute('id') or ''
                                                        
                                                        # Skip placing entry grids (grPlacing)
                                                        if 'grPlacing' in table_id:
                                                            continue
                                                        
                                                        # Look for non-placing entry grids (12 columns: Entry, Horse, Rider, Country, Owner, Trainer, Prize, Start, Score, Percent, USEF, EC)
                                                        table_rows = nested_table.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow'], tr.dxgvDataRow")
                                                        if table_rows:
                                                            # Check if this looks like a non-placing entry table (has 12 columns)
                                                            for tr in table_rows[:1]:  # Check first row to see structure
                                                                cells = tr.find_elements(By.TAG_NAME, "td")
                                                                if len(cells) >= 12:  # 12 columns for non-placing entries
                                                                    # This could be a non-placing entry grid
                                                                    # Store all rows from this table
                                                                    for nr in table_rows:
                                                                        nr_id = nr.get_attribute('id') or ''
                                                                        if 'HeaderRow' not in nr_id and 'FilterRow' not in nr_id:
                                                                            nonplacing_detail_rows.append((nr, nested_table))
                                                                    break
                                                except StaleElementReferenceException:
                                                    if nonplacing_attempt < max_nonplacing_retries - 1:
                                                        raise  # Re-raise to trigger retry
                                                    continue
                                                except Exception:
                                                    continue
                                        
                                        if nonplacing_detail_rows:
                                            print_with_timestamp(f"      Found {len(nonplacing_detail_rows)} non-placing entry rows")
                                            nonplacing_success = True
                                            break
                                    except StaleElementReferenceException:
                                        if nonplacing_attempt < max_nonplacing_retries - 1:
                                            print_with_timestamp(f"      Non-placing grid search stale element (attempt {nonplacing_attempt + 1}/{max_nonplacing_retries}), retrying...")
                                            time.sleep(sleep_short / 4)
                                            continue
                                        else:
                                            break
                                    except Exception as e:
                                        if nonplacing_attempt < max_nonplacing_retries - 1:
                                            time.sleep(sleep_short / 4)
                                            continue
                                        else:
                                            print_with_timestamp(f"      [WARNING] Error finding non-placing entries grid: {e}")
                                            break
                                
                                # Extract and save non-placing entries
                                if nonplacing_detail_rows:
                                    # Get column mapping for non-placing entries
                                    nonplacing_grid_table = nonplacing_detail_rows[0][1] if isinstance(nonplacing_detail_rows[0], tuple) else None
                                    if nonplacing_grid_table:
                                        nonplacing_column_map = get_column_indices_for_nonplacing_grid(nonplacing_grid_table)
                                        print_with_timestamp(f"      Non-placing entry column mapping: {nonplacing_column_map}")
                                    else:
                                        print_with_timestamp(f"      [WARNING] Could not find grid table for non-placing column mapping")
                                        nonplacing_column_map = {}
                                    
                                    # Extract all non-placing entry details
                                    all_nonplacing_details = []
                                    seen_nonplacing_entries = set()
                                    
                                    for detail_row_item in nonplacing_detail_rows:
                                        if isinstance(detail_row_item, tuple):
                                            detail_row = detail_row_item[0]
                                        else:
                                            detail_row = detail_row_item
                                        
                                        if nonplacing_column_map:
                                            try:
                                                cells = detail_row.find_elements(By.TAG_NAME, "td")
                                                if len(cells) >= 3:
                                                    entry_data = {}
                                                    # Set Place to 0 for non-placing entries
                                                    entry_data['Place'] = '0'
                                                    # Set AddBack to '$0.00' for non-placing entries (not in grid)
                                                    entry_data['AddBack'] = '$0.00'
                                                    
                                                    for field, idx in nonplacing_column_map.items():
                                                        if field in ['Place', 'AddBack']:
                                                            continue  # Already set to defaults, skip these fields
                                                        if idx is not None and len(cells) > idx:
                                                            entry_data[field] = cells[idx].text.strip()
                                                        else:
                                                            entry_data[field] = ''
                                                    
                                                    # Check for duplicates using Entry number
                                                    entry_number = entry_data.get('Entry', '').strip()
                                                    if entry_number:
                                                        if entry_number in seen_nonplacing_entries:
                                                            continue  # Skip duplicate
                                                        seen_nonplacing_entries.add(entry_number)
                                                    
                                                    if entry_data and len(all_nonplacing_details) < nonplacing_count:
                                                        all_nonplacing_details.append(entry_data)
                                            except StaleElementReferenceException:
                                                # Use retry function for stale elements
                                                def extract_nonplacing_entry():
                                                    cells = detail_row.find_elements(By.TAG_NAME, "td")
                                                    if len(cells) < 3:
                                                        return None
                                                    entry_data = {}
                                                    # Set Place to 0 for non-placing entries
                                                    entry_data['Place'] = '0'
                                                    # Set AddBack to '$0.00' for non-placing entries (not in grid)
                                                    entry_data['AddBack'] = '$0.00'
                                                    
                                                    for field, idx in nonplacing_column_map.items():
                                                        if field in ['Place', 'AddBack']:
                                                            continue  # Already set to defaults
                                                        if idx is not None and len(cells) > idx:
                                                            entry_data[field] = cells[idx].text.strip()
                                                        else:
                                                            entry_data[field] = ''
                                                    return entry_data
                                                
                                                entry_details = retry_on_stale_element(extract_nonplacing_entry, max_retries=3, delay=sleep_short, reconnect_func=create_reconnect_func)
                                                if entry_details:
                                                    entry_details['Place'] = '0'  # Ensure Place is set
                                                    entry_details['AddBack'] = '$0.00'  # Ensure AddBack is set
                                                    entry_number = entry_details.get('Entry', '').strip()
                                                    if entry_number and entry_number not in seen_nonplacing_entries:
                                                        seen_nonplacing_entries.add(entry_number)
                                                        if len(all_nonplacing_details) < nonplacing_count:
                                                            all_nonplacing_details.append(entry_details)
                                            except Exception:
                                                pass
                                    
                                    # Save non-placing entries to database
                                    if all_nonplacing_details:
                                        print_with_timestamp(f"      Extracted {len(all_nonplacing_details)} non-placing entry details, saving to database...")
                                        saved_nonplacing = 0
                                        cursor_nonplacing = conn.cursor()
                                        try:
                                            for entry_details in all_nonplacing_details:
                                                if save_show_result_to_database(conn, show_class_id, entry_details, cursor=cursor_nonplacing, commit=False):
                                                    saved_nonplacing += 1
                                                    results_count += 1
                                            conn.commit()
                                            print_with_timestamp(f"      Saved {saved_nonplacing}/{len(all_nonplacing_details)} non-placing entries")
                                            
                                            # Check if we've reached the expected count and mark as complete
                                            cursor_check_complete = conn.cursor()
                                            cursor_check_complete.execute("""
                                                SELECT COUNT(*) 
                                                FROM sResults.ShowResults 
                                                WHERE ShowClassID = ? AND Place = 0
                                            """, show_class_id)
                                            final_nonplacing_count = cursor_check_complete.fetchone()[0]
                                            cursor_check_complete.close()
                                            
                                            if final_nonplacing_count >= nonplacing_count:
                                                cursor_mark = conn.cursor()
                                                cursor_mark.execute("""
                                                    UPDATE sResults.ShowClass 
                                                    SET NonPlacingComplete = 1, UpdatedDate = GETDATE()
                                                    WHERE ID = ?
                                                """, show_class_id)
                                                conn.commit()
                                                cursor_mark.close()
                                                print_with_timestamp(f"      [OK] Marked class as complete ({final_nonplacing_count}/{nonplacing_count} non-placing entries)")
                                            
                                            # Log batch save
                                            log_import_activity(conn, 'scrape_class_results.py', target_table='ShowResults', 
                                                              action='INSERT', row_count=saved_nonplacing,
                                                              additional_info=f'ShowClassID: {show_class_id}, Non-placing entries, Batch size: {len(all_nonplacing_details)}')
                                        except Exception as e:
                                            conn.rollback()
                                            print_with_timestamp(f"      [WARNING] Error in batch save of non-placing entries, rolling back: {e}")
                                            log_import_activity(conn, 'scrape_class_results.py', target_table='ShowResults', 
                                                              action='ERROR', error_detail=str(e),
                                                              additional_info=f'ShowClassID: {show_class_id}, Non-placing entries, Batch size: {len(all_nonplacing_details)}')
                                        finally:
                                            cursor_nonplacing.close()
                                    elif nonplacing_column_map:
                                        print_with_timestamp(f"      [WARNING] No non-placing entry details extracted from {len(nonplacing_detail_rows)} rows")
                                elif max_entries and max_placings and max_entries > max_placings:
                                    print_with_timestamp(f"      [WARNING] No non-placing entry rows found (expected {nonplacing_count})")
                        else:
                            # Expansion failed - report error and potentially retry
                            print_with_timestamp(f"      [ERROR] Failed to expand row {row_idx} (row_expanded=False)")
                            print_with_timestamp(f"      [ERROR] Row ID: {class_row_id}")
                            # Don't skip the row - try to continue or log the failure
                            # We could retry here or mark it for later processing
                            
                            # Collapse row after capturing data (even if expansion failed, ensure row state is correct)
                            try:
                                # Re-find the row to avoid stale element
                                def refresh_for_collapse():
                                    grid_collapse = driver.find_element(By.CSS_SELECTOR, 
                                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                    rows_collapse = grid_collapse.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                    if not rows_collapse:
                                        all_rows_collapse = grid_collapse.find_elements(By.TAG_NAME, "tr")
                                        rows_collapse = []
                                        for r in all_rows_collapse:
                                            row_id_c = r.get_attribute('id') or ''
                                            row_class_c = r.get_attribute('class') or ''
                                            if ('DataRow' in row_id_c or 'dxgvDataRow' in row_class_c) and 'HeaderRow' not in row_id_c and 'FilterRow' not in row_id_c:
                                                rows_collapse.append(r)
                                    
                                    if row_idx <= len(rows_collapse):
                                        row_to_collapse = rows_collapse[row_idx - 1]
                                        collapse_row_id_c = row_to_collapse.get_attribute('id') or ''
                                        if collapse_row_id_c:
                                            collapse_row(driver, collapse_row_id_c, reconnect_func=create_reconnect_func)
                                            return True
                                    return False
                                
                                # Try with retry and reconnection support
                                try:
                                    refresh_for_collapse()
                                except StaleElementReferenceException:
                                    # Try reconnecting and retrying
                                    new_driver_collapse = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
                                    if new_driver_collapse:
                                        driver = new_driver_collapse
                                        # Re-expand first to get back to the same state
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
                                            collapse_row_id = row_to_collapse.get_attribute('id') or ''
                                            if collapse_row_id:
                                                collapse_row(driver, collapse_row_id, reconnect_func=create_reconnect_func)
                            except Exception as e:
                                print_with_timestamp(f"      [WARNING] Could not collapse row: {e}")
                    except Exception as e:
                        print_with_timestamp(f"    [WARNING] Error expanding/extracting entry details: {e}")
                        import traceback
                        traceback.print_exc()
                        continue

            except Exception as e:
                print_with_timestamp(f"  [WARNING] Error processing entry details for row {row_idx}: {e}")
                continue
        
        print_with_timestamp(f"  [OK] Completed scraping for ShowGUID {show_guid}: {results_count} results saved")
        
        # Log show processing completion
        log_import_activity(conn, 'scrape_class_results.py', action='PROCESS_SHOW_COMPLETE', 
                          row_count=results_count,
                          additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}, Total results saved: {results_count}')
        
        return results_count, driver  # Return driver in case it was reconnected
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error scraping class results for ShowGUID {show_guid}: {e}")
        import traceback
        traceback.print_exc()
        return results_count, driver  # Return driver in case it was reconnected

def main(skip_processed=True, load_missing_classes=False, start_from_show_guid=None, sleep_short=0.5, sleep_medium=1):
    """Main function to scrape class results
    
    Args:
        skip_processed: If True, skip shows that already have ShowClass or ShowResults data (default: True)
        load_missing_classes: If True, load only classes with Placings > 0 that don't have ShowResults (default: False)
        start_from_show_guid: Optional ShowGUID to start from (only processes ShowListID >= that ShowGUID's ID)
        sleep_short: Short sleep duration in seconds (default: 0.5)
        sleep_medium: Medium sleep duration in seconds (default: 1)
    """
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("HorseShowsOnline - Class Results Scraper")
    print_with_timestamp("=" * 60 + "\n")
    
    if load_missing_classes:
        print_with_timestamp("[INFO] Will load only missing class results (classes with Placings > 0 that don't have ShowResults)\n")
    elif skip_processed:
        print_with_timestamp("[INFO] Will skip shows with existing ShowClass or ShowResults data\n")
    else:
        print_with_timestamp("[INFO] Will process all shows, including those with existing data\n")
    
    driver = None
    conn = None
    
    try:
        # Setup driver
        print_with_timestamp("Initializing browser (headless mode)...")
        driver = setup_driver(headless=True)
        print_with_timestamp("  [OK] Browser initialized\n")
        
        # Connect to database
        print_with_timestamp("Connecting to database...")
        conn = get_db_connection()
        print_with_timestamp("[OK] Connected to database")
        
        # Create tables
        print_with_timestamp("\nEnsuring database tables exist...")
        create_importlog_table_if_not_exists(conn)
        create_competitors_table_if_not_exists(conn)
        create_horse_table_if_not_exists(conn)
        create_showclass_table_if_not_exists(conn)
        create_showresults_table_if_not_exists(conn)
        print_with_timestamp("[OK] Database tables verified/created\n")
        
        # Log script start
        log_import_activity(conn, 'scrape_class_results.py', action='START', 
                          additional_info=f'skip_processed={skip_processed}, load_missing_classes={load_missing_classes}, start_from_show_guid={start_from_show_guid}')
        
        # Get ShowGUIDs, Years, and ShowNames from database
        if load_missing_classes:
            print_with_timestamp("Fetching shows with missing class results...")
            show_data_list = get_shows_with_missing_classes(conn, start_from_show_guid=start_from_show_guid)
            print_with_timestamp(f"[OK] Found {len(show_data_list)} shows with missing classes\n")
            
            if not show_data_list:
                print_with_timestamp("[WARNING] No shows with missing class results found.")
                return
            
            # Scrape results for each show (with specific class IDs)
            total_results = 0
            for idx, (show_list_id, show_guid, year, show_name, missing_class_ids) in enumerate(show_data_list, 1):
                print_with_timestamp(f"\nProcessing show {idx}/{len(show_data_list)} ({len(missing_class_ids)} missing classes)...")
                results_count, driver = scrape_class_results_for_show(driver, show_list_id, show_guid, year, show_name, conn, show_class_ids=missing_class_ids, sleep_short=sleep_short, sleep_medium=sleep_medium)
                total_results += results_count
                
                # Small delay between shows
                time.sleep(sleep_medium)
        else:
            print_with_timestamp("Fetching ShowGUIDs, Years, and ShowNames from ShowList table...")
            show_data_list = get_show_data_from_database(conn, skip_processed=skip_processed, start_from_show_guid=start_from_show_guid)
            print_with_timestamp(f"[OK] Found {len(show_data_list)} shows\n")
            
            if not show_data_list:
                print_with_timestamp("[WARNING] No ShowGUIDs found in database. Please run scrape_shows_by_year.py first.")
                return
            
            # Scrape results for each show
            total_results = 0
            for idx, (show_list_id, show_guid, year, show_name) in enumerate(show_data_list, 1):
                print_with_timestamp(f"\nProcessing show {idx}/{len(show_data_list)}...")
                results_count, driver = scrape_class_results_for_show(driver, show_list_id, show_guid, year, show_name, conn, sleep_short=sleep_short, sleep_medium=sleep_medium)
                total_results += results_count
                
                # Small delay between shows
                time.sleep(sleep_medium)
        
        print_with_timestamp(f"\n{'='*60}")
        print_with_timestamp(f"Scraping complete! Total results collected: {total_results}")
        print_with_timestamp(f"{'='*60}\n")
        
        # Log completion
        if conn:
            log_import_activity(conn, 'scrape_class_results.py', action='COMPLETE', 
                              row_count=total_results, additional_info=f'Total results: {total_results}')
        
    except KeyboardInterrupt:
        print_with_timestamp("\n\n[WARNING] Scraping interrupted by user")
        if conn:
            log_import_activity(conn, 'scrape_class_results.py', action='INTERRUPTED', 
                              error_detail='User interrupted scraping')
    except Exception as e:
        print_with_timestamp(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        error_trace = traceback.format_exc()
        if conn:
            log_import_activity(conn, 'scrape_class_results.py', action='ERROR', 
                              error_detail=str(e), additional_info=error_trace[:4000])  # Limit to 4000 chars
        traceback.print_exc()
    finally:
        if conn:
            try:
                conn.close()
                print_with_timestamp("[OK] Database connection closed")
            except:
                pass
        if driver:
            print_with_timestamp("\nClosing browser...")
            driver.quit()

if __name__ == '__main__':
    import sys
    
    # Check for command-line arguments
    skip_processed = True
    load_missing_classes = False
    start_from_show_guid = None
    
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        arg_lower = arg.lower()
        
        if arg_lower in ['--process-all', '-a', '--all']:
            skip_processed = False
            print_with_timestamp("[INFO] Command-line argument detected: Will process all shows (including those with existing data)")
        elif arg_lower in ['--load-missing', '-m', '--missing']:
            load_missing_classes = True
            print_with_timestamp("[INFO] Command-line argument detected: Will load only missing class results")
        elif arg_lower in ['--start-from', '-s']:
            if i + 1 < len(sys.argv):
                start_from_show_guid = sys.argv[i + 1]
                print_with_timestamp(f"[INFO] Command-line argument detected: Will start from ShowGUID {start_from_show_guid}")
                i += 1  # Skip the next argument as it's the ShowGUID value
            else:
                print_with_timestamp("[ERROR] --start-from requires a ShowGUID value")
                sys.exit(1)
        elif arg_lower in ['--help', '-h']:
            print_with_timestamp("Usage: python scrape_class_results.py [OPTIONS]")
            print_with_timestamp("Options:")
            print_with_timestamp("  --process-all, -a, --all: Process all shows, including those with existing ShowClass or ShowResults data")
            print_with_timestamp("  --load-missing, -m, --missing: Load only missing class results (classes with Placings > 0 that don't have ShowResults)")
            print_with_timestamp("  --start-from SHOWGUID, -s SHOWGUID: Start processing from the specified ShowGUID (only processes ShowListID >= that ShowGUID's ID)")
            print_with_timestamp("  Default: Skip shows with existing data")
            sys.exit(0)
        
        i += 1
    
    # load_missing_classes takes precedence over skip_processed
    if load_missing_classes:
        skip_processed = False
    
    main(skip_processed=skip_processed, load_missing_classes=load_missing_classes, start_from_show_guid=start_from_show_guid, sleep_short=0.5, sleep_medium=1)

