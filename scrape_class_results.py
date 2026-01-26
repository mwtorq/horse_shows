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
import getpass
import socket
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
def reconnect_browser_and_navigate(driver, show_guid, year, show_name, current_url_hint=None, sleep_short=0.3, sleep_medium=0.5, sleep_long=1):
    """Reconnect browser and navigate back to ClassResults page (optimized for speed)
    
    Args:
        driver: Current WebDriver instance (will be quit and replaced)
        show_guid: ShowGUID to navigate to
        year: Year for navigation context
        show_name: Show name for navigation context
        current_url_hint: Optional hint about what URL we were on
        sleep_short: Short sleep duration in seconds (default: 0.3, optimized for speed)
        sleep_medium: Medium sleep duration in seconds (default: 0.5, optimized for speed)
        sleep_long: Long sleep duration in seconds (default: 1, optimized for speed)
    
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
        
        # Minimal wait
        time.sleep(sleep_short)
        
        # Create new browser instance
        print_with_timestamp(f"      [RECONNECT] Creating new browser connection...")
        new_driver = setup_driver(headless=True)
        
        # Navigate back to ClassResults page using ShowSelector (required)
        print_with_timestamp(f"      [RECONNECT] Navigating to ShowSelector page...")
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        new_driver.get(show_selector_url)
        
        # Wait for page to load minimally
        try:
            WebDriverWait(new_driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.dxtc-tab, table[id*='grMaster']"))
            )
        except:
            time.sleep(sleep_medium)  # Fallback minimal wait
        
        # Activate Shows By Year tab (optimized - reduced sleeps)
        print_with_timestamp(f"      [RECONNECT] Activating 'Shows By Year' tab...")
        if not activate_shows_by_year_tab(new_driver, sleep_medium=0.5, sleep_short=0.2):
            print_with_timestamp(f"      [RECONNECT] Warning: Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            new_driver.get(class_results_url)
            # Wait for grid with WebDriverWait instead of fixed sleep
            try:
                WebDriverWait(new_driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                )
            except:
                time.sleep(sleep_long)  # Fallback wait
        else:
            # Select the year (optimized - reduced sleeps)
            print_with_timestamp(f"      [RECONNECT] Selecting year {year}...")
            if not select_year(new_driver, year, sleep_short=0.5, sleep_medium=0.8):
                print_with_timestamp(f"      [RECONNECT] Warning: Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                new_driver.get(class_results_url)
                # Wait for grid with WebDriverWait instead of fixed sleep
                try:
                    WebDriverWait(new_driver, 6).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                    )
                except:
                    time.sleep(sleep_long)  # Fallback wait
            else:
                # Find and click the show row (optimized - reduced sleeps)
                print_with_timestamp(f"      [RECONNECT] Finding and clicking show row...")
                if not find_and_click_show_row(new_driver, show_guid, year, show_name, sleep_medium=1):
                    print_with_timestamp(f"      [RECONNECT] Warning: Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    new_driver.get(class_results_url)
                    # Wait for grid with WebDriverWait instead of fixed sleep
                    try:
                        WebDriverWait(new_driver, 6).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                        )
                    except:
                        time.sleep(sleep_long)  # Fallback wait
        
        # Wait for grid to load with optimized timeout
        try:
            print_with_timestamp(f"      [RECONNECT] Waiting for grid table to load...")
            WebDriverWait(new_driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']"))
            )
            print_with_timestamp(f"      [RECONNECT] Grid table found")
        except TimeoutException:
            print_with_timestamp(f"      [RECONNECT] Warning: Grid table not found after 8 seconds, retrying...")
            # Retry once with a fresh navigation
            try:
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                new_driver.get(class_results_url)
                WebDriverWait(new_driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']"))
                )
                print_with_timestamp(f"      [RECONNECT] Grid table found after retry")
            except:
                print_with_timestamp(f"      [RECONNECT] Warning: Grid table still not found, but continuing...")
        
        time.sleep(sleep_short)  # Minimal additional wait for JavaScript
        
        print_with_timestamp(f"      [RECONNECT] Browser reconnected successfully")
        return new_driver
        
    except Exception as e:
        print_with_timestamp(f"      [RECONNECT] Error reconnecting browser: {e}")
        import traceback
        traceback.print_exc()
        return None

def retry_on_stale_element(operation_func, max_retries=3, delay=0.1, reconnect_func=None, max_total_time=20, operation_name="operation", *args, **kwargs):
    """Helper function to retry an operation on StaleElementReferenceException
    
    Args:
        operation_func: Function to execute that may throw StaleElementReferenceException
        max_retries: Maximum number of retry attempts (default: 3)
        delay: Delay between retries in seconds (default: 0.1, very fast)
        reconnect_func: Optional function to reconnect browser. Called early if time limit exceeded.
        max_total_time: Maximum total time in seconds before forcing reconnection (default: 20)
        operation_name: Name of operation for logging (default: "operation")
        *args, **kwargs: Arguments to pass to operation_func
    
    Returns:
        Result of operation_func, or None if all retries failed
    """
    import time as time_module
    start_time = time_module.time()
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                elapsed = time_module.time() - start_time
                print_with_timestamp(f"      [RETRY] Attempt {attempt + 1}/{max_retries} for {operation_name} (elapsed: {elapsed:.1f}s)...")
            return operation_func(*args, **kwargs)
        except StaleElementReferenceException as e:
            last_exception = e
            elapsed_time = time_module.time() - start_time
            
            # If we've exceeded the time limit, try reconnection immediately
            if reconnect_func and elapsed_time >= max_total_time:
                print_with_timestamp(f"      [RETRY] {operation_name} timeout ({elapsed_time:.1f}s >= {max_total_time}s), attempting browser reconnection...")
                new_driver = reconnect_func()
                if new_driver:
                    if 'driver' in kwargs:
                        kwargs['driver'] = new_driver
                    print_with_timestamp(f"      [RETRY] Browser reconnected, retrying {operation_name}...")
                    time.sleep(delay * 2)
                    start_time = time_module.time()  # Reset timer after reconnect
                    continue
            
            if attempt < max_retries - 1:
                # Try reconnection early (on second attempt) if we're getting persistent stale elements
                if reconnect_func and attempt == 1 and elapsed_time >= 5:  # After 5 seconds, try reconnection
                    print_with_timestamp(f"      [RETRY] {operation_name} stale element persists after {attempt + 1} attempts ({elapsed_time:.1f}s), attempting browser reconnection...")
                    new_driver = reconnect_func()
                    if new_driver:
                        if 'driver' in kwargs:
                            kwargs['driver'] = new_driver
                        print_with_timestamp(f"      [RETRY] Browser reconnected, retrying {operation_name}...")
                        time.sleep(delay * 2)
                        start_time = time_module.time()  # Reset timer after reconnect
                        continue
                else:
                    # Fast retry with minimal delay
                    print_with_timestamp(f"      [RETRY] Stale element on {operation_name}, retrying in {delay}s (attempt {attempt + 1}/{max_retries}, elapsed: {elapsed_time:.1f}s)...")
                    time.sleep(delay)
                    continue
            else:
                # Last attempt failed, return None
                elapsed_time = time_module.time() - start_time
                print_with_timestamp(f"      [RETRY] {operation_name} failed after {max_retries} attempts ({elapsed_time:.1f}s)")
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
    # Check if running on LDAHSAR - use Windows authentication if so
    hostname = socket.gethostname().upper()
    use_windows_auth = (hostname == 'LDAHSAR')
    
    if use_windows_auth:
        print_with_timestamp(f"[INFO] Running on {hostname}, using Windows authentication")
    else:
        # Prompt for password for sa user on other machines
        password = getpass.getpass("Enter SQL Server password for sa user: ")
    
    drivers = [
        'ODBC Driver 17 for SQL Server',
        'ODBC Driver 18 for SQL Server',
        'SQL Server',
        'SQL Server Native Client 11.0',
    ]
    
    for driver in drivers:
        try:
            if use_windows_auth:
                # Use Windows authentication (Trusted Connection)
                conn_str = f'DRIVER={{{driver}}};SERVER=LDAHSAR\\SQLEXPRESS;DATABASE=HorseShows;Trusted_Connection=yes;'
            else:
                # Use SQL Server authentication with sa user
                conn_str = f'DRIVER={{{driver}}};SERVER=LDAHSAR\\SQLEXPRESS;DATABASE=HorseShows;UID=sa;PWD={password};'
            
            conn = pyodbc.connect(conn_str)
            auth_method = "Windows authentication" if use_windows_auth else "SQL Server authentication (sa)"
            print_with_timestamp(f"[OK] Connected to HorseShows database using driver: {driver} ({auth_method})")
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
                    RiderUSEFID NVARCHAR(50),
                    RiderState NVARCHAR(10),
                    RiderUSEFStatus NVARCHAR(500),
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
            
            # Check if new columns exist, add them if not
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_SCHEMA = 'sResults' 
                AND TABLE_NAME = 'Competitors' 
                AND COLUMN_NAME = 'RiderUSEFID'
            """)
            has_rider_usef_id = cursor.fetchone()[0] > 0
            
            if not has_rider_usef_id:
                print_with_timestamp("Adding RiderUSEFID, RiderState, and RiderUSEFStatus columns to Competitors table...")
                try:
                    # Add columns after Rider column (need to use ALTER TABLE ADD)
                    cursor.execute("""
                        ALTER TABLE sResults.Competitors 
                        ADD RiderUSEFID NVARCHAR(50),
                            RiderState NVARCHAR(10),
                            RiderUSEFStatus NVARCHAR(500)
                    """)
                    conn.commit()
                    print_with_timestamp("[OK] Added RiderUSEFID, RiderState, and RiderUSEFStatus columns")
                except Exception as e:
                    print_with_timestamp(f"[WARNING] Error adding new columns: {e}")
            
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

def activate_shows_by_year_tab(driver, sleep_medium=0.5, sleep_short=0.2):
    """Activate the 'Shows By Year' tab
    
    Args:
        driver: WebDriver instance
        sleep_medium: Medium sleep duration in seconds (default: 3)
        sleep_short: Short sleep duration in seconds (default: 0.5)
    """
    print_with_timestamp("Activating 'Shows By Year' tab...")
    
    try:
        # Reduced initial wait - use WebDriverWait instead
        try:
            WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.dxtc-tab"))
            )
        except:
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

def activate_class_results_tab(driver, sleep_short=0.5, sleep_medium=1):
    """Activate the 'Class Results' tab on ShowDetails page
    
    Args:
        driver: WebDriver instance
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    """
    print_with_timestamp("  Activating 'Class Results' tab...")
    
    try:
        # Reduced initial wait - use WebDriverWait instead
        try:
            WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.dxtc-tab"))
            )
        except:
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

def select_year(driver, year, sleep_short=0.5, sleep_medium=0.8):
    """Select a specific year in the year picker
    
    Args:
        driver: WebDriver instance
        year: Year to select
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    """
    print_with_timestamp(f"\nSelecting year {year}...")
    
    try:
        # Reduced initial wait - use WebDriverWait instead
        try:
            WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.ID, "MainContent_panFilter_ddShowYear_I"))
            )
        except:
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
        
        # Wait for grid to update (reduced wait)
        time.sleep(sleep_medium)
        
        # Use WebDriverWait to check if grid has updated instead of fixed sleep
        try:
            WebDriverWait(driver, 2).until(
                lambda d: d.find_element(By.ID, picker_id).get_attribute('value') == str(year)
            )
        except:
            pass  # Continue even if wait fails
        
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

def get_incomplete_classes_for_show(conn, show_list_id, skip_processed=True):
    """Get list of ShowClass IDs that still need processing for a show
    
    Includes:
    1. Classes with Placings > 0 that don't have placing ShowResults (Place > 0) - NonPlacingComplete is ignored for placing entries
    2. Classes that have placing results but are missing non-placing entries (Entries > Placings and NonPlacingComplete = 0)
    
    Note: NonPlacingComplete field only applies to non-placing entries (Place = 0).
    Placing entries (Place > 0) are always collected regardless of NonPlacingComplete status.
    
    Args:
        conn: Database connection
        show_list_id: ShowList ID
        skip_processed: If True, only return classes that need processing.
                       If False, return all classes with Placings > 0 (for reprocessing).
    
    Returns:
        List of ShowClass IDs that need processing, or None if all classes should be processed
    """
    try:
        cursor = conn.cursor()
        
        if skip_processed:
            # Get classes that need processing:
            # 1. Classes with Placings > 0 that don't have placing ShowResults (Place > 0) - ignore NonPlacingComplete
            # 2. Classes that have placing results but are missing non-placing entries (Entries > Placings and NonPlacingComplete = 0)
            cursor.execute("""
                SELECT DISTINCT sc.ID
                FROM sResults.ShowClass sc
                WHERE sc.ShowListID = ?
                AND sc.Placings > 0
                AND (
                    -- Case 1: No placing results at all (Place > 0) - ignore NonPlacingComplete for placing entries
                    NOT EXISTS (
                        SELECT 1
                        FROM sResults.ShowResults sr
                        WHERE sr.ShowClassID = sc.ID
                        AND sr.Place > 0
                    )
                    OR
                    -- Case 2: Has placing results but missing non-placing entries (only check NonPlacingComplete for non-placing)
                    (
                        sc.Entries > sc.Placings
                        AND ISNULL(sc.NonPlacingComplete, 0) = 0
                        AND EXISTS (
                            SELECT 1
                            FROM sResults.ShowResults sr
                            WHERE sr.ShowClassID = sc.ID
                            AND sr.Place > 0
                        )
                    )
                )
                ORDER BY sc.ID
            """, show_list_id)
        else:
            # Get all classes with Placings > 0 (for reprocessing)
            cursor.execute("""
                SELECT sc.ID
                FROM sResults.ShowClass sc
                WHERE sc.ShowListID = ?
                AND sc.Placings > 0
                ORDER BY sc.ID
            """, show_list_id)
        
        incomplete_class_ids = [row[0] for row in cursor.fetchall()]
        cursor.close()
        
        return incomplete_class_ids if incomplete_class_ids else None
    except Exception as e:
        print_with_timestamp(f"[WARNING] Error getting incomplete classes for ShowListID {show_list_id}: {e}")
        return None

def get_show_data_from_database(conn, skip_processed=True, start_from_show_guid=None, single_show_guid=None):
    """Get ID, ShowGUID, Year, and ShowName from ShowList table where EndDate < today, ordered by ID
    
    Args:
        conn: Database connection
        skip_processed: If True, skip shows that already have ShowClass or ShowResults data
        start_from_show_guid: Optional ShowGUID to start from (only processes ShowListID >= that ShowGUID's ID)
        single_show_guid: Optional ShowGUID to load only that specific show
    """
    try:
        cursor = conn.cursor()
        
        # If single_show_guid is provided, filter for exactly that ShowGUID
        # When loading a single show, be more lenient with criteria (only require ShowGUID exists)
        # Ignore skip_processed when loading a single show (user explicitly requested it)
        if single_show_guid:
            print_with_timestamp(f"[INFO] Loading single show: ShowGUID {single_show_guid}")
            # Always load the show when explicitly requested, regardless of skip_processed
            cursor.execute("""
                SELECT ID, ShowGUID, Year, ShowName 
                FROM sResults.ShowList 
                WHERE ShowGUID = ?
                AND ShowGUID IS NOT NULL AND ShowGUID != ''
                ORDER BY ID
            """, single_show_guid)
            
            show_data = [(row[0], row[1], row[2], row[3]) for row in cursor.fetchall()]
            cursor.close()
            if show_data:
                print_with_timestamp(f"[OK] Found show: {show_data[0][3]} (ShowGUID: {single_show_guid})")
            else:
                print_with_timestamp(f"[WARNING] ShowGUID {single_show_guid} not found in database")
            return show_data
        
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

def get_shows_with_missing_classes(conn, start_from_show_guid=None, single_show_guid=None):
    """Get shows that have ShowClass rows with Placings > 0 that don't have corresponding ShowResults
    
    Args:
        conn: Database connection
        start_from_show_guid: Optional ShowGUID to start from (only processes ShowListID >= that ShowGUID's ID)
        single_show_guid: Optional ShowGUID to load only that specific show
    
    Returns: List of tuples (show_list_id, show_guid, year, show_name, list of ShowClass IDs to process)
    """
    try:
        cursor = conn.cursor()
        
        # If single_show_guid is provided, filter for exactly that ShowGUID
        # When loading a single show, be more lenient with criteria (only require ShowGUID exists)
        if single_show_guid:
            print_with_timestamp(f"[INFO] Loading single show: ShowGUID {single_show_guid}")
            cursor.execute("""
                SELECT DISTINCT
                    sl.ID,
                    sl.ShowGUID,
                    sl.Year,
                    sl.ShowName
                FROM sResults.ShowList sl
                WHERE sl.ShowGUID = ?
                AND sl.ShowGUID IS NOT NULL AND sl.ShowGUID != ''
                -- Has ShowClass rows that need processing (missing placing results OR missing non-placing entries)
                AND EXISTS (
                    SELECT 1
                    FROM sResults.ShowClass sc
                    WHERE sc.ShowListID = sl.ID
                    AND sc.Placings > 0
                    AND (
                        -- Case 1: No placing results at all (Place > 0)
                        NOT EXISTS (
                            SELECT 1
                            FROM sResults.ShowResults sr
                            WHERE sr.ShowClassID = sc.ID
                            AND sr.Place > 0
                        )
                        OR
                        -- Case 2: Has placing results but missing non-placing entries
                        (
                            sc.Entries > sc.Placings
                            AND ISNULL(sc.NonPlacingComplete, 0) = 0
                            AND EXISTS (
                                SELECT 1
                                FROM sResults.ShowResults sr
                                WHERE sr.ShowClassID = sc.ID
                                AND sr.Place > 0
                            )
                        )
                    )
                )
                ORDER BY sl.ID
            """, single_show_guid)
            
            show_data = cursor.fetchall()
            result = []
            
            # For each show, get the specific ShowClass IDs that need processing
            for row in show_data:
                show_list_id = row[0]
                show_guid = row[1]
                year = row[2]
                show_name = row[3]
                
                # Get ShowClass IDs that need processing (using same logic as get_incomplete_classes_for_show):
                # 1. Classes with Placings > 0 that don't have placing ShowResults (Place > 0)
                # 2. Classes that have placing results but are missing non-placing entries (Entries > Placings and NonPlacingComplete = 0)
                cursor.execute("""
                    SELECT DISTINCT sc.ID
                    FROM sResults.ShowClass sc
                    WHERE sc.ShowListID = ?
                    AND sc.Placings > 0
                    AND (
                        -- Case 1: No placing results at all (Place > 0) - ignore NonPlacingComplete for placing entries
                        NOT EXISTS (
                            SELECT 1
                            FROM sResults.ShowResults sr
                            WHERE sr.ShowClassID = sc.ID
                            AND sr.Place > 0
                        )
                        OR
                        -- Case 2: Has placing results but missing non-placing entries (only check NonPlacingComplete for non-placing)
                        (
                            sc.Entries > sc.Placings
                            AND ISNULL(sc.NonPlacingComplete, 0) = 0
                            AND EXISTS (
                                SELECT 1
                                FROM sResults.ShowResults sr
                                WHERE sr.ShowClassID = sc.ID
                                AND sr.Place > 0
                            )
                        )
                    )
                    ORDER BY sc.ID
                """, show_list_id)
                
                missing_class_ids = [r[0] for r in cursor.fetchall()]
                
                if missing_class_ids:
                    result.append((show_list_id, show_guid, year, show_name, missing_class_ids))
            
            cursor.close()
            if result:
                print_with_timestamp(f"[OK] Found show: {result[0][3]} (ShowGUID: {single_show_guid})")
                print_with_timestamp(f"[OK] Total missing classes to process: {sum(len(ids) for _, _, _, _, ids in result)}")
            else:
                # Provide more detailed error message
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ID, ShowGUID, Year, ShowName
                    FROM sResults.ShowList 
                    WHERE ShowGUID = ?
                """, single_show_guid)
                check_row = cursor.fetchone()
                cursor.close()
                
                if check_row:
                    show_id, show_guid, year, show_name = check_row
                    # Check if it has missing classes (using same logic as get_incomplete_classes_for_show)
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM sResults.ShowClass sc
                        WHERE sc.ShowListID = ?
                        AND sc.Placings > 0
                        AND (
                            -- Case 1: No placing results at all (Place > 0)
                            NOT EXISTS (
                                SELECT 1
                                FROM sResults.ShowResults sr
                                WHERE sr.ShowClassID = sc.ID
                                AND sr.Place > 0
                            )
                            OR
                            -- Case 2: Has placing results but missing non-placing entries
                            (
                                sc.Entries > sc.Placings
                                AND ISNULL(sc.NonPlacingComplete, 0) = 0
                                AND EXISTS (
                                    SELECT 1
                                    FROM sResults.ShowResults sr
                                    WHERE sr.ShowClassID = sc.ID
                                    AND sr.Place > 0
                                )
                            )
                        )
                    """, show_id)
                    missing_count = cursor.fetchone()[0]
                    cursor.close()
                    
                    if missing_count == 0:
                        print_with_timestamp(f"[WARNING] ShowGUID {single_show_guid} found in database ({show_name}) but has no missing classes")
                    else:
                        print_with_timestamp(f"[WARNING] ShowGUID {single_show_guid} found in database ({show_name}) but query did not return it")
                else:
                    print_with_timestamp(f"[WARNING] ShowGUID {single_show_guid} not found in database")
            return result
        
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
                -- Has ShowClass rows that need processing (missing placing results OR missing non-placing entries)
                AND EXISTS (
                    SELECT 1
                    FROM sResults.ShowClass sc
                    WHERE sc.ShowListID = sl.ID
                    AND sc.Placings > 0
                    AND (
                        -- Case 1: No placing results at all (Place > 0)
                        NOT EXISTS (
                            SELECT 1
                            FROM sResults.ShowResults sr
                            WHERE sr.ShowClassID = sc.ID
                            AND sr.Place > 0
                        )
                        OR
                        -- Case 2: Has placing results but missing non-placing entries
                        (
                            sc.Entries > sc.Placings
                            AND ISNULL(sc.NonPlacingComplete, 0) = 0
                            AND EXISTS (
                                SELECT 1
                                FROM sResults.ShowResults sr
                                WHERE sr.ShowClassID = sc.ID
                                AND sr.Place > 0
                            )
                        )
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
                -- Has ShowClass rows that need processing (missing placing results OR missing non-placing entries)
                AND EXISTS (
                    SELECT 1
                    FROM sResults.ShowClass sc
                    WHERE sc.ShowListID = sl.ID
                    AND sc.Placings > 0
                    AND (
                        -- Case 1: No placing results at all (Place > 0)
                        NOT EXISTS (
                            SELECT 1
                            FROM sResults.ShowResults sr
                            WHERE sr.ShowClassID = sc.ID
                            AND sr.Place > 0
                        )
                        OR
                        -- Case 2: Has placing results but missing non-placing entries
                        (
                            sc.Entries > sc.Placings
                            AND ISNULL(sc.NonPlacingComplete, 0) = 0
                            AND EXISTS (
                                SELECT 1
                                FROM sResults.ShowResults sr
                                WHERE sr.ShowClassID = sc.ID
                                AND sr.Place > 0
                            )
                        )
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
            
            # Get ShowClass IDs that need processing (using same logic as get_incomplete_classes_for_show):
            # 1. Classes with Placings > 0 that don't have placing ShowResults (Place > 0)
            # 2. Classes that have placing results but are missing non-placing entries (Entries > Placings and NonPlacingComplete = 0)
            cursor.execute("""
                SELECT DISTINCT sc.ID
                FROM sResults.ShowClass sc
                WHERE sc.ShowListID = ?
                AND sc.Placings > 0
                AND (
                    -- Case 1: No placing results at all (Place > 0) - ignore NonPlacingComplete for placing entries
                    NOT EXISTS (
                        SELECT 1
                        FROM sResults.ShowResults sr
                        WHERE sr.ShowClassID = sc.ID
                        AND sr.Place > 0
                    )
                    OR
                    -- Case 2: Has placing results but missing non-placing entries (only check NonPlacingComplete for non-placing)
                    (
                        sc.Entries > sc.Placings
                        AND ISNULL(sc.NonPlacingComplete, 0) = 0
                        AND EXISTS (
                            SELECT 1
                            FROM sResults.ShowResults sr
                            WHERE sr.ShowClassID = sc.ID
                            AND sr.Place > 0
                        )
                    )
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

def expand_row(driver, row_id, reconnect_func=None, sleep_short=0.1, sleep_very_short=0.05):
    """Expand a row by clicking the expand button/icon using row ID
    
    Args:
        driver: WebDriver instance
        row_id: Row ID string to find the row element
        reconnect_func: Optional function to reconnect browser on stale element
        sleep_short: Short sleep duration in seconds (default: 0.1, reduced for faster retries)
        sleep_very_short: Very short sleep duration in seconds (default: 0.05)
    """
    try:
        if not row_id:
            return False
        
        # Validate that this is a main row ID, not a detail row ID
        # Detail rows contain: grPlacing, grNonPlacing, dxdt (detail containers), or are in detail grids
        detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
        is_detail_row = any(indicator in row_id for indicator in detail_row_indicators)
        
        if is_detail_row:
            print_with_timestamp(f"        [EXPAND] Rejected detail row ID: {row_id[:50]}...")
            return False
        
        # Always re-find the row element immediately before use (don't cache)
        def find_and_click_expand():
            # Re-find row element fresh each time
            # Try multiple methods to find the row, but only in the main grid (not detail grids)
            row_element = None
            
            try:
                # Method 1: Find by ID (fastest if ID is still valid)
                row_element = driver.find_element(By.ID, row_id)
                # Verify it's NOT in a detail grid (rows with detail indicators in their ID are detail rows)
                row_id_attr = row_element.get_attribute('id') or ''
                detail_row_indicators_check = ['grPlacing', 'grNonPlacing', 'dxdt']
                if any(indicator in row_id_attr for indicator in detail_row_indicators_check):
                    raise NoSuchElementException("Row is in detail grid, not main grid")
            except (NoSuchElementException, StaleElementReferenceException):
                # Method 2: Try XPath with main grid context (exclude detail grids)
                try:
                    row_element = driver.find_element(By.XPATH, 
                        f"//table[contains(@id, 'grMaster') and not(contains(@id, 'grPlacing'))]//tr[@id='{row_id}']")
                except (NoSuchElementException, StaleElementReferenceException):
                    # Method 3: Try finding in main grid using alternative selectors
                    try:
                        main_grid = driver.find_element(By.CSS_SELECTOR, "table[id*='grMaster']")
                        row_element = main_grid.find_element(By.XPATH, f".//tr[@id='{row_id}']")
                    except (NoSuchElementException, StaleElementReferenceException):
                        raise NoSuchElementException(f"Could not find row with ID: {row_id} in main grid")
            
            if not row_element:
                raise NoSuchElementException(f"Could not find row with ID: {row_id}")
            
            # Get first cell fresh
            first_cell = row_element.find_element(By.TAG_NAME, "td")
            first_cell_class = first_cell.get_attribute('class') or ''
            
            # Check if this is a detail button cell
            if 'dxgvDetailButton' in first_cell_class:
                # Look for the expand/collapse images
                detail_images = first_cell.find_elements(By.TAG_NAME, "img")
                for img in detail_images:
                    try:
                        img_class = img.get_attribute('class') or ''
                        img_onclick = img.get_attribute('onclick') or ''
                        
                        # Check if already expanded
                        if 'gvDetailExpandedButton' in img_class or 'GVHideDetailRow' in img_onclick:
                            return True  # Already expanded
                        
                        # Check if it's an expand button
                        if 'GVShowDetailRow' in img_onclick or ('gvDetail' in img_class and 'Expanded' not in img_class):
                            driver.execute_script("arguments[0].click();", img)
                            return True
                    except StaleElementReferenceException:
                        # Re-find images if stale
                        detail_images = first_cell.find_elements(By.TAG_NAME, "img")
                        continue
                    except:
                        continue
                
                # If no specific image found, try clicking the first cell
                driver.execute_script("arguments[0].click();", first_cell)
                return True
            
            # Fallback: Try to find expand button in first cell
            expand_images = first_cell.find_elements(By.CSS_SELECTOR, 
                "img[src*='Plus'], img[src*='plus'], img[src*='Expand'], img[src*='expand']")
            expand_links = first_cell.find_elements(By.CSS_SELECTOR, 
                "a.dxgvCommandColumnItem, a[onclick*='Expand'], a[onclick*='expand']")
            expand_buttons = expand_images + expand_links
            
            if expand_buttons:
                driver.execute_script("arguments[0].click();", expand_buttons[0])
                return True
            
            # Last resort: click the first cell directly
            driver.execute_script("arguments[0].click();", first_cell)
            return True
        
        # Retry with aggressive re-finding and early reconnection on timeout
        print_with_timestamp(f"        [EXPAND] Attempting to expand row (ID: {row_id[:50]}...)")
        result = retry_on_stale_element(find_and_click_expand, max_retries=3, delay=sleep_short, reconnect_func=reconnect_func, max_total_time=10, operation_name="expand_row")
        if result is not False:
            print_with_timestamp(f"        [EXPAND] Row expansion successful")
        else:
            print_with_timestamp(f"        [EXPAND] Row expansion failed")
        return result is not False  # Return True if operation succeeded, False otherwise
        
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

def find_and_click_show_row(driver, show_guid, year, show_name, sleep_medium=1):
    """Find and click the show row in the ShowSelector grid to navigate to ClassResults
    
    Args:
        driver: WebDriver instance
        show_guid: ShowGUID to navigate to
        year: Year for navigation context
        show_name: Show name for navigation context
        sleep_medium: Medium sleep duration in seconds (default: 3)
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Wait for grid to load (optimized - use WebDriverWait instead of fixed sleep)
            try:
                WebDriverWait(driver, 3).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']"))
                )
            except:
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
            
            # Find all data rows (re-find each time to avoid stale elements)
            def find_rows(current_grid=None):
                if current_grid is None:
                    current_grid = grid
                try:
                    rows = current_grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                    if not rows:
                        all_rows = current_grid.find_elements(By.TAG_NAME, "tr")
                        rows = []
                        for r in all_rows:
                            try:
                                row_id = r.get_attribute('id') or ''
                                row_class = r.get_attribute('class') or ''
                                if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                    rows.append(r)
                            except StaleElementReferenceException:
                                continue
                    return rows
                except StaleElementReferenceException:
                    # Re-find grid if it's stale
                    try:
                        current_grid = driver.find_element(By.CSS_SELECTOR, 
                            "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                        return find_rows(current_grid)
                    except:
                        return []
            
            rows = find_rows()
            
            # Find the row with matching Show Name
            # Column structure: 0=Command, 1=Date, 2=Name, 3=Location, 4=State, 5=Body
            target_row_index = None
            exact_match_index = None
            partial_matches = []  # Store (index, row_show_name) for partial matches
            
            for idx, row in enumerate(rows):
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:
                        # Show Name is typically at index 2
                        show_name_cell = cells[2] if len(cells) > 2 else cells[1]
                        row_show_name = show_name_cell.text.strip()
                        
                        # Try exact match first (case-insensitive)
                        if show_name and show_name.lower() == row_show_name.lower():
                            exact_match_index = idx
                            target_row_index = idx
                            print_with_timestamp(f"  Found exact matching show row: {row_show_name}")
                            break
                        # Store partial matches for fallback
                        elif show_name and show_name.lower() in row_show_name.lower():
                            partial_matches.append((idx, row_show_name))
                except StaleElementReferenceException:
                    # Re-find rows if they become stale
                    rows = find_rows()
                    continue
                except Exception as e:
                    continue
            
            # If no exact match, try to find the best partial match
            # Prefer matches where the show_name length is closer to the row_show_name length
            if target_row_index is None and partial_matches:
                # Sort by length difference (prefer shorter differences)
                partial_matches.sort(key=lambda x: abs(len(x[1]) - len(show_name)))
                # Use the first (best) match
                target_row_index = partial_matches[0][0]
                print_with_timestamp(f"  Found partial matching show row: {partial_matches[0][1]} (no exact match found)")
            
            if target_row_index is not None:
                try:
                    # Re-find the grid and rows to avoid stale elements
                    grid = driver.find_element(By.CSS_SELECTOR, 
                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                    rows = find_rows()
                    
                    if target_row_index < len(rows):
                        target_row = rows[target_row_index]
                        cells = target_row.find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 3:
                            clickable_cell = cells[2]  # Show Name cell
                            driver.execute_script("arguments[0].click();", clickable_cell)
                            # Wait for navigation (optimized - use WebDriverWait)
                            try:
                                WebDriverWait(driver, 3).until(
                                    lambda d: show_guid.lower() in d.current_url.lower() or 'ClassResults' in d.current_url or 'ShowDetails' in d.current_url
                                )
                            except:
                                time.sleep(sleep_medium)  # Fallback wait
                            
                            # Verify we're on the correct page by checking URL contains ShowGUID
                            current_url = driver.current_url
                            if show_guid.lower() in current_url.lower():
                                print_with_timestamp(f"  [OK] Verified correct show page (ShowGUID in URL)")
                            else:
                                print_with_timestamp(f"  [WARNING] ShowGUID not found in URL after click, using direct navigation")
                                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                                driver.get(class_results_url)
                                # Wait for grid with WebDriverWait instead of fixed sleep
                                try:
                                    WebDriverWait(driver, 6).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                                    )
                                except:
                                    time.sleep(sleep_medium)  # Fallback wait
                                return True
                            
                            # Now click the ClassResults tab on the ShowDetails page (optimized)
                            if activate_class_results_tab(driver, sleep_short=0.5, sleep_medium=1):
                                print_with_timestamp(f"  [OK] Class Results tab activated")
                                return True
                            else:
                                print_with_timestamp(f"  [WARNING] Could not activate Class Results tab, trying direct navigation")
                                # Fallback to direct navigation (optimized)
                                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                                driver.get(class_results_url)
                                # Wait for grid with WebDriverWait instead of fixed sleep
                                try:
                                    WebDriverWait(driver, 6).until(
                                        EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                                    )
                                except:
                                    time.sleep(sleep_medium)  # Fallback wait
                                return True
                except StaleElementReferenceException as e:
                    if attempt < max_retries - 1:
                        print_with_timestamp(f"  [RETRY] Stale element when clicking (attempt {attempt + 1}/{max_retries}), retrying...")
                        time.sleep(0.2)
                        continue
                    else:
                        print_with_timestamp(f"  [WARNING] Stale element when clicking after {max_retries} attempts, trying direct navigation")
                except Exception as e:
                    if attempt < max_retries - 1:
                        print_with_timestamp(f"  [RETRY] Error clicking show row (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                        time.sleep(0.2)
                        continue
                    else:
                        print_with_timestamp(f"  [WARNING] Error clicking show row after {max_retries} attempts: {e}")
            
            # If we get here and haven't returned, break out of retry loop
            break
            
        except StaleElementReferenceException as e:
            if attempt < max_retries - 1:
                print_with_timestamp(f"  [RETRY] Stale element in find_and_click_show_row (attempt {attempt + 1}/{max_retries}), retrying...")
                time.sleep(0.2)
                continue
            else:
                print_with_timestamp(f"  [WARNING] Stale element after {max_retries} attempts, trying direct navigation")
        except Exception as e:
            if attempt < max_retries - 1:
                print_with_timestamp(f"  [RETRY] Error in find_and_click_show_row (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                time.sleep(0.2)
                continue
            else:
                print_with_timestamp(f"  [ERROR] Error finding/clicking show row after {max_retries} attempts: {e}")
    
    # If we couldn't find it by name, try direct navigation (optimized)
    print_with_timestamp(f"  [WARNING] Could not find show row by name '{show_name}', navigating directly to ClassResults")
    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
    driver.get(class_results_url)
    # Wait for grid with WebDriverWait instead of fixed sleep
    try:
        WebDriverWait(driver, 6).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
        )
    except:
        time.sleep(sleep_medium)  # Fallback wait
    return True

def scrape_class_results_for_show(driver, show_list_id, show_guid, year, show_name, conn, show_class_ids=None, sleep_short=0.3, sleep_medium=0.5, sleep_long=1):
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
        # Check if driver session is valid before proceeding
        try:
            current_url = driver.current_url
        except Exception as e:
            print_with_timestamp(f"  [WARNING] Driver session invalid at start, reconnecting...")
            new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
            if new_driver:
                driver = new_driver
            else:
                print_with_timestamp(f"  [ERROR] Failed to reconnect browser, aborting show")
                return 0, driver
        
        # Navigate to ShowSelector page first (optimized)
        show_selector_url = 'https://horseshowsonline.com/ShowSelector.aspx'
        try:
            current_url = driver.current_url
            if 'ShowSelector' not in current_url:
                print_with_timestamp("  Navigating to ShowSelector page...")
                driver.get(show_selector_url)
                # Wait for page to load minimally
                try:
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "li.dxtc-tab, table[id*='grMaster']"))
                    )
                except:
                    time.sleep(sleep_medium)  # Fallback minimal wait
                log_import_activity(conn, 'scrape_class_results.py', action='NAVIGATE', 
                                  additional_info=f'Navigated to ShowSelector page for ShowGUID: {show_guid}')
        except Exception as e:
            print_with_timestamp(f"  [WARNING] Error checking/accessing current URL: {e}, attempting reconnection...")
            new_driver = reconnect_browser_and_navigate(driver, show_guid, year, show_name)
            if new_driver:
                driver = new_driver
                # Try navigation again
                try:
                    driver.get(show_selector_url)
                    WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "li.dxtc-tab, table[id*='grMaster']"))
                    )
                except:
                    time.sleep(sleep_medium)
            else:
                print_with_timestamp(f"  [ERROR] Failed to reconnect browser, aborting show")
                return 0, driver
        
        # Activate Shows By Year tab (optimized - reduced sleeps)
        if not activate_shows_by_year_tab(driver, sleep_medium=0.5, sleep_short=0.2):
            print_with_timestamp(f"  [WARNING] Failed to activate 'Shows By Year' tab, trying direct navigation")
            class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
            driver.get(class_results_url)
            # Wait for grid with WebDriverWait instead of fixed sleep
            try:
                WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                )
            except:
                time.sleep(sleep_long)  # Fallback wait
        else:
            # Select the year (optimized - reduced sleeps)
            if not select_year(driver, year, sleep_short=0.5, sleep_medium=0.8):
                print_with_timestamp(f"  [WARNING] Failed to select year {year}, trying direct navigation")
                class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                driver.get(class_results_url)
                # Wait for grid with WebDriverWait instead of fixed sleep
                try:
                    WebDriverWait(driver, 6).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                    )
                except:
                    time.sleep(sleep_long)  # Fallback wait
            else:
                # Find and click the show row to navigate to ClassResults (optimized - reduced sleeps)
                if not find_and_click_show_row(driver, show_guid, year, show_name, sleep_medium=1):
                    print_with_timestamp(f"  [WARNING] Failed to find show row, trying direct navigation")
                    class_results_url = f'https://horseshowsonline.com/ClassResults?ShowGUID={show_guid}'
                    driver.get(class_results_url)
                    # Wait for grid with WebDriverWait instead of fixed sleep
                    try:
                        WebDriverWait(driver, 6).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
                        )
                    except:
                        time.sleep(sleep_long)  # Fallback wait
        
        # Wait for the ClassResults page to load - look for the grid table (optimized)
        try:
            print_with_timestamp(f"  Waiting for grid table to load (timeout: 15s)...")
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grMaster'], table.dxgvTable"))
            )
            print_with_timestamp(f"  Grid table detected by WebDriverWait")
        except TimeoutException:
            print_with_timestamp(f"  [WARNING] Grid table not found after 15 seconds")
            # Debug: Check what tables are actually on the page
            try:
                all_tables = driver.find_elements(By.TAG_NAME, "table")
                print_with_timestamp(f"  [DEBUG] Found {len(all_tables)} tables on page")
                for i, table in enumerate(all_tables[:5]):  # Show first 5 tables
                    table_id = table.get_attribute('id') or 'no-id'
                    table_class = table.get_attribute('class') or 'no-class'
                    is_displayed = table.is_displayed()
                    tr_count = len(table.find_elements(By.TAG_NAME, "tr"))
                    print_with_timestamp(f"    Table {i+1}: id='{table_id[:60]}...', class='{table_class[:60]}...', displayed={is_displayed}, rows={tr_count}")
            except Exception as e:
                print_with_timestamp(f"  [DEBUG] Error checking page tables: {e}")
        
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
            
            # Build a lookup map: (Class, ClassName) -> (row_index, row_id) (case-insensitive keys)
            grid_lookup = {}  # Key: (class.lower(), class_name.lower()), Value: (row_index (1-based), row_id)
            
            for idx, class_row in enumerate(class_rows, 1):
                def extract_class_info():
                    cells = class_row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 3:
                        return None, None, None
                    
                    # Get row ID
                    row_id = class_row.get_attribute('id') or ''
                    
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
                    
                    return grid_class, grid_class_name, row_id
                
                try:
                    result = retry_on_stale_element(extract_class_info, max_retries=3, delay=sleep_short)
                    if result and result[0] is not None:
                        grid_class, grid_class_name, row_id = result
                        # Use case-insensitive keys for lookup
                        lookup_key = (grid_class.lower(), grid_class_name.lower())
                        grid_lookup[lookup_key] = (idx, row_id)
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
                        lookup_result = grid_lookup.get(lookup_key)
                        
                        if lookup_result:
                            row_index, row_id = lookup_result
                            class_data_list.append((row_index, row_id, show_class_id, entries))
                            print_with_timestamp(f"    Found row {row_index} (ID: {row_id[:50]}...) for Class {class_num}: {class_name[:50]}")
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
                        # Get row ID for reliable lookup (avoids index shifts after expansions)
                        try:
                            row_id = class_row.get_attribute('id') or ''
                            class_data_list.append((row_idx, row_id, show_class_id, entries))
                        except:
                            # If we can't get row ID, fall back to index-only format
                            class_data_list.append((row_idx, None, show_class_id, entries))
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

        # PASS 2: Expand all class rows at once, then extract entry details from all
        print_with_timestamp(f"\n  PASS 2: Extracting entry details...")
        log_import_activity(conn, 'scrape_class_results.py', action='PASS2_START', 
                          additional_info=f'ShowGUID: {show_guid}, ShowListID: {show_list_id}, Classes to process: {len(class_data_list)}')
        
        # Create reconnect function for this show context (closure that captures show context)
        # Note: driver is accessed from outer scope when called, not captured at definition time
        def create_reconnect_func():
            nonlocal driver  # Allow access to outer scope driver variable
            return reconnect_browser_and_navigate(driver, show_guid, year, show_name)
        
        # STEP 1: Expand rows one at a time, extract data, then collapse
        # (Grid only allows one row expanded at a time)
        print_with_timestamp(f"  Step 1: Processing {len(class_data_list)} rows (expand -> extract -> collapse)...")
        row_id_map = {}  # Map row_idx -> class_row_id for later reference
        processed_count = 0
        failed_rows = []  # Track rows that failed to expand for retry
        entry_column_map = None  # Will be set from first placing grid
        nonplacing_column_map = None  # Will be set from first non-placing grid
        
        # Re-find the grid and all rows first (only main grid, not detail grids)
        try:
            # Find the main grid (prefer grMaster, exclude detail grids like grPlacing)
            grid = None
            try:
                # Try to find main grid by XPath (excludes grPlacing)
                grid = driver.find_element(By.XPATH, 
                    "//table[contains(@id, 'grMaster') and not(contains(@id, 'grPlacing'))]")
            except NoSuchElementException:
                # Fallback to CSS selector
                grid = driver.find_element(By.CSS_SELECTOR, 
                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                # Verify it's not a detail grid
                grid_id = grid.get_attribute('id') or ''
                if 'grPlacing' in grid_id:
                    # Try XPath again as fallback
                    grid = driver.find_element(By.XPATH, 
                        "//table[contains(@id, 'grMaster') and not(contains(@id, 'grPlacing'))]")
            
            rows = []
            all_rows = grid.find_elements(By.TAG_NAME, "tr")
            for r in all_rows:
                try:
                    row_id = r.get_attribute('id') or ''
                    row_class = r.get_attribute('class') or ''
                    # Exclude detail rows (containing grPlacing, grNonPlacing, dxdt), header rows, and filter rows
                    detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
                    is_detail_row = any(indicator in row_id for indicator in detail_row_indicators)
                    
                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and \
                       'HeaderRow' not in row_id and 'FilterRow' not in row_id and \
                       not is_detail_row:
                        rows.append(r)
                except StaleElementReferenceException:
                    continue  # Skip stale rows during collection
            
            # Expand all rows in sequence
            for pass2_idx, row_data in enumerate(class_data_list, 1):
                # Handle both old format (row_idx, show_class_id, entries) and new format (row_idx, row_id, show_class_id, entries)
                if len(row_data) == 3:
                    row_idx, show_class_id, entries = row_data
                    stored_row_id = None
                else:
                    row_idx, stored_row_id, show_class_id, entries = row_data
                # Check if driver session is still valid, reconnect if needed
                try:
                    _ = driver.current_url  # Test if session is valid
                except Exception:
                    print_with_timestamp(f"    [WARNING] Driver session invalid, reconnecting...")
                    new_driver = create_reconnect_func()
                    if new_driver:
                        driver = new_driver
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
                    else:
                        print_with_timestamp(f"    [ERROR] Failed to reconnect, skipping remaining rows")
                        break
                
                # Re-find rows before each expansion to avoid stale element references
                # (DOM may have changed from expanding previous rows)
                try:
                    grid = driver.find_element(By.CSS_SELECTOR, 
                        "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                    rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                    if not rows:
                        all_rows = grid.find_elements(By.TAG_NAME, "tr")
                        rows = []
                        for r in all_rows:
                            try:
                                row_id = r.get_attribute('id') or ''
                                row_class = r.get_attribute('class') or ''
                                # Exclude detail rows (containing grPlacing, grNonPlacing, dxdt), header rows, and filter rows
                                detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
                                is_detail_row = any(indicator in row_id for indicator in detail_row_indicators)
                                
                                if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and \
                                   'HeaderRow' not in row_id and 'FilterRow' not in row_id and \
                                   not is_detail_row:
                                    rows.append(r)
                            except StaleElementReferenceException:
                                continue  # Skip stale rows during collection
                except Exception as e:
                    print_with_timestamp(f"    [WARNING] Error re-finding rows before row {row_idx}: {e}")
                    # Try to reconnect and continue
                    try:
                        new_driver = create_reconnect_func()
                        if new_driver:
                            driver = new_driver
                            grid = driver.find_element(By.CSS_SELECTOR, 
                                "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                            rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                            if not rows:
                                all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                rows = []
                                for r in all_rows:
                                    try:
                                        row_id = r.get_attribute('id') or ''
                                        row_class = r.get_attribute('class') or ''
                                        if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and 'HeaderRow' not in row_id and 'FilterRow' not in row_id:
                                            rows.append(r)
                                    except StaleElementReferenceException:
                                        continue
                    except:
                        pass
                
                if row_idx > len(rows):
                    print_with_timestamp(f"    [WARNING] Row {row_idx} no longer available (found {len(rows)} rows), skipping")
                    continue
                
                try:
                    # Re-find the specific row right before use to avoid stale reference
                    class_row = None
                    class_row_id = None
                    max_row_find_retries = 3
                    for find_retry in range(max_row_find_retries):
                        try:
                            # First try to find by stored row ID if available (avoids index shifts after expansions)
                            if stored_row_id:
                                try:
                                    class_row = driver.find_element(By.ID, stored_row_id)
                                    class_row_id = stored_row_id
                                    # Validate it's not a detail row
                                    detail_row_indicators_check = ['grPlacing', 'grNonPlacing', 'dxdt']
                                    is_detail = any(indicator in class_row_id for indicator in detail_row_indicators_check)
                                    if not is_detail:
                                        break  # Successfully found row by ID
                                except:
                                    # Row ID not found (might have been removed/changed), fall through to index lookup
                                    pass
                            
                            # Fallback to index lookup
                            if not class_row_id and row_idx <= len(rows):
                                class_row = rows[row_idx - 1]
                                class_row_id = class_row.get_attribute('id') or ''
                                if class_row_id:
                                    break  # Successfully found row ID
                            
                            # If we got here, row wasn't found or has no ID, re-find rows
                            if find_retry < max_row_find_retries - 1:
                                time.sleep(0.1)
                                grid = driver.find_element(By.CSS_SELECTOR, 
                                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                if not rows:
                                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                    rows = []
                                    for r in all_rows:
                                        try:
                                            row_id = r.get_attribute('id') or ''
                                            row_class = r.get_attribute('class') or ''
                                            # Exclude detail rows (containing grPlacing, grNonPlacing, dxdt), header rows, and filter rows
                                            detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
                                            is_detail_row = any(indicator in row_id for indicator in detail_row_indicators)
                                            
                                            if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and \
                                               'HeaderRow' not in row_id and 'FilterRow' not in row_id and \
                                               not is_detail_row:
                                                rows.append(r)
                                        except StaleElementReferenceException:
                                            continue
                        except StaleElementReferenceException:
                            # Row reference is stale, re-find rows and retry
                            if find_retry < max_row_find_retries - 1:
                                time.sleep(0.1)
                                grid = driver.find_element(By.CSS_SELECTOR, 
                                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                if not rows:
                                    all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                    rows = []
                                    for r in all_rows:
                                        try:
                                            row_id = r.get_attribute('id') or ''
                                            row_class = r.get_attribute('class') or ''
                                            # Exclude detail rows (containing grPlacing, grNonPlacing, dxdt), header rows, and filter rows
                                            detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
                                            is_detail_row = any(indicator in row_id for indicator in detail_row_indicators)
                                            
                                            if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and \
                                               'HeaderRow' not in row_id and 'FilterRow' not in row_id and \
                                               not is_detail_row:
                                                rows.append(r)
                                        except StaleElementReferenceException:
                                            continue
                            continue
                    
                    if not class_row_id:
                        print_with_timestamp(f"    [WARNING] Row {row_idx} has no ID after {max_row_find_retries} retries, skipping")
                        continue
                    
                    # Validate that this is a main row ID, not a detail row ID
                    # Detail rows contain: grPlacing, grNonPlacing, dxdt (detail containers), or are in detail grids
                    detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
                    is_detail_row = any(indicator in class_row_id for indicator in detail_row_indicators)
                    
                    if is_detail_row:
                        print_with_timestamp(f"    [WARNING] Row {row_idx} has detail row ID ({class_row_id[:80]}...), skipping")
                        print_with_timestamp(f"    [DEBUG] Full row ID: {class_row_id}")
                        print_with_timestamp(f"    [DEBUG] Found {len(rows)} rows in grid (after filtering detail rows)")
                        print_with_timestamp(f"    [DEBUG] Looking for row at index {row_idx - 1} in filtered rows array")
                        continue
                    
                    row_id_map[row_idx] = class_row_id
                    
                    # Expand the row with retry logic
                    print_with_timestamp(f"    Expanding row {pass2_idx}/{len(class_data_list)} (row {row_idx})...")
                    row_expanded = False
                    max_expand_retries = 3
                    for expand_retry in range(max_expand_retries):
                        row_expanded = expand_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                        
                        # Check if driver was reconnected during expansion
                        try:
                            _ = driver.current_url  # Test if session is still valid
                        except Exception:
                            print_with_timestamp(f"    [WARNING] Driver session invalid after expansion, reconnecting...")
                            new_driver = create_reconnect_func()
                            if new_driver:
                                driver = new_driver
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
                        
                        if row_expanded:
                            break
                        elif expand_retry < max_expand_retries - 1:
                            print_with_timestamp(f"    [RETRY] Failed to expand row {row_idx}, retrying ({expand_retry + 1}/{max_expand_retries})...")
                            time.sleep(sleep_medium)  # Wait before retry
                            # Re-find the row before retrying
                            try:
                                grid = driver.find_element(By.CSS_SELECTOR, 
                                    "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
                                # Try to find row by ID
                                try:
                                    row_element = driver.find_element(By.ID, class_row_id)
                                    if row_element:
                                        # Row found, continue with retry
                                        pass
                                except:
                                    # Row not found by ID, try to re-find by index
                                    rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                    if not rows:
                                        all_rows = grid.find_elements(By.TAG_NAME, "tr")
                                        rows = []
                                        for r in all_rows:
                                            try:
                                                r_id = r.get_attribute('id') or ''
                                                r_class = r.get_attribute('class') or ''
                                                if ('DataRow' in r_id or 'dxgvDataRow' in r_class) and 'HeaderRow' not in r_id and 'FilterRow' not in r_id:
                                                    rows.append(r)
                                            except:
                                                continue
                            except:
                                pass
                    
                    if not row_expanded:
                        print_with_timestamp(f"    [WARNING] Failed to expand row {row_idx} after {max_expand_retries} attempts")
                        failed_rows.append((row_idx, class_row_id))
                        continue  # Skip to next row if expansion failed
                    
                    # Row is expanded, now extract data immediately (before it gets collapsed by next expansion)
                    print_with_timestamp(f"    [DEBUG] Row {row_idx} expanded successfully, proceeding to extraction...")
                    # Wait for detail grids to appear and load
                    try:
                        # Wait for placing grids to appear near this row
                        WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table[id*='grPlacing']"))
                        )
                        time.sleep(sleep_short)  # Small additional wait after detection
                    except:
                        # If grids don't appear, wait a bit anyway
                        time.sleep(sleep_medium * 2)
                    
                    # Extract data for this single row using JavaScript
                    try:
                        print_with_timestamp(f"    Extracting data for row {row_idx} (class_row_id: {class_row_id[:60]}...)...")
                        row_extracted_data = driver.execute_script("""
                            // Function to extract text from a cell, handling nested elements
                            function getCellText(cell) {
                                if (!cell) return '';
                                var text = '';
                                for (var i = 0; i < cell.childNodes.length; i++) {
                                    var node = cell.childNodes[i];
                                    if (node.nodeType === 3) { // Text node
                                        text += node.textContent.trim();
                                    } else if (node.nodeType === 1 && node.tagName !== 'TABLE') {
                                        var innerText = node.textContent || node.innerText || '';
                                        if (!node.querySelector('table')) {
                                            text += innerText.trim();
                                        }
                                    }
                                }
                                return text.trim() || (cell.textContent || cell.innerText || '').trim();
                            }
                            
                            var classRowId = arguments[0];
                            var result = {
                                rowId: classRowId,
                                placingEntries: [],
                                nonPlacingEntries: [],
                                debug: {rowsSearched: 0, detailContainersFound: 0, placingGridsFound: 0, nonPlacingGridsFound: 0, nextRowIds: []}
                            };
                            
                            // Find the class row
                            var classRow = document.getElementById(classRowId);
                            if (!classRow) {
                                result.debug.error = 'Class row not found by ID: ' + classRowId;
                                return result;
                            }
                            
                            // Find detail containers and grids following this row
                            var allRows = classRow.parentElement.querySelectorAll('tr');
                            var classRowIndex = -1;
                            for (var i = 0; i < allRows.length; i++) {
                                if (allRows[i].id === classRowId) {
                                    classRowIndex = i;
                                    break;
                                }
                            }
                            
                            if (classRowIndex === -1) {
                                result.debug.error = 'Class row index not found';
                                return result;
                            }
                            
                            // Search next 50 rows for detail grids (increased from 20 to handle more complex layouts)
                            for (var j = classRowIndex + 1; j < allRows.length && j < classRowIndex + 51; j++) {
                                result.debug.rowsSearched++;
                                var nextRow = allRows[j];
                                var nextRowId = nextRow.id || '';
                                
                                // Check if this is another class row (stop searching)
                                // A class row has DataRow in ID but not grPlacing/grNonPlacing/dxdt, and has few cells (typically 2-8)
                                if (nextRowId.indexOf('DataRow') !== -1 && nextRowId.indexOf('grPlacing') === -1 && 
                                    nextRowId.indexOf('grNonPlacing') === -1 && nextRowId.indexOf('dxdt') === -1) {
                                    var cells = nextRow.querySelectorAll('td');
                                    // Class rows typically have 2-8 cells (Class, Class Name, Entries, Placings, etc.)
                                    // Detail rows have 10+ cells (Place, Entry, Horse, Rider, etc.)
                                    if (cells.length <= 8) {
                                        break; // This is a new class row, stop searching
                                    }
                                }
                                
                                // Track detail containers
                                if (nextRowId.indexOf('dxdt') !== -1) {
                                    result.debug.detailContainersFound++;
                                    if (result.debug.nextRowIds.length < 5) {
                                        result.debug.nextRowIds.push(nextRowId.substring(0, 80));
                                    }
                                }
                                
                                // Look for placing grids (search recursively in this row and all descendants)
                                var placingGrids = nextRow.querySelectorAll("table[id*='grPlacing']");
                                if (placingGrids.length > 0) {
                                    result.debug.placingGridsFound += placingGrids.length;
                                }
                                for (var pg = 0; pg < placingGrids.length; pg++) {
                                    var placingGrid = placingGrids[pg];
                                    var placingRows = placingGrid.querySelectorAll("tr[id*='DataRow'], tr.dxgvDataRow");
                                    for (var pr = 0; pr < placingRows.length; pr++) {
                                        var placingRow = placingRows[pr];
                                        var prId = placingRow.id || '';
                                        if (prId.indexOf('HeaderRow') === -1 && prId.indexOf('FilterRow') === -1) {
                                            var cells = placingRow.querySelectorAll('td');
                                            if (cells.length >= 10) {
                                                var entryData = {};
                                                for (var c = 0; c < cells.length; c++) {
                                                    entryData['cell_' + c] = getCellText(cells[c]);
                                                }
                                                result.placingEntries.push(entryData);
                                            }
                                        }
                                    }
                                }
                                
                                // Look for non-placing grids
                                // First, explicitly look for grNonPlacing tables
                                var nonPlacingGrids = nextRow.querySelectorAll("table[id*='grNonPlacing']");
                                for (var npg = 0; npg < nonPlacingGrids.length; npg++) {
                                    var npGrid = nonPlacingGrids[npg];
                                    result.debug.nonPlacingGridsFound++;
                                    var tableRows = npGrid.querySelectorAll("tr[id*='DataRow'], tr.dxgvDataRow");
                                    for (var nr = 0; nr < tableRows.length; nr++) {
                                        var nonPlacingRow = tableRows[nr];
                                        var nrId = nonPlacingRow.id || '';
                                        if (nrId.indexOf('HeaderRow') === -1 && nrId.indexOf('FilterRow') === -1) {
                                            var cells = nonPlacingRow.querySelectorAll('td');
                                            if (cells.length >= 6) {
                                                var entryData = {};
                                                for (var c = 0; c < cells.length; c++) {
                                                    entryData['cell_' + c] = getCellText(cells[c]);
                                                }
                                                result.nonPlacingEntries.push(entryData);
                                            }
                                        }
                                    }
                                }
                                
                                // Also look for other tables that might contain non-placing entries
                                // (tables without grPlacing that have rows with 12+ cells)
                                if (result.nonPlacingEntries.length === 0) {
                                    var allTables = nextRow.querySelectorAll('table');
                                    for (var t = 0; t < allTables.length; t++) {
                                        var table = allTables[t];
                                        var tableId = table.id || '';
                                        // Skip placing grids and already processed non-placing grids
                                        if (tableId.indexOf('grPlacing') !== -1 || tableId.indexOf('grNonPlacing') !== -1) {
                                            continue;
                                        }
                                        var tableRows = table.querySelectorAll("tr[id*='DataRow'], tr.dxgvDataRow");
                                        if (tableRows.length > 0) {
                                            var firstRowCells = tableRows[0].querySelectorAll('td');
                                            if (firstRowCells.length >= 12) {
                                                result.debug.nonPlacingGridsFound++;
                                                for (var nr = 0; nr < tableRows.length; nr++) {
                                                    var nonPlacingRow = tableRows[nr];
                                                    var nrId = nonPlacingRow.id || '';
                                                    if (nrId.indexOf('HeaderRow') === -1 && nrId.indexOf('FilterRow') === -1) {
                                                        var cells = nonPlacingRow.querySelectorAll('td');
                                                        if (cells.length >= 12) {
                                                            var entryData = {};
                                                            for (var c = 0; c < cells.length; c++) {
                                                                entryData['cell_' + c] = getCellText(cells[c]);
                                                            }
                                                            result.nonPlacingEntries.push(entryData);
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            return result;
                        """, class_row_id)
                        
                        # Log debug info from JavaScript
                        if isinstance(row_extracted_data, dict) and 'debug' in row_extracted_data:
                            debug_info = row_extracted_data['debug']
                            print_with_timestamp(f"    [DEBUG] JavaScript search: {debug_info.get('rowsSearched', 0)} rows searched, {debug_info.get('detailContainersFound', 0)} detail containers, {debug_info.get('placingGridsFound', 0)} placing grids, {debug_info.get('nonPlacingGridsFound', 0)} non-placing grids")
                            if 'error' in debug_info:
                                print_with_timestamp(f"    [DEBUG] JavaScript error: {debug_info['error']}")
                            if debug_info.get('nextRowIds'):
                                print_with_timestamp(f"    [DEBUG] Sample next row IDs: {debug_info['nextRowIds']}")
                        
                        # Remove debug from extracted data for processing
                        if isinstance(row_extracted_data, dict) and 'debug' in row_extracted_data:
                            row_extracted_data = {k: v for k, v in row_extracted_data.items() if k != 'debug'}
                        
                        # Get column maps from first grid if not already set
                        if not entry_column_map or not nonplacing_column_map:
                            try:
                                placing_grids = driver.find_elements(By.CSS_SELECTOR, "table[id*='grPlacing']")
                                if placing_grids and not entry_column_map:
                                    entry_column_map = get_column_indices_for_entry_grid(placing_grids[0])
                                    if entry_column_map:
                                        print_with_timestamp(f"    [DEBUG] Entry column mapping: {entry_column_map}")
                                
                                # Try to get non-placing column map from a non-placing grid
                                if not nonplacing_column_map:
                                    # Look for a table with 12+ columns that's not a placing grid
                                    all_tables = driver.find_elements(By.CSS_SELECTOR, "table")
                                    for table in all_tables:
                                        table_id = table.get_attribute('id') or ''
                                        if 'grPlacing' not in table_id:
                                            try:
                                                rows = table.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                                if rows:
                                                    cells = rows[0].find_elements(By.TAG_NAME, "td")
                                                    if len(cells) >= 12:
                                                        nonplacing_column_map = get_column_indices_for_nonplacing_grid(table)
                                                        if nonplacing_column_map:
                                                            print_with_timestamp(f"    [DEBUG] Non-placing column mapping: {nonplacing_column_map}")
                                                            break
                                            except:
                                                continue
                            except Exception as e:
                                print_with_timestamp(f"    [WARNING] Error getting column maps: {e}")
                        
                        # Process the extracted data for this row
                        print_with_timestamp(f"    [DEBUG] Extracted data structure: placingEntries={len(row_extracted_data.get('placingEntries', [])) if row_extracted_data else 0}, nonPlacingEntries={len(row_extracted_data.get('nonPlacingEntries', [])) if row_extracted_data else 0}")
                        
                        # Debug: show raw cell data from first placing entry
                        if row_extracted_data and row_extracted_data.get('placingEntries'):
                            first_raw = row_extracted_data['placingEntries'][0]
                            raw_cells = [f"{k}={v[:20] if v else ''}" for k, v in sorted(first_raw.items()) if k.startswith('cell_')][:8]
                            print_with_timestamp(f"    [DEBUG] First placing raw cells: {raw_cells}")
                        
                        # Debug: show raw cell data from first non-placing entry
                        if row_extracted_data and row_extracted_data.get('nonPlacingEntries'):
                            first_raw_np = row_extracted_data['nonPlacingEntries'][0]
                            raw_np_cells = [f"{k}={v[:20] if v else ''}" for k, v in sorted(first_raw_np.items()) if k.startswith('cell_')][:8]
                            print_with_timestamp(f"    [DEBUG] First non-placing raw cells: {raw_np_cells}")
                        
                        # If we have non-placing entries but no column map, try to set it from the extracted data
                        if row_extracted_data and row_extracted_data.get('nonPlacingEntries') and not nonplacing_column_map:
                            print_with_timestamp(f"    [DEBUG] Non-placing entries found but column map missing, attempting to set from extracted data...")
                            # Try to find a non-placing grid on the page to get column mapping
                            try:
                                all_tables = driver.find_elements(By.CSS_SELECTOR, "table")
                                for table in all_tables:
                                    table_id = table.get_attribute('id') or ''
                                    if 'grPlacing' not in table_id:
                                        try:
                                            rows = table.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
                                            if rows:
                                                cells = rows[0].find_elements(By.TAG_NAME, "td")
                                                if len(cells) >= 12:
                                                    nonplacing_column_map = get_column_indices_for_nonplacing_grid(table)
                                                    if nonplacing_column_map:
                                                        print_with_timestamp(f"    [DEBUG] Non-placing column mapping set from grid: {nonplacing_column_map}")
                                                        break
                                        except:
                                            continue
                            except Exception as e:
                                print_with_timestamp(f"    [WARNING] Error setting non-placing column map: {e}")
                        
                        # If still no column map but we have non-placing entries, use default mapping
                        if row_extracted_data and row_extracted_data.get('nonPlacingEntries') and not nonplacing_column_map:
                            print_with_timestamp(f"    [DEBUG] Using default non-placing column mapping (column map not found)")
                            # Use default positional mapping for non-placing entries (12 columns)
                            nonplacing_column_map = {
                                'Entry': 0,
                                'Horse': 1,
                                'Rider': 2,
                                'Country': 3,
                                'Owner': 4,
                                'Trainer': 5,
                                'Prize': 6,
                                'Start': 7,
                                'Score': 8,
                                'Percent': 9,
                                'USEF': 10,
                                'EC': 11,
                                'Place': None,  # Will be set to 0
                                'AddBack': None,  # Will be set to '$0.00'
                            }
                        
                        if row_extracted_data and (row_extracted_data.get('placingEntries') or row_extracted_data.get('nonPlacingEntries')):
                            # Get class details for validation
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
                            
                            # Process placing entries
                            placing_entries = row_extracted_data.get('placingEntries', [])
                            if placing_entries and entry_column_map:
                                # Process and save placing entries (similar to existing code)
                                all_entry_details = []
                                for entry_data in placing_entries:
                                    entry_details = {}
                                    for field, idx in entry_column_map.items():
                                        if idx is not None:
                                            cell_key = f'cell_{idx}'
                                            entry_details[field] = entry_data.get(cell_key, '').strip()
                                        else:
                                            entry_details[field] = ''
                                    if entry_details:
                                        all_entry_details.append(entry_details)
                                
                                # Debug: show first entry to verify column mapping
                                if all_entry_details:
                                    first_entry = all_entry_details[0]
                                    print_with_timestamp(f"    [DEBUG] First placing entry: Place={first_entry.get('Place')}, Entry={first_entry.get('Entry')}, Horse={first_entry.get('Horse', '')[:30]}")
                                
                                if all_entry_details:
                                    saved_entries = 0
                                    skipped_duplicates = 0
                                    cursor = conn.cursor()
                                    try:
                                        for entry_details in all_entry_details:
                                            result = save_show_result_to_database(conn, show_class_id, entry_details, cursor=cursor, commit=False)
                                            if result:
                                                saved_entries += 1
                                                results_count += 1
                                            else:
                                                skipped_duplicates += 1
                                        conn.commit()
                                        print_with_timestamp(f"      Saved {saved_entries}/{len(all_entry_details)} placing entries (skipped {skipped_duplicates} duplicates)")
                                    except Exception as e:
                                        conn.rollback()
                                        print_with_timestamp(f"      [WARNING] Error saving placing entries: {e}")
                                    finally:
                                        cursor.close()
                            
                            # Process non-placing entries
                            if max_entries and max_placings and max_entries > max_placings and not nonplacing_complete:
                                nonplacing_count = max_entries - max_placings
                                nonplacing_entries = row_extracted_data.get('nonPlacingEntries', [])
                                print_with_timestamp(f"    [DEBUG] Non-placing check: max_entries={max_entries}, max_placings={max_placings}, nonplacing_count={nonplacing_count}, nonplacing_complete={nonplacing_complete}")
                                print_with_timestamp(f"    [DEBUG] Non-placing entries found: {len(nonplacing_entries) if nonplacing_entries else 0}, column_map_set={nonplacing_column_map is not None}")
                                if nonplacing_entries:
                                    if not nonplacing_column_map:
                                        print_with_timestamp(f"    [WARNING] Non-placing entries found but column map is missing - cannot process")
                                    else:
                                        # Process and save non-placing entries (similar to existing code)
                                        all_nonplacing_details = []
                                        seen_nonplacing_entries = set()
                                        for entry_data in nonplacing_entries:
                                            entry_details = {}
                                            entry_details['Place'] = '0'
                                            entry_details['AddBack'] = '$0.00'
                                            for field, idx in nonplacing_column_map.items():
                                                if field in ['Place', 'AddBack']:
                                                    continue
                                                if idx is not None:
                                                    cell_key = f'cell_{idx}'
                                                    entry_details[field] = entry_data.get(cell_key, '').strip()
                                                else:
                                                    entry_details[field] = ''
                                            
                                            # Create unique key to avoid duplicates
                                            entry_key = (entry_details.get('Horse', ''), entry_details.get('Rider', ''))
                                            if entry_key not in seen_nonplacing_entries and entry_key[0]:
                                                seen_nonplacing_entries.add(entry_key)
                                                all_nonplacing_details.append(entry_details)
                                        
                                        # Debug: show first non-placing entry to verify column mapping
                                        if all_nonplacing_details:
                                            first_np = all_nonplacing_details[0]
                                            print_with_timestamp(f"    [DEBUG] First non-placing entry: Entry={first_np.get('Entry')}, Horse={first_np.get('Horse', '')[:30]}, Rider={first_np.get('Rider', '')[:30]}")
                                        
                                        if all_nonplacing_details:
                                            saved_nonplacing = 0
                                            skipped_np_duplicates = 0
                                            cursor = conn.cursor()
                                            try:
                                                for entry_details in all_nonplacing_details[:nonplacing_count]:
                                                    result = save_show_result_to_database(conn, show_class_id, entry_details, cursor=cursor, commit=False)
                                                    if result:
                                                        saved_nonplacing += 1
                                                        results_count += 1
                                                    else:
                                                        skipped_np_duplicates += 1
                                                conn.commit()
                                                print_with_timestamp(f"      Saved {saved_nonplacing}/{len(all_nonplacing_details)} non-placing entries (expected: {nonplacing_count}, skipped {skipped_np_duplicates} duplicates)")
                                                
                                                # Mark class as complete if we got all expected entries
                                                # Also mark complete if entries were skipped as duplicates (they already exist)
                                                total_processed = saved_nonplacing + skipped_np_duplicates
                                                if total_processed >= nonplacing_count:
                                                    cursor.execute("""
                                                        UPDATE sResults.ShowClass 
                                                        SET NonPlacingComplete = 1 
                                                        WHERE ID = ?
                                                    """, show_class_id)
                                                    conn.commit()
                                                    if saved_nonplacing > 0:
                                                        print_with_timestamp(f"      [OK] Marked class as complete ({saved_nonplacing} saved, {skipped_np_duplicates} already existed)")
                                                    else:
                                                        print_with_timestamp(f"      [OK] Marked class as complete (all {skipped_np_duplicates} entries already existed)")
                                            except Exception as e:
                                                conn.rollback()
                                                print_with_timestamp(f"      [WARNING] Error saving non-placing entries: {e}")
                                            finally:
                                                cursor.close()
                                else:
                                    if max_entries and max_placings and max_entries > max_placings:
                                        print_with_timestamp(f"    [DEBUG] No non-placing entries extracted (expected {max_entries - max_placings})")
                        
                        # Collapse the row before moving to next
                        try:
                            collapse_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                            time.sleep(sleep_short)  # Small delay after collapse
                        except Exception as e:
                            print_with_timestamp(f"    [WARNING] Error collapsing row {row_idx}: {e}")
                            # Continue anyway
                        
                        # Only increment processed_count after successful extraction and collapse
                        processed_count += 1
                    
                    except Exception as e:
                        print_with_timestamp(f"    [WARNING] Error extracting data for row {row_idx}: {e}")
                        import traceback
                        traceback.print_exc()
                        # Try to collapse anyway
                        try:
                            collapse_row(driver, class_row_id, reconnect_func=create_reconnect_func)
                        except:
                            pass
                
                except Exception as e:
                    print_with_timestamp(f"    [WARNING] Error expanding row {row_idx}: {e}")
                    # Check if error was due to invalid session
                    try:
                        _ = driver.current_url
                    except Exception:
                        print_with_timestamp(f"    [WARNING] Driver session invalid after error, reconnecting...")
                        new_driver = create_reconnect_func()
                        if new_driver:
                            driver = new_driver
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
                    continue
            
            print_with_timestamp(f"  [OK] Processed {processed_count}/{len(class_data_list)} rows")
            
        except Exception as e:
            print_with_timestamp(f"  [ERROR] Error during row processing: {e}")
            import traceback
            traceback.print_exc()
        
        # All rows have been processed (expand -> extract -> collapse)
        # No further processing needed
        
        # STEP 3: Optional cleanup - collapse any remaining expanded rows
        # (Most rows should already be collapsed, but this is a safety measure)
        # STEP 3: Collapse all rows at once (optional cleanup)
        print_with_timestamp(f"  Step 3: Collapsing all expanded rows...")
        collapsed_count = 0
        try:
            # Check if driver session is still valid before collapsing
            try:
                _ = driver.current_url  # Test if session is valid
            except Exception:
                print_with_timestamp(f"  [WARNING] Driver session invalid before collapse, reconnecting...")
                new_driver = create_reconnect_func()
                if new_driver:
                    driver = new_driver
                else:
                    print_with_timestamp(f"  [WARNING] Failed to reconnect, skipping collapse")
                    return results_count, driver
            
            grid = driver.find_element(By.CSS_SELECTOR, 
                "table[id*='grMaster'], table.dxgvTable, table[id*='DXMainTable']")
            rows = grid.find_elements(By.CSS_SELECTOR, "tr[id*='DataRow']")
            if not rows:
                all_rows = grid.find_elements(By.TAG_NAME, "tr")
                rows = []
                for r in all_rows:
                    row_id = r.get_attribute('id') or ''
                    row_class = r.get_attribute('class') or ''
                    # Exclude detail rows (containing grPlacing, grNonPlacing, dxdt), header rows, and filter rows
                    detail_row_indicators = ['grPlacing', 'grNonPlacing', 'dxdt']
                    is_detail_row = any(indicator in row_id for indicator in detail_row_indicators)
                    
                    if ('DataRow' in row_id or 'dxgvDataRow' in row_class) and \
                       'HeaderRow' not in row_id and 'FilterRow' not in row_id and \
                       not is_detail_row:
                        rows.append(r)
            
            for row_idx, class_row_id in row_id_map.items():
                try:
                    if collapse_row(driver, class_row_id, reconnect_func=create_reconnect_func):
                        collapsed_count += 1
                except Exception as e:
                    print_with_timestamp(f"    [WARNING] Could not collapse row {row_idx}: {e}")
                    continue
            
            print_with_timestamp(f"  [OK] Collapsed {collapsed_count}/{len(row_id_map)} rows")
        except Exception as e:
            print_with_timestamp(f"  [WARNING] Error during bulk collapse: {e}")
        
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

def main(skip_processed=True, load_missing_classes=False, start_from_show_guid=None, single_show_guid=None, sleep_short=0.5, sleep_medium=1):
    """Main function to scrape class results
    
    Args:
        skip_processed: If True, skip shows that already have ShowClass or ShowResults data (default: True)
        load_missing_classes: If True, load only classes with Placings > 0 that don't have ShowResults (default: False)
        start_from_show_guid: Optional ShowGUID to start from (only processes ShowListID >= that ShowGUID's ID)
        single_show_guid: Optional ShowGUID to load only that specific show
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
                          additional_info=f'skip_processed={skip_processed}, load_missing_classes={load_missing_classes}, start_from_show_guid={start_from_show_guid}, single_show_guid={single_show_guid}')
        
        # Get ShowGUIDs, Years, and ShowNames from database
        if load_missing_classes:
            print_with_timestamp("Fetching shows with missing class results...")
            show_data_list = get_shows_with_missing_classes(conn, start_from_show_guid=start_from_show_guid, single_show_guid=single_show_guid)
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
            show_data_list = get_show_data_from_database(conn, skip_processed=skip_processed, start_from_show_guid=start_from_show_guid, single_show_guid=single_show_guid)
            print_with_timestamp(f"[OK] Found {len(show_data_list)} shows\n")
            
            if not show_data_list:
                print_with_timestamp("[WARNING] No ShowGUIDs found in database. Please run scrape_shows_by_year.py first.")
                return
            
            # Scrape results for each show
            total_results = 0
            for idx, (show_list_id, show_guid, year, show_name) in enumerate(show_data_list, 1):
                print_with_timestamp(f"\nProcessing show {idx}/{len(show_data_list)}...")
                
                # When loading a single show with --show-guid, always only load classes where results are missing
                incomplete_class_ids = None
                if single_show_guid:
                    # First check if any classes exist for this show
                    cursor_check = conn.cursor()
                    cursor_check.execute("""
                        SELECT COUNT(*) 
                        FROM sResults.ShowClass 
                        WHERE ShowListID = ?
                    """, show_list_id)
                    total_classes = cursor_check.fetchone()[0]
                    cursor_check.close()
                    
                    if total_classes == 0:
                        # No classes loaded yet - need to run PASS 1 to load classes
                        print_with_timestamp(f"  [INFO] No classes found in database for this show")
                        print_with_timestamp(f"  [INFO] Will load classes from website (PASS 1) and then collect results")
                        # incomplete_class_ids remains None, so PASS 1 will run
                    else:
                        # Classes exist - check for incomplete classes
                        print_with_timestamp(f"  Checking for classes with missing results...")
                        incomplete_class_ids = get_incomplete_classes_for_show(conn, show_list_id, skip_processed=True)
                        
                        if incomplete_class_ids:
                            print_with_timestamp(f"  [RESUME] Found {len(incomplete_class_ids)} classes with missing results")
                            print_with_timestamp(f"  [RESUME] Will process only classes with missing results (skipping already completed classes)")
                        else:
                            # All classes are complete
                            print_with_timestamp(f"  [INFO] All {total_classes} classes have complete results. No missing results to process.")
                            print_with_timestamp(f"  Skipping show (all classes complete)")
                            continue
                
                # Pass incomplete_class_ids to scrape function to resume from where left off
                results_count, driver = scrape_class_results_for_show(
                    driver, show_list_id, show_guid, year, show_name, conn, 
                    show_class_ids=incomplete_class_ids, 
                    sleep_short=sleep_short, sleep_medium=sleep_medium
                )
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
            try:
                log_import_activity(conn, 'scrape_class_results.py', action='INTERRUPTED', 
                                  error_detail='User interrupted scraping')
            except:
                pass
        # Explicitly terminate browser on interrupt
        if driver:
            try:
                print_with_timestamp("\nTerminating browser session...")
                driver.quit()
            except Exception as e:
                print_with_timestamp(f"[WARNING] Error terminating browser: {e}")
                # Try to force kill if normal quit fails
                try:
                    if hasattr(driver, 'service') and hasattr(driver.service, 'process'):
                        driver.service.process.kill()
                except:
                    pass
    except Exception as e:
        print_with_timestamp(f"\n[ERROR] Fatal Error: {e}")
        import traceback
        error_trace = traceback.format_exc()
        if conn:
            try:
                log_import_activity(conn, 'scrape_class_results.py', action='ERROR', 
                                  error_detail=str(e), additional_info=error_trace[:4000])  # Limit to 4000 chars
            except:
                pass
        traceback.print_exc()
    finally:
        if conn:
            try:
                conn.close()
                print_with_timestamp("[OK] Database connection closed")
            except:
                pass
        if driver:
            try:
                print_with_timestamp("\nClosing browser...")
                driver.quit()
            except Exception as e:
                print_with_timestamp(f"[WARNING] Error closing browser in finally: {e}")
                # Try to force kill if normal quit fails
                try:
                    if hasattr(driver, 'service') and hasattr(driver.service, 'process'):
                        driver.service.process.kill()
                except:
                    pass

if __name__ == '__main__':
    import sys
    
    # Check for command-line arguments
    skip_processed = True
    load_missing_classes = False
    start_from_show_guid = None
    single_show_guid = None
    
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
        elif arg_lower in ['--show-guid', '--single-show', '-g']:
            if i + 1 < len(sys.argv):
                single_show_guid = sys.argv[i + 1]
                print_with_timestamp(f"[INFO] Command-line argument detected: Will load single show: ShowGUID {single_show_guid}")
                i += 1  # Skip the next argument as it's the ShowGUID value
            else:
                print_with_timestamp("[ERROR] --show-guid requires a ShowGUID value")
                sys.exit(1)
        elif arg_lower in ['--help', '-h']:
            print_with_timestamp("Usage: python scrape_class_results.py [OPTIONS]")
            print_with_timestamp("Options:")
            print_with_timestamp("  --process-all, -a, --all: Process all shows, including those with existing ShowClass or ShowResults data")
            print_with_timestamp("  --load-missing, -m, --missing: Load only missing class results (classes with Placings > 0 that don't have ShowResults)")
            print_with_timestamp("  --start-from SHOWGUID, -s SHOWGUID: Start processing from the specified ShowGUID (only processes ShowListID >= that ShowGUID's ID)")
            print_with_timestamp("  --show-guid SHOWGUID, --single-show SHOWGUID, -g SHOWGUID: Load only the specified show by ShowGUID")
            print_with_timestamp("  Default: Skip shows with existing data")
            sys.exit(0)
        
        i += 1
    
    # Validate mutually exclusive parameters
    if single_show_guid and start_from_show_guid:
        print_with_timestamp("[ERROR] --show-guid and --start-from cannot be used together")
        sys.exit(1)
    
    # load_missing_classes takes precedence over skip_processed
    if load_missing_classes:
        skip_processed = False
    
    main(skip_processed=skip_processed, load_missing_classes=load_missing_classes, start_from_show_guid=start_from_show_guid, single_show_guid=single_show_guid, sleep_short=0.5, sleep_medium=1)

