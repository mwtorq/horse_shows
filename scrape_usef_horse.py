"""
Scraper to search for horses on USEF website and extract their information
Navigates to https://www.usef.org/search/horses
Handles authentication if required
Searches for a horse by Name and Owner LastName
Extracts and updates horse information in database
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from urllib3.exceptions import ReadTimeoutError, MaxRetryError, NewConnectionError
import time
import getpass
import re
import urllib.parse
import pyodbc
from datetime import datetime

def print_with_timestamp(message, end='\n'):
    """Print message with timestamp prefix"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if message.startswith('\n'):
        leading_newlines = 0
        for char in message:
            if char == '\n':
                leading_newlines += 1
            else:
                break
        print('\n' * leading_newlines, end='')
        remaining_message = message[leading_newlines:]
        print(f"[{timestamp}] {remaining_message}", end=end)
    else:
        print(f"[{timestamp}] {message}", end=end)

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

def check_and_authenticate(driver, url, sleep_short=2, sleep_medium=3, username=None, password=None):
    """Check if authentication is required and handle login if needed
    
    Args:
        driver: WebDriver instance
        url: URL to navigate to
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
        username: Optional username to use (if None, will prompt)
        password: Optional password to use (if None, will prompt)
    
    Returns:
        Tuple of (True/False, username, password) - True if authenticated or not required, False if authentication failed
    """
    print_with_timestamp(f"Navigating to {url}...")
    driver.get(url)
    time.sleep(sleep_medium)
    
    # FIRST: Handle cookie banner if present (login link appears after accepting cookies)
    print_with_timestamp("  Checking for cookie banner...")
    cookie_accepted = False
    try:
        # Look for common cookie accept buttons (CybotCookiebot is the cookie banner system)
        cookie_selectors = [
            "//button[@id='CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']",
            "//button[contains(@id, 'CybotCookiebot') and contains(@id, 'Allow')]",
            "//button[contains(text(), 'Accept All') or contains(text(), 'Accept')]",
            "//button[contains(text(), 'I Accept')]",
            "//a[contains(text(), 'Accept')]",
            "//button[contains(@class, 'cookie') and contains(@class, 'accept')]",
            "//*[@id='CybotCookiebotDialogBody']//button[contains(text(), 'Accept')]",
        ]
        
        for selector in cookie_selectors:
            try:
                cookie_buttons = driver.find_elements(By.XPATH, selector)
                for cookie_button in cookie_buttons:
                    try:
                        if cookie_button.is_displayed():
                            print_with_timestamp(f"  Found cookie accept button, clicking...")
                            driver.execute_script("arguments[0].click();", cookie_button)
                            time.sleep(sleep_short)
                            cookie_accepted = True
                            print_with_timestamp("  Cookies accepted")
                            break
                    except:
                        continue
                if cookie_accepted:
                    break
            except:
                continue
    except Exception as e:
        print_with_timestamp(f"  [DEBUG] Error handling cookies: {e}")
    
    # Wait a moment after accepting cookies for page to update
    if cookie_accepted:
        time.sleep(sleep_short)
    
    # Check for common login indicators
    login_indicators = [
        "//input[@type='password']",
        "//input[@name='password' or @id='password' or @name='Password' or @id='Password']",
        "//form[contains(@action, 'login') or contains(@action, 'Login')]",
        "//a[contains(text(), 'Login') or contains(text(), 'Sign In') or contains(text(), 'Log in')]",
        "//button[contains(text(), 'Login') or contains(text(), 'Sign In')]"
    ]
    
    needs_login = False
    login_form = None
    login_link = None
    
    # Check for password field (strongest indicator)
    try:
        password_field = driver.find_element(By.XPATH, "//input[@type='password']")
        if password_field.is_displayed():
            needs_login = True
            print_with_timestamp("  Authentication required - password field found")
    except NoSuchElementException:
        pass
    
    # Check for login form
    if not needs_login:
        try:
            login_form = driver.find_element(By.XPATH, "//form[contains(@action, 'login') or contains(@action, 'Login')]")
            if login_form.is_displayed():
                needs_login = True
                print_with_timestamp("  Authentication required - login form found")
        except NoSuchElementException:
            pass
    
    # Always check for login link (must click this first to reveal login form)
    # The page might have a login link even if no password field is visible yet
    login_link_found = None
    print_with_timestamp("  Checking for Log In link...")
    
    login_link_selectors = [
        "//a[contains(text(), 'Log In')]",
        "//a[normalize-space(text())='Log In']",
        "//a[contains(text(), 'Login')]",
        "//a[contains(text(), 'Sign In')]",
        "//a[contains(text(), 'Log in')]",
        "//a[contains(@href, 'login') or contains(@href, 'Login') or contains(@href, 'signin')]",
        "//button[contains(text(), 'Log In')]",
        "//button[contains(text(), 'Login')]",
        "//button[contains(text(), 'Sign In')]",
    ]
    
    for selector in login_link_selectors:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            for elem in elements:
                try:
                    if elem.is_displayed():
                        login_link_found = elem
                        link_text = elem.text.strip()
                        print_with_timestamp(f"  Found Log In link: '{link_text}'")
                        needs_login = True
                        break
                except:
                    continue
            if login_link_found:
                break
        except:
            continue
    
    # Also check for "Already have an account?" text which often precedes login links
    if not login_link_found:
        try:
            account_text = driver.find_elements(By.XPATH, "//*[contains(text(), 'Already have an account') or contains(text(), 'already have an account')]")
            if account_text:
                print_with_timestamp("  Found 'Already have an account?' text, looking for nearby Log In link...")
                for text_elem in account_text:
                    try:
                        # Look for login link near this text (following sibling or nearby)
                        nearby_links = text_elem.find_elements(By.XPATH, "./following::a[contains(text(), 'Log') or contains(text(), 'Sign')]")
                        for link in nearby_links:
                            try:
                                if link.is_displayed():
                                    login_link_found = link
                                    link_text = link.text.strip()
                                    print_with_timestamp(f"  Found Log In link near 'Already have an account?' text: '{link_text}'")
                                    needs_login = True
                                    break
                            except:
                                continue
                        if login_link_found:
                            break
                    except:
                        continue
        except Exception as e:
            print_with_timestamp(f"  [DEBUG] Error searching for login link near account text: {e}")
    
    if not needs_login and not login_link_found:
        print_with_timestamp("  No authentication required")
        return True, username, password
    
    # If we found a login link, click it first to reveal the login form
    if login_link_found:
        try:
            print_with_timestamp("  Clicking Log In link...")
            # Scroll into view first
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_link_found)
            time.sleep(0.3)  # Reduced wait
            # Try JavaScript click first
            driver.execute_script("arguments[0].click();", login_link_found)
            print_with_timestamp("  Log In link clicked via JavaScript")
            # Wait for login form to appear with WebDriverWait (faster, with timeout)
            try:
                WebDriverWait(driver, 5).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.XPATH, "//input[@type='password']")),
                        EC.presence_of_element_located((By.XPATH, "//input[@name='password' or @id='password']"))
                    )
                )
                print_with_timestamp("  Login form appeared")
            except TimeoutException:
                print_with_timestamp("  [WARNING] Login form not found after wait, continuing anyway...")
                time.sleep(1)  # Fallback short wait
        except Exception as e:
            print_with_timestamp(f"  [WARNING] Error clicking login link with JavaScript: {e}, trying normal click...")
            try:
                login_link_found.click()
                print_with_timestamp("  Log In link clicked via normal click")
                # Wait for login form with WebDriverWait
                try:
                    WebDriverWait(driver, 5).until(
                        EC.any_of(
                            EC.presence_of_element_located((By.XPATH, "//input[@type='password']")),
                            EC.presence_of_element_located((By.XPATH, "//input[@name='password' or @id='password']"))
                        )
                    )
                    print_with_timestamp("  Login form appeared")
                except TimeoutException:
                    time.sleep(1)  # Fallback short wait
            except Exception as e2:
                print_with_timestamp(f"  [ERROR] Error clicking login link: {e2}")
                return False, None, None
    
    # Prompt for credentials if not provided
    if not username or not password:
        print_with_timestamp("\n  Authentication required. Please enter credentials:")
        username = input("  Username/Email: ").strip()
        password = getpass.getpass("  Password: ").strip()
        
        if not username or not password:
            print_with_timestamp("  [ERROR] Username and password are required")
            return False, None, None
    else:
        print_with_timestamp("\n  Re-authenticating with stored credentials...")
    
    # Wait a moment for login form to appear (if we clicked a link) - already waited above
    # No additional wait needed
    
    # Try to find and fill login form
    try:
        # Try to find username/email field
        username_field = None
        username_selectors = [
            (By.ID, "username"),
            (By.ID, "email"),
            (By.NAME, "username"),
            (By.NAME, "email"),
            (By.NAME, "user"),
            (By.XPATH, "//input[@type='email']"),
            (By.XPATH, "//input[@type='text' and (@name='username' or @name='email' or @name='user')]")
        ]
        
        for by, value in username_selectors:
            try:
                username_field = driver.find_element(by, value)
                if username_field.is_displayed():
                    break
            except NoSuchElementException:
                continue
        
        if not username_field:
            # Try to find first text input before password field
            try:
                password_field = driver.find_element(By.XPATH, "//input[@type='password']")
                username_field = password_field.find_element(By.XPATH, "./preceding::input[@type='text' or @type='email'][1]")
            except:
                pass
        
        if username_field:
            username_field.clear()
            username_field.send_keys(username)
            print_with_timestamp("  Entered username")
        else:
            print_with_timestamp("  [WARNING] Could not find username field, trying to continue...")
        
        # Find and fill password field
        password_field = driver.find_element(By.XPATH, "//input[@type='password']")
        password_field.clear()
        password_field.send_keys(password)
        print_with_timestamp("  Entered password")
        
        # Find and click login/submit button
        submit_button = None
        submit_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//input[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Login') or contains(text(), 'Sign In') or contains(text(), 'Log in')]"),
            (By.XPATH, "//button[contains(text(), 'Submit')]"),
            (By.XPATH, "//input[@value='Login' or @value='Sign In' or @value='Log in' or @value='Submit']")
        ]
        
        for by, value in submit_selectors:
            try:
                submit_button = driver.find_element(by, value)
                if submit_button.is_displayed():
                    break
            except NoSuchElementException:
                continue
        
        if submit_button:
            submit_button.click()
            print_with_timestamp("  Clicked login button")
            # Wait for login to complete (check if password field disappears or URL changes)
            try:
                WebDriverWait(driver, 5).until(
                    EC.any_of(
                        lambda d: "password" not in d.current_url.lower(),
                        EC.invisibility_of_element_located((By.XPATH, "//input[@type='password']"))
                    )
                )
                print_with_timestamp("  [OK] Login appears successful")
                time.sleep(0.5)  # Brief wait for page to settle
                return True, username, password
            except TimeoutException:
                # Check if password field is still visible (login failed)
                try:
                    driver.find_element(By.XPATH, "//input[@type='password']")
                    print_with_timestamp("  [WARNING] Login may have failed - password field still visible")
                    return False, username, password
                except NoSuchElementException:
                    print_with_timestamp("  [OK] Login appears successful (password field not found)")
                    return True, username, password
        else:
            print_with_timestamp("  [ERROR] Could not find login/submit button")
            return False, username, password
            
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error during authentication: {e}")
        return False, username, password

def reconnect_browser_and_authenticate(old_driver, search_url, auth_username, auth_password, headless=True):
    """Reconnect browser by quitting old session and creating new one, then re-authenticate
    
    Args:
        old_driver: Current WebDriver instance (will be quit)
        search_url: URL to navigate to after reconnection
        auth_username: Username for authentication
        auth_password: Password for authentication
        headless: Run browser in headless mode (default: True)
    
    Returns:
        New WebDriver instance if successful, None otherwise
    """
    print_with_timestamp("  [RECONNECT] Quitting hung browser session...")
    try:
        # Try to quit gracefully with a timeout
        import threading
        
        quit_success = [False]
        quit_error = [None]
        
        def quit_driver():
            try:
                old_driver.quit()
                quit_success[0] = True
            except Exception as e:
                quit_error[0] = e
        
        quit_thread = threading.Thread(target=quit_driver)
        quit_thread.daemon = True
        quit_thread.start()
        quit_thread.join(timeout=5)  # Wait max 5 seconds for quit
        
        if not quit_success[0]:
            print_with_timestamp("  [RECONNECT] Browser quit timed out or failed, trying to kill process...")
            try:
                # Try to kill the browser process directly
                if hasattr(old_driver, 'service') and hasattr(old_driver.service, 'process'):
                    old_driver.service.process.kill()
                    print_with_timestamp("  [RECONNECT] Browser process killed")
            except Exception as kill_error:
                print_with_timestamp(f"  [RECONNECT] Could not kill browser process: {kill_error}")
                if quit_error[0]:
                    print_with_timestamp(f"  [RECONNECT] Original quit error: {quit_error[0]}")
    except Exception as e:
        print_with_timestamp(f"  [RECONNECT] Error quitting old browser: {e}, continuing anyway...")
        pass
    
    # Small delay to ensure process cleanup
    time.sleep(1)
    
    print_with_timestamp("  [RECONNECT] Creating new browser session...")
    try:
        new_driver = setup_driver(headless=headless)
        print_with_timestamp("  [RECONNECT] New browser session created")
        
        # Re-authenticate with stored credentials
        print_with_timestamp("  [RECONNECT] Re-authenticating with stored credentials...")
        try:
            auth_success, _, _ = check_and_authenticate(new_driver, search_url, username=auth_username, password=auth_password)
            
            if auth_success:
                print_with_timestamp("  [RECONNECT] Re-authentication successful")
                return new_driver
            else:
                print_with_timestamp("  [RECONNECT] Re-authentication failed")
                try:
                    new_driver.quit()
                except:
                    pass
                return None
        except (ReadTimeoutError, MaxRetryError, TimeoutError, NewConnectionError) as auth_timeout:
            print_with_timestamp(f"  [RECONNECT] Timeout/connection error during re-authentication: {auth_timeout}")
            print_with_timestamp("  [RECONNECT] Retrying authentication after brief delay...")
            try:
                # Wait a moment and try one more time
                time.sleep(2)
                auth_success, _, _ = check_and_authenticate(new_driver, search_url, username=auth_username, password=auth_password)
                if auth_success:
                    print_with_timestamp("  [RECONNECT] Re-authentication successful on retry")
                    return new_driver
                else:
                    print_with_timestamp("  [RECONNECT] Re-authentication failed on retry")
                    try:
                        new_driver.quit()
                    except:
                        pass
                    return None
            except Exception as retry_error:
                print_with_timestamp(f"  [RECONNECT] Re-authentication retry also failed: {retry_error}")
                try:
                    new_driver.quit()
                except:
                    pass
                return None
    except Exception as e:
        print_with_timestamp(f"  [RECONNECT] Error creating new browser session: {e}")
        import traceback
        traceback.print_exc()
        return None

def search_horse(driver, horse_name, owner_last_name=None, sleep_short=2, sleep_medium=3, retry_auth=None, headless=True):
    """Search for a horse by name and optionally owner last name
    
    Args:
        driver: WebDriver instance (may be replaced if reconnection occurs)
        horse_name: Horse name to search for
        owner_last_name: Optional owner last name to search for (if None, searches by horse name only)
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
        retry_auth: Optional tuple of (url, username, password) for re-authentication on timeout
        headless: Run browser in headless mode (default: True)
    
    Returns:
        Tuple of (success: bool, new_driver: WebDriver or None). If reconnection occurred, new_driver will be the new instance.
    """
    print_with_timestamp(f"\nSearching for horse: {horse_name} (Owner: {owner_last_name})...")
    
    try:
        # Wait for page to load (reduced time)
        time.sleep(1)
        
        # Handle cookie banner if present (with timeout)
        try:
            cookie_selectors = [
                "//button[@id='CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']",
                "//button[contains(text(), 'Accept All') or contains(text(), 'Accept')]",
                "//button[contains(text(), 'I Accept')]",
            ]
            for selector in cookie_selectors:
                try:
                    cookie_button = WebDriverWait(driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                    if cookie_button.is_displayed():
                        driver.execute_script("arguments[0].click();", cookie_button)
                        print_with_timestamp("  Accepted cookies")
                        time.sleep(0.5)  # Reduced wait
                        break
                except:
                    continue
        except:
            pass
        
        # Wait a bit more for page to fully render (reduced time)
        time.sleep(0.5)
        
        # Ensure we're on the correct page
        current_url = driver.current_url
        if 'search/horses' not in current_url.lower():
            print_with_timestamp(f"  [WARNING] Not on horses search page (current: {current_url}), navigating...")
            search_url = "https://www.usef.org/search/horses"
            driver.get(search_url)
            time.sleep(sleep_medium)
            # Handle cookie banner again
            try:
                cookie_selectors = [
                    "//button[@id='CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']",
                    "//button[contains(text(), 'Accept All') or contains(text(), 'Accept')]",
                ]
                for selector in cookie_selectors:
                    try:
                        cookie_button = driver.find_element(By.XPATH, selector)
                        if cookie_button.is_displayed():
                            driver.execute_script("arguments[0].click();", cookie_button)
                            time.sleep(sleep_short)
                            break
                    except:
                        continue
            except:
                pass
        
        # Wait for form fields to be visible (they might load dynamically) - reduced timeout
        try:
            # Look for "Horse Name" label or field
            WebDriverWait(driver, 5).until(
                EC.any_of(
                    EC.presence_of_element_located((By.XPATH, "//label[contains(text(), 'Horse Name')]")),
                    EC.presence_of_element_located((By.XPATH, "//input[contains(@name, 'HorseName') or contains(@id, 'HorseName')]")),
                    EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Horse Name')]")),
                    EC.presence_of_element_located((By.ID, "Name")),
                    EC.presence_of_element_located((By.NAME, "Name"))
                )
            )
            print_with_timestamp("  Form fields loaded")
        except TimeoutException:
            print_with_timestamp("  [WARNING] Form fields not found after wait, continuing anyway...")
        
        # Find Horse Name field with comprehensive selectors
        name_field = None
        name_selectors = [
            (By.XPATH, "//label[contains(text(), 'Horse Name')]/following::input[1]"),
            (By.XPATH, "//label[contains(text(), 'Horse Name')]/ancestor::div[1]//input"),
            (By.XPATH, "//input[contains(@name, 'HorseName') or contains(@id, 'HorseName')]"),
            (By.XPATH, "//input[contains(@placeholder, 'Horse Name')]"),
            (By.ID, "Name"),  # Fallback to Name
            (By.NAME, "Name"),  # Fallback to Name
            (By.XPATH, "//input[@id='Name' or @name='Name']"),
            (By.XPATH, "//input[contains(@placeholder, 'Name') or contains(@placeholder, 'name')]"),
            (By.XPATH, "//input[contains(@name, 'name') or contains(@id, 'name')]"),
        ]
        
        for by, value in name_selectors:
            try:
                elements = driver.find_elements(by, value)
                for elem in elements:
                    if elem.is_displayed() and elem.get_attribute('type') in [None, 'text', 'search']:
                        name_field = elem
                        print_with_timestamp(f"  Found Name field using: {by}={value}")
                        break
                if name_field:
                    break
            except Exception as e:
                continue
        
        # Try JavaScript as fallback
        if not name_field:
            try:
                # Try to find field by label text "Horse Name"
                name_field = driver.execute_script("""
                    var labels = document.querySelectorAll('label');
                    for (var i = 0; i < labels.length; i++) {
                        if (labels[i].textContent && labels[i].textContent.includes('Horse Name')) {
                            var input = labels[i].querySelector('input') || 
                                       labels[i].nextElementSibling || 
                                       document.querySelector('input[name*="HorseName" i], input[id*="HorseName" i]');
                            if (input) return input;
                        }
                    }
                    return document.getElementById('Name') || document.querySelector('input[name="Name"]');
                """)
                if name_field:
                    print_with_timestamp("  Found Horse Name field via JavaScript")
            except Exception as e:
                print_with_timestamp(f"  [DEBUG] JavaScript fallback error: {e}")
                pass
        
        if not name_field:
            print_with_timestamp("  [ERROR] Could not find Name field after all attempts")
            # Debug: Print page title and URL
            try:
                print_with_timestamp(f"  [DEBUG] Page title: {driver.title}")
                print_with_timestamp(f"  [DEBUG] Current URL: {driver.current_url}")
                # List all input fields
                all_inputs = driver.find_elements(By.TAG_NAME, "input")
                print_with_timestamp(f"  [DEBUG] Found {len(all_inputs)} input fields on page")
                for i, inp in enumerate(all_inputs[:10]):  # Print first 10
                    try:
                        inp_id = inp.get_attribute('id') or 'no-id'
                        inp_name = inp.get_attribute('name') or 'no-name'
                        inp_type = inp.get_attribute('type') or 'no-type'
                        print_with_timestamp(f"    Input {i+1}: id='{inp_id}', name='{inp_name}', type='{inp_type}'")
                    except:
                        pass
            except:
                pass
            return False, None
        
        # Find Owner Last Name/Farm Name field (only if owner_last_name is provided)
        owner_last_name_field = None
        if owner_last_name:
            owner_selectors = [
                (By.XPATH, "//label[contains(text(), 'Owner Last Name') or contains(text(), 'Farm Name')]/following::input[1]"),
                (By.XPATH, "//label[contains(text(), 'Owner Last Name') or contains(text(), 'Farm Name')]/ancestor::div[1]//input"),
                (By.XPATH, "//input[contains(@name, 'OwnerLastName') or contains(@id, 'OwnerLastName')]"),
                (By.XPATH, "//input[contains(@placeholder, 'Owner Last Name') or contains(@placeholder, 'Farm Name')]"),
                (By.ID, "OwnerLastName"),  # Fallback
                (By.NAME, "OwnerLastName"),  # Fallback
                (By.XPATH, "//input[@id='OwnerLastName' or @name='OwnerLastName']"),
            ]
            
            for by, value in owner_selectors:
                try:
                    elements = driver.find_elements(by, value)
                    for elem in elements:
                        if elem.is_displayed() and elem.get_attribute('type') in [None, 'text', 'search']:
                            owner_last_name_field = elem
                            print_with_timestamp(f"  Found Owner Last Name/Farm Name field using: {by}={value}")
                            break
                    if owner_last_name_field:
                        break
                except NoSuchElementException:
                    continue
            
            # Try JavaScript as fallback
            if not owner_last_name_field:
                try:
                    owner_last_name_field = driver.execute_script("""
                        var labels = document.querySelectorAll('label');
                        for (var i = 0; i < labels.length; i++) {
                            if (labels[i].textContent && (labels[i].textContent.includes('Owner Last Name') || labels[i].textContent.includes('Farm Name'))) {
                                var input = labels[i].querySelector('input') || 
                                           labels[i].nextElementSibling || 
                                           document.querySelector('input[name*="OwnerLastName" i], input[id*="OwnerLastName" i]');
                                if (input) return input;
                            }
                        }
                        return document.getElementById('OwnerLastName') || document.querySelector('input[name="OwnerLastName"]');
                    """)
                    if owner_last_name_field:
                        print_with_timestamp("  Found Owner Last Name/Farm Name field via JavaScript")
                except:
                    pass
            
            if not owner_last_name_field:
                print_with_timestamp("  [WARNING] Could not find Owner Last Name/Farm Name field, searching by horse name only")
                owner_last_name = None  # Fall back to horse name only
        
        # Fill in the fields
        try:
            # Use JavaScript to set values directly if we have the field reference
            if name_field:
                try:
                    # Try to get the actual input element's ID or name
                    field_id = name_field.get_attribute('id') or ''
                    field_name = name_field.get_attribute('name') or ''
                    
                    if field_id:
                        driver.execute_script(f"document.getElementById('{field_id}').value = arguments[0];", horse_name)
                        driver.execute_script(f"document.getElementById('{field_id}').dispatchEvent(new Event('input', {{bubbles: true}}));")
                        driver.execute_script(f"document.getElementById('{field_id}').dispatchEvent(new Event('change', {{bubbles: true}}));")
                        print_with_timestamp(f"  Set horse name via JavaScript (ID: {field_id}): {horse_name}")
                    elif field_name:
                        driver.execute_script(f"document.querySelector('input[name=\"{field_name}\"]').value = arguments[0];", horse_name)
                        driver.execute_script(f"document.querySelector('input[name=\"{field_name}\"]').dispatchEvent(new Event('input', {{bubbles: true}}));")
                        driver.execute_script(f"document.querySelector('input[name=\"{field_name}\"]').dispatchEvent(new Event('change', {{bubbles: true}}));")
                        print_with_timestamp(f"  Set horse name via JavaScript (name: {field_name}): {horse_name}")
                    else:
                        # Fallback to Selenium
                        name_field.clear()
                        name_field.send_keys(horse_name)
                        print_with_timestamp(f"  Entered horse name via Selenium: {horse_name}")
                except:
                    # Fallback to Selenium
                    name_field.clear()
                    name_field.send_keys(horse_name)
                    print_with_timestamp(f"  Entered horse name via Selenium: {horse_name}")
            else:
                print_with_timestamp("  [ERROR] No name field reference available")
                return False, None
            
            if owner_last_name and owner_last_name_field:
                try:
                    owner_field_id = owner_last_name_field.get_attribute('id') or ''
                    owner_field_name = owner_last_name_field.get_attribute('name') or ''
                    
                    if owner_field_id:
                        driver.execute_script(f"document.getElementById('{owner_field_id}').value = arguments[0];", owner_last_name)
                        driver.execute_script(f"document.getElementById('{owner_field_id}').dispatchEvent(new Event('input', {{bubbles: true}}));")
                        driver.execute_script(f"document.getElementById('{owner_field_id}').dispatchEvent(new Event('change', {{bubbles: true}}));")
                        print_with_timestamp(f"  Set owner last name via JavaScript (ID: {owner_field_id}): {owner_last_name}")
                    elif owner_field_name:
                        driver.execute_script(f"document.querySelector('input[name=\"{owner_field_name}\"]').value = arguments[0];", owner_last_name)
                        driver.execute_script(f"document.querySelector('input[name=\"{owner_field_name}\"]').dispatchEvent(new Event('input', {{bubbles: true}}));")
                        driver.execute_script(f"document.querySelector('input[name=\"{owner_field_name}\"]').dispatchEvent(new Event('change', {{bubbles: true}}));")
                        print_with_timestamp(f"  Set owner last name via JavaScript (name: {owner_field_name}): {owner_last_name}")
                    else:
                        owner_last_name_field.clear()
                        owner_last_name_field.send_keys(owner_last_name)
                        print_with_timestamp(f"  Entered owner last name via Selenium: {owner_last_name}")
                except:
                    owner_last_name_field.clear()
                    owner_last_name_field.send_keys(owner_last_name)
                    print_with_timestamp(f"  Entered owner last name via Selenium: {owner_last_name}")
            elif owner_last_name_field:
                # Clear owner last name field if it exists
                try:
                    owner_field_id = owner_last_name_field.get_attribute('id') or ''
                    if owner_field_id:
                        driver.execute_script(f"document.getElementById('{owner_field_id}').value = '';")
                    else:
                        owner_last_name_field.clear()
                    print_with_timestamp("  Cleared owner last name field (searching by horse name only)")
                except:
                    pass
        except Exception as e:
            print_with_timestamp(f"  [ERROR] Error filling fields: {e}")
            import traceback
            traceback.print_exc()
            return False, None
        
        time.sleep(0.5)  # Reduced wait time
        
        # Find and click search button (with timeout)
        search_button = None
        search_selectors = [
            (By.XPATH, "//input[@type='submit' and @value='Search' and @name='action' and contains(@class, 'btn-primary')]"),
            (By.XPATH, "//input[@type='submit' and @value='Search' and @name='action']"),
            (By.XPATH, "//input[@type='submit' and @value='Search']"),
            (By.XPATH, "//button[contains(text(), 'Search') and contains(@class, 'btn-primary')]"),
            (By.XPATH, "//button[contains(text(), 'Search')]"),
            (By.XPATH, "//input[@type='submit']")
        ]
        
        # Try to find button with WebDriverWait (faster, with timeout)
        try:
            search_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='submit' and @value='Search' and @name='action']"))
            )
            print_with_timestamp("  Found search button via WebDriverWait")
        except TimeoutException:
            # Try other selectors
            for by, value in search_selectors:
                try:
                    elements = driver.find_elements(by, value)
                    for elem in elements:
                        if elem.is_displayed():
                            search_button = elem
                            print_with_timestamp(f"  Found search button using: {by}={value}")
                            break
                    if search_button:
                        break
                except:
                    continue
        
        if not search_button:
            # Try JavaScript to find and click search button (faster)
            try:
                search_button_js = driver.execute_script("""
                    return document.querySelector('input[type="submit"][value="Search"][name="action"].btn-primary') ||
                           document.querySelector('input[type="submit"][value="Search"][name="action"]') ||
                           document.querySelector('input[type="submit"][value="Search"]') ||
                           document.querySelector('button.btn-primary:contains("Search")') ||
                           document.querySelector('button:contains("Search")');
                """)
                if search_button_js:
                    print_with_timestamp("  Found search button via JavaScript, clicking...")
                    driver.execute_script("arguments[0].click();", search_button_js)
                    print_with_timestamp("  Clicked search button via JavaScript")
                    time.sleep(1)  # Reduced wait time
                    return True, None
                else:
                    print_with_timestamp("  [ERROR] Could not find search button")
                    return False, None
            except Exception as e:
                print_with_timestamp(f"  [ERROR] Could not find search button: {e}")
                return False, None
        
        # Click the button
        try:
            # Try JavaScript click first (faster and more reliable)
            driver.execute_script("arguments[0].click();", search_button)
            print_with_timestamp("  Clicked search button via JavaScript")
        except:
            # Fallback to normal click
            try:
                search_button.click()
                print_with_timestamp("  Clicked search button")
            except Exception as e:
                print_with_timestamp(f"  [ERROR] Could not click search button: {e}")
                return False, None
        
        time.sleep(1)  # Reduced wait time from sleep_medium
        
        return True, None
        
    except (ReadTimeoutError, MaxRetryError, TimeoutError, NewConnectionError) as e:
        print_with_timestamp(f"  [WARNING] Timeout/connection error during search: {e}")
        print_with_timestamp("  Attempting to reconnect browser and re-authenticate...")
        
        # If retry_auth is provided, reconnect browser and re-authenticate
        if retry_auth:
            auth_url, auth_username, auth_password = retry_auth
            try:
                # Reconnect browser (quit old, create new) and re-authenticate
                new_driver = reconnect_browser_and_authenticate(driver, auth_url, auth_username, auth_password, headless=headless)
                if new_driver:
                    print_with_timestamp("  Browser reconnected and re-authenticated, retrying search...")
                    # Retry the search with new driver (only once to avoid infinite loop)
                    return search_horse(new_driver, horse_name, owner_last_name, sleep_short, sleep_medium, retry_auth=None, headless=headless)
                else:
                    print_with_timestamp("  [ERROR] Browser reconnection/re-authentication failed")
                    return False, None
            except Exception as reconnect_error:
                print_with_timestamp(f"  [ERROR] Error during browser reconnection: {reconnect_error}")
                import traceback
                traceback.print_exc()
                return False, None
        else:
            print_with_timestamp("  [ERROR] No retry authentication info provided")
            return False, None
        
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error during search: {e}")
        import traceback
        traceback.print_exc()
        return False, None

def has_search_results(driver, horse_name, sleep_short=2, timeout=20):
    """Check if search results contain the horse name
    
    Args:
        driver: WebDriver instance
        horse_name: Horse name to look for
        sleep_short: Short sleep duration in seconds (default: 2)
        timeout: Maximum time to wait for results in seconds (default: 20)
    
    Returns:
        True if results found, False otherwise
    """
    try:
        # Wait for results to load with timeout
        import time as time_module
        start_time = time_module.time()
        
        # Wait longer initially for page to start loading after search button click
        time.sleep(3)
        
        # Check for results with timeout
        while (time_module.time() - start_time) < timeout:
        
            # Check elapsed time
            elapsed = time_module.time() - start_time
            if elapsed >= timeout:
                break
            
            # Look for result rows matching the horse's name (with timeout protection)
            try:
                # First, wait for table to appear (if it exists) - but don't block if it doesn't
                if elapsed < 10:  # Only wait for table in first 10 seconds
                    try:
                        WebDriverWait(driver, 2).until(
                            EC.any_of(
                                EC.presence_of_element_located((By.XPATH, "//table//tbody//tr")),
                                EC.presence_of_element_located((By.XPATH, "//table//tr")),
                                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'No results') or contains(text(), 'no results')]"))
                            )
                        )
                    except TimeoutException:
                        # Table might not have appeared yet, continue checking
                        pass
                
                # Strategy 1: Look for any table rows (results exist if table has rows)
                try:
                    # Check if there are any result rows in the table (not just header)
                    all_table_rows = driver.find_elements(By.XPATH, "//table//tbody//tr | //table//tr")
                    if len(all_table_rows) > 0:
                        # If we have table rows, check if any contain the horse name
                        # But also check if it's just a header row
                        for row in all_table_rows[:20]:  # Check first 20 rows
                            try:
                                row_text = row.text[:300]  # Limit text check
                                row_text_upper = row_text.upper()
                                horse_name_upper = horse_name.upper()
                                
                                # Skip header rows (common header text)
                                if any(header in row_text_upper for header in ['ID', 'NAME', 'HORSE', 'OWNER', 'FOAL DATE', 'COLOR', 'SEX']):
                                    if len(row_text_upper) < 50:  # Likely a header row
                                        continue
                                
                                # Check if horse name is present (case-insensitive)
                                if horse_name_upper in row_text_upper:
                                    print_with_timestamp(f"  Found results for {horse_name} in table row (elapsed: {elapsed:.1f}s)")
                                    return True
                            except:
                                continue
                        
                        # If we have table rows but didn't find the horse name, 
                        # it might still be loading or the name format is different
                        # Don't return False yet, continue checking
                        if elapsed < 15:  # Give more time if we see table rows
                            print_with_timestamp(f"  Table rows found but horse name not matched yet, continuing to check... (elapsed: {elapsed:.1f}s)")
                except Exception as e:
                    # If we can't check table rows, continue with other strategies
                    pass
                
                # Strategy 2: Look for rows specifically containing horse name
                result_row_selectors = [
                    f"//table//tbody//tr[contains(., '{horse_name}')]",
                    f"//tr[contains(., '{horse_name}')]",
                ]
                
                for selector in result_row_selectors:
                    try:
                        # Use a quick check - limit to first few rows to avoid hanging
                        rows = driver.find_elements(By.XPATH, selector)
                        # Only check first 20 rows to avoid hanging on large result sets
                        for row in rows[:20]:
                            try:
                                row_text = row.text[:300]  # Limit text check to avoid hanging
                                row_text_upper = row_text.upper()
                                horse_name_upper = horse_name.upper()
                                
                                # Check if horse name is present (case-insensitive)
                                if horse_name_upper in row_text_upper:
                                    print_with_timestamp(f"  Found results for {horse_name} via selector (elapsed: {elapsed:.1f}s)")
                                    return True
                            except:
                                continue
                    except (ReadTimeoutError, MaxRetryError, TimeoutError, NewConnectionError):
                        # If we get a timeout, break out of the loop
                        print_with_timestamp(f"  [WARNING] Timeout while checking results, elapsed: {elapsed:.1f}s")
                        break
                    except:
                        continue
                
                # Also check for "No results" messages
                try:
                    no_results_selectors = [
                        "//*[contains(text(), 'No results')]",
                        "//*[contains(text(), 'no results')]",
                        "//*[contains(text(), 'No matches')]",
                    ]
                    
                    for selector in no_results_selectors:
                        try:
                            no_results = driver.find_elements(By.XPATH, selector)
                            if no_results:
                                for elem in no_results[:3]:  # Only check first 3
                                    try:
                                        if elem.is_displayed():
                                            return False
                                    except:
                                        continue
                        except:
                            continue
                except:
                    pass
                
            except (ReadTimeoutError, MaxRetryError, TimeoutError, NewConnectionError) as timeout_err:
                print_with_timestamp(f"  [WARNING] Connection error while checking results: {timeout_err}")
                break
            except Exception as e:
                # Other errors - log but continue
                if elapsed < 2:  # Only log if we haven't been trying long
                    print_with_timestamp(f"  [DEBUG] Error checking results: {e}")
            
            # If no results found yet and we have time, wait a bit and check again
            elapsed = time_module.time() - start_time
            if elapsed < timeout - 1.0:
                # Wait longer between checks to give page more time to load
                time.sleep(1.0)
            else:
                break
        
        # Timeout reached, assume no results
        print_with_timestamp(f"  [WARNING] Results check timed out after {timeout}s, assuming no results")
        return False
    except Exception as e:
        print_with_timestamp(f"  [WARNING] Error checking for results: {e}")
        return False

def extract_horse_info(driver, horse_name, sleep_short=2, sleep_medium=3):
    """Extract horse information from the search results page
    
    Args:
        driver: WebDriver instance
        horse_name: Horse name to find in results
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    
    Returns:
        Dictionary with 'usefid', 'foal_date', 'color', 'sex', 'breed', 'sire', 'dam' keys, or None if not found
    """
    print_with_timestamp(f"\nExtracting horse information from results for {horse_name}...")
    
    try:
        # Wait for results to load
        time.sleep(sleep_medium)
        
        horse_info = {
            'usefid': None,
            'foal_date': None,
            'color': None,
            'sex': None,
            'breed': None,
            'sire': None,
            'dam': None
        }
        
        # Look for result rows matching the horse's name
        try:
            # Find the result row that contains the horse name
            result_row_selectors = [
                f"//table//tbody//tr[contains(., '{horse_name}')]",
                f"//tr[contains(., '{horse_name}')]",
                f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{horse_name.lower()}')]/ancestor::tr[1]",
            ]
            
            result_row = None
            for selector in result_row_selectors:
                try:
                    rows = driver.find_elements(By.XPATH, selector)
                    for row in rows:
                        try:
                            row_text = row.text
                            row_text_upper = row_text.upper()
                            horse_name_upper = horse_name.upper()
                            
                            # Check if horse name is present (case-insensitive)
                            if horse_name_upper in row_text_upper:
                                result_row = row
                                print_with_timestamp(f"  Found result row for {horse_name}")
                                break
                        except Exception as e:
                            continue
                    if result_row:
                        break
                except:
                    continue
            
            if result_row:
                # Extract USEFID - look for number preceding the horse's name
                try:
                    # Get all text from the row
                    row_text = result_row.text
                    row_html = result_row.get_attribute('innerHTML')
                    
                    # Look for pattern: number followed by horse name (above the details)
                    # Pattern might be like "1234567 HORSE NAME" or "ID: 1234567 HORSE NAME"
                    usefid_patterns = [
                        r'(\d{6,})\s+' + re.escape(horse_name),  # 6+ digits followed by horse name
                        r'(\d{6,})\s*<[^>]*>' + re.escape(horse_name),  # In HTML
                        r'ID[:\s]+(\d{6,})',  # "ID: 1234567"
                        r'^(\d{6,})\s+',  # Starts with 6+ digits
                    ]
                    
                    for pattern in usefid_patterns:
                        match = re.search(pattern, row_text, re.IGNORECASE)
                        if match:
                            horse_info['usefid'] = match.group(1)
                            print_with_timestamp(f"  Found USEFID: {horse_info['usefid']}")
                            break
                    
                    # Also try HTML patterns
                    if not horse_info['usefid']:
                        for pattern in usefid_patterns:
                            match = re.search(pattern, row_html, re.IGNORECASE)
                            if match:
                                horse_info['usefid'] = match.group(1)
                                print_with_timestamp(f"  Found USEFID from HTML: {horse_info['usefid']}")
                                break
                    
                    # Also check first cell for ID
                    if not horse_info['usefid']:
                        try:
                            first_td = result_row.find_element(By.XPATH, "./td[1]")
                            if first_td:
                                id_text = first_td.text.strip()
                                id_match = re.search(r'(\d{6,})', id_text)
                                if id_match:
                                    horse_info['usefid'] = id_match.group(1)
                                    print_with_timestamp(f"  Found USEFID from first cell: {horse_info['usefid']}")
                        except:
                            pass
                    
                    # Also check for links with ID in href
                    if not horse_info['usefid']:
                        try:
                            links = result_row.find_elements(By.XPATH, ".//a[contains(@href, 'id=') or contains(@href, 'ID=')]")
                            for link in links:
                                href = link.get_attribute('href')
                                if href:
                                    parsed = urllib.parse.urlparse(href)
                                    params = urllib.parse.parse_qs(parsed.query)
                                    if 'id' in params:
                                        horse_info['usefid'] = params['id'][0]
                                        print_with_timestamp(f"  Found USEFID from link: {horse_info['usefid']}")
                                        break
                                    elif 'ID' in params:
                                        horse_info['usefid'] = params['ID'][0]
                                        print_with_timestamp(f"  Found USEFID from link: {horse_info['usefid']}")
                                        break
                        except:
                            pass
                except Exception as e:
                    print_with_timestamp(f"  [DEBUG] Error extracting USEFID: {e}")
                
                # Extract other information from the result row
                # Look for labels like "Foal Date:", "Color:", "Sex:", "Breed:", "Sire:", "Dam:"
                if 'row_html' not in locals():
                    row_html = result_row.get_attribute('innerHTML')
                
                # Foal Date - capture date including slashes, stop at " - " or end
                foal_date_patterns = [
                    r'Foal\s+Date[:\s]+([\d/]+[^<\n]*?)(?:\s*-\s*Age\s+Verified|$|</)',
                    r'Foal\s+Date[:\s]+([\d/]+)(?:\s*-\s*[^<\n]*)?',
                    r'DOB[:\s]+([\d/]+[^<\n]*?)(?:\s*-\s*Age\s+Verified|$|</)',
                    r'DOB[:\s]+([\d/]+)(?:\s*-\s*[^<\n]*)?',
                    r'Date\s+of\s+Birth[:\s]+([\d/]+[^<\n]*?)(?:\s*-\s*Age\s+Verified|$|</)',
                    r'Date\s+of\s+Birth[:\s]+([\d/]+)(?:\s*-\s*[^<\n]*)?',
                ]
                for pattern in foal_date_patterns:
                    match = re.search(pattern, row_html, re.IGNORECASE)
                    if match:
                        foal_date = match.group(1).strip()
                        # Strip " - Age Verified" or similar suffixes
                        foal_date = re.sub(r'\s*-\s*Age\s+Verified.*$', '', foal_date, flags=re.IGNORECASE).strip()
                        foal_date = re.sub(r'\s*-\s*.*$', '', foal_date).strip()  # Strip any remaining " - ..." suffix
                        # Clean up any trailing non-date characters
                        foal_date = re.sub(r'[^\d/].*$', '', foal_date).strip()
                        horse_info['foal_date'] = foal_date
                        print_with_timestamp(f"  Found Foal Date: {horse_info['foal_date']}")
                        break
                
                # Color - capture only until next field (Sex, Breed, etc.) or end of line
                color_patterns = [
                    r'Color[:\s]+([^<\n]+?)(?:\s+Sex[:\s]|$|</)',
                    r'Color[:\s]+([A-Za-z\s]+?)(?=\s+Sex|$|</)',
                ]
                for pattern in color_patterns:
                    match = re.search(pattern, row_html, re.IGNORECASE)
                    if match:
                        color = match.group(1).strip()
                        # Remove any trailing whitespace and ensure we stop at Sex field
                        color = re.sub(r'\s+Sex.*$', '', color, flags=re.IGNORECASE).strip()
                        horse_info['color'] = color
                        print_with_timestamp(f"  Found Color: {horse_info['color']}")
                        break
                
                # Sex - capture only the sex value, not following text
                sex_patterns = [
                    r'Sex[:\s]+([A-Za-z]+?)(?:\s|$|</)',
                    r'Gender[:\s]+([A-Za-z]+?)(?:\s|$|</)',
                ]
                for pattern in sex_patterns:
                    match = re.search(pattern, row_html, re.IGNORECASE)
                    if match:
                        sex = match.group(1).strip()
                        # Ensure we only capture the sex value (G, M, F, etc.)
                        sex = re.sub(r'\s+.*$', '', sex).strip()
                        horse_info['sex'] = sex
                        print_with_timestamp(f"  Found Sex: {horse_info['sex']}")
                        break
                
                # Breed
                breed_patterns = [
                    r'Breed[:\s]+([^<\n]+)',
                ]
                for pattern in breed_patterns:
                    match = re.search(pattern, row_html, re.IGNORECASE)
                    if match:
                        horse_info['breed'] = match.group(1).strip()
                        print_with_timestamp(f"  Found Breed: {horse_info['breed']}")
                        break
                
                # Sire
                sire_patterns = [
                    r'Sire[:\s]+([^<\n]+)',
                ]
                for pattern in sire_patterns:
                    match = re.search(pattern, row_html, re.IGNORECASE)
                    if match:
                        horse_info['sire'] = match.group(1).strip()
                        print_with_timestamp(f"  Found Sire: {horse_info['sire']}")
                        break
                
                # Dam
                dam_patterns = [
                    r'Dam[:\s]+([^<\n]+)',
                ]
                for pattern in dam_patterns:
                    match = re.search(pattern, row_html, re.IGNORECASE)
                    if match:
                        horse_info['dam'] = match.group(1).strip()
                        print_with_timestamp(f"  Found Dam: {horse_info['dam']}")
                        break
                
                # If we found at least the USEFID, return the info
                if horse_info['usefid']:
                    print_with_timestamp(f"  [OK] Found horse information:")
                    print_with_timestamp(f"    USEFID: {horse_info['usefid']}")
                    if horse_info['foal_date']:
                        print_with_timestamp(f"    Foal Date: {horse_info['foal_date']}")
                    if horse_info['color']:
                        print_with_timestamp(f"    Color: {horse_info['color']}")
                    if horse_info['sex']:
                        print_with_timestamp(f"    Sex: {horse_info['sex']}")
                    if horse_info['breed']:
                        print_with_timestamp(f"    Breed: {horse_info['breed']}")
                    if horse_info['sire']:
                        print_with_timestamp(f"    Sire: {horse_info['sire']}")
                    if horse_info['dam']:
                        print_with_timestamp(f"    Dam: {horse_info['dam']}")
                    return horse_info
                else:
                    print_with_timestamp("  [WARNING] Could not extract USEFID from results")
            else:
                print_with_timestamp("  [WARNING] Could not find result row for horse")
        except Exception as e:
            print_with_timestamp(f"  [DEBUG] Error in result row strategy: {e}")
            import traceback
            traceback.print_exc()
        
        print_with_timestamp("  [WARNING] Could not extract horse information from results")
        print_with_timestamp(f"  Current URL: {driver.current_url}")
        return None
            
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error extracting horse information: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_db_connection():
    """Get SQL Server database connection"""
    # Check if running on LDAHSAR - use Windows authentication if so
    import socket
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

def parse_owner_name_into_last_name(owner_name):
    """Parse owner name to extract last name
    
    Args:
        owner_name: Owner name string (could be "LastName, FirstName" or "FirstName LastName")
    
    Returns:
        Last name string or None if parsing fails
    """
    if not owner_name or not owner_name.strip():
        return None
    
    owner_name = owner_name.strip()
    
    # Primary format: "LastName, FirstName"
    if ',' in owner_name:
        parts = [p.strip() for p in owner_name.split(',', 1)]
        if len(parts) >= 1:
            return parts[0]  # Part before comma is LastName
    
    # Fallback format: "FirstName LastName" - take last part
    parts = owner_name.split()
    if len(parts) >= 1:
        return parts[-1]  # Last part is LastName
    
    return None

def ensure_horse_columns_exist(conn):
    """Ensure Sire, Dam, DOB, Sex, Color, Breed, USEFID columns exist in sResults.Horse table
    
    Args:
        conn: Database connection
    
    Returns:
        True if columns exist or were created, False otherwise
    """
    cursor = conn.cursor()
    try:
        # Check if Sire column exists
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = 'sResults' 
            AND TABLE_NAME = 'Horse' 
            AND COLUMN_NAME = 'Sire'
        """)
        has_sire = cursor.fetchone()[0] > 0
        
        if not has_sire:
            print_with_timestamp("Adding Sire, Dam, DOB, Sex, Color, Breed, USEFID columns to Horse table...")
            try:
                # Add columns after HorseName column
                cursor.execute("""
                    ALTER TABLE sResults.Horse 
                    ADD Sire NVARCHAR(200),
                        Dam NVARCHAR(200),
                        DOB DATE,
                        Sex NVARCHAR(20),
                        Color NVARCHAR(50),
                        Breed NVARCHAR(100),
                        USEFID NVARCHAR(50)
                """)
                conn.commit()
                print_with_timestamp("[OK] Added Sire, Dam, DOB, Sex, Color, Breed, USEFID columns")
                return True
            except Exception as e:
                print_with_timestamp(f"[ERROR] Error adding new columns: {e}")
                conn.rollback()
                return False
        else:
            print_with_timestamp("[OK] Sire, Dam, DOB, Sex, Color, Breed, USEFID columns already exist")
            return True
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error checking/creating columns: {e}")
        return False
    finally:
        cursor.close()

def update_horses_from_usef(conn, driver, headless=True, start_from_horse=None):
    """Update Horse table with USEF information for all horses
    
    Args:
        conn: Database connection
        driver: WebDriver instance
        headless: Run browser in headless mode (default: True)
        start_from_horse: Horse name to start from. All horses before this one will be skipped.
    
    Returns:
        Tuple of (number of horses updated, driver instance). Driver may be replaced if reconnection occurred.
    """
    print_with_timestamp("\nUpdating Horse table with USEF information...")
    
    # Ensure columns exist before proceeding
    if not ensure_horse_columns_exist(conn):
        print_with_timestamp("[ERROR] Could not ensure columns exist, aborting")
        return 0, driver
    
    cursor = conn.cursor()
    try:
        # Get all unique HorseName values with their corresponding Owner from Competitors
        # Join Horse and Competitors on OwnerID (Horse.OwnerID = Competitors.ID)
        cursor.execute("""
            SELECT DISTINCT h.ID, h.HorseName, c.Owner
            FROM sResults.Horse h
            INNER JOIN sResults.Competitors c ON h.OwnerID = c.ID
            WHERE h.HorseName IS NOT NULL AND h.HorseName != ''
            AND c.Owner IS NOT NULL AND c.Owner != ''
            AND (h.USEFID IS NULL OR h.USEFID = '')
            ORDER BY h.ID
        """)
        
        horses = cursor.fetchall()
        print_with_timestamp(f"Found {len(horses)} unique horses to process")
        
        if len(horses) == 0:
            print_with_timestamp("No horses found in Horse table")
            return 0, driver
        
        # Skip to start_from_horse if specified
        start_index = 0
        total_horses = len(horses)
        if start_from_horse:
            try:
                for idx, (horse_id, horse_name, _) in enumerate(horses):
                    if horse_name == start_from_horse:
                        start_index = idx
                        horses = horses[start_index:]
                        print_with_timestamp(f"Starting from horse: {start_from_horse} (ID: {horse_id}, skipped {start_index} horses)")
                        break
                else:
                    print_with_timestamp(f"[WARNING] Horse '{start_from_horse}' not found in list. Starting from beginning.")
                    print_with_timestamp(f"  Available horses start with: {horses[0][1] if horses else 'N/A'}")
                    start_index = 0
            except Exception as e:
                print_with_timestamp(f"[WARNING] Error finding start horse: {e}")
                start_index = 0
        
        updated_count = 0
        failed_count = 0
        
        # Navigate to USEF search page and authenticate once
        search_url = "https://www.usef.org/search/horses"
        auth_success, auth_username, auth_password = check_and_authenticate(driver, search_url)
        
        if not auth_success:
            print_with_timestamp("[ERROR] Authentication failed, cannot continue")
            return 0, driver
        
        # Store credentials for retry on timeout
        retry_auth = (search_url, auth_username, auth_password)
        
        # Calculate starting index for display
        start_display_idx = start_index + 1
        
        # Process each horse
        for idx, (horse_id, horse_name, owner_name) in enumerate(horses, start_display_idx):
            try:
                print_with_timestamp(f"\n[{idx}/{total_horses}] Processing horse: {horse_name} (Owner: {owner_name})")
                
                # Clean horse name - remove quotes and trailing numbers/descriptors like "FATIMO" (1) -> FATIMO
                cleaned_horse_name = horse_name.strip()
                # Remove surrounding quotes if present
                if cleaned_horse_name.startswith('"') and cleaned_horse_name.endswith('"'):
                    cleaned_horse_name = cleaned_horse_name[1:-1].strip()
                # Remove trailing patterns like " (1)", " (2)", etc.
                cleaned_horse_name = re.sub(r'\s*\(\d+\)\s*$', '', cleaned_horse_name).strip()
                # Remove any remaining quotes
                cleaned_horse_name = cleaned_horse_name.replace('"', '').strip()
                if cleaned_horse_name != horse_name:
                    print_with_timestamp(f"  Cleaned horse name: '{horse_name}' -> '{cleaned_horse_name}'")
                horse_name = cleaned_horse_name
                
                # Parse owner name to get last name
                owner_last_name = parse_owner_name_into_last_name(owner_name)
                
                if not owner_last_name:
                    print_with_timestamp(f"  [WARNING] Could not parse owner name '{owner_name}' into last name")
                    failed_count += 1
                    continue
                
                print_with_timestamp(f"  Parsed owner last name: {owner_last_name}")
                
                # Search for the horse with owner last name (with retry auth info)
                search_success, new_driver = search_horse(driver, horse_name, owner_last_name, retry_auth=retry_auth, headless=headless)
                if new_driver:
                    driver = new_driver  # Update driver reference if reconnection occurred
                
                if not search_success:
                    print_with_timestamp(f"  [WARNING] Search failed for {horse_name}")
                    failed_count += 1
                    time.sleep(2)
                    continue
                
                # Check if results were found (with reasonable timeout)
                has_results = has_search_results(driver, horse_name, timeout=20)
                
                # If no results found with owner last name, try searching with just horse name
                if not has_results and owner_last_name:
                    print_with_timestamp(f"  [WARNING] No results found with owner last name '{owner_last_name}', trying search with just horse name...")
                    search_success, new_driver = search_horse(driver, horse_name, owner_last_name=None, retry_auth=retry_auth, headless=headless)
                    if new_driver:
                        driver = new_driver  # Update driver reference if reconnection occurred
                    
                    if not search_success:
                        print_with_timestamp(f"  [WARNING] Search failed for {horse_name} (horse name only)")
                        failed_count += 1
                        time.sleep(2)
                        continue
                    
                    # Check again if results were found (with reasonable timeout)
                    has_results = has_search_results(driver, horse_name, timeout=20)
                    if not has_results:
                        print_with_timestamp(f"  [WARNING] No results found for {horse_name} (even with horse name only)")
                        failed_count += 1
                        time.sleep(2)
                        continue
                
                # Extract horse information
                horse_info = extract_horse_info(driver, horse_name)
                
                if horse_info and horse_info.get('usefid'):
                    # Update all rows with this horse name
                    # Parse DOB from foal_date string
                    dob_value = None
                    if horse_info.get('foal_date'):
                        try:
                            # Clean the date string - keep only digits and slashes
                            foal_date_str = horse_info['foal_date'].strip()
                            # Remove " - Age Verified" or similar suffixes if still present
                            foal_date_str = re.sub(r'\s*-\s*Age\s+Verified.*$', '', foal_date_str, flags=re.IGNORECASE).strip()
                            foal_date_str = re.sub(r'\s*-\s*.*$', '', foal_date_str).strip()
                            
                            # Extract just the date part (digits and slashes)
                            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', foal_date_str)
                            if date_match:
                                foal_date_str = date_match.group(1)
                            
                            # Try common date formats
                            for fmt in ['%m/%d/%Y', '%m/%d/%y', '%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%m-%d-%Y']:
                                try:
                                    dob_value = datetime.strptime(foal_date_str, fmt).date()
                                    print_with_timestamp(f"  Parsed DOB: {dob_value} from '{foal_date_str}'")
                                    break
                                except ValueError:
                                    continue
                            
                            if not dob_value:
                                print_with_timestamp(f"  [WARNING] Could not parse DOB from '{foal_date_str}'")
                        except Exception as e:
                            print_with_timestamp(f"  [WARNING] Error parsing DOB: {e}")
                            pass
                    
                    cursor.execute("""
                        UPDATE sResults.Horse 
                        SET Sire = ?,
                            Dam = ?,
                            DOB = ?,
                            Sex = ?,
                            Color = ?,
                            Breed = ?,
                            USEFID = ?,
                            UpdatedDate = GETDATE()
                        WHERE HorseName = ?
                    """, 
                        horse_info.get('sire'),
                        horse_info.get('dam'),
                        dob_value,
                        horse_info.get('sex'),
                        horse_info.get('color'),
                        horse_info.get('breed'),
                        horse_info.get('usefid'),
                        horse_name
                    )
                    conn.commit()
                    updated_rows = cursor.rowcount
                    updated_count += updated_rows
                    print_with_timestamp(f"  [OK] Updated {updated_rows} row(s) for {horse_name}")
                    print_with_timestamp(f"    USEFID: {horse_info.get('usefid')}, DOB: {horse_info.get('foal_date')}, Color: {horse_info.get('color')}, Sex: {horse_info.get('sex')}")
                else:
                    print_with_timestamp(f"  [WARNING] Could not find valid USEF information for {horse_name}")
                    failed_count += 1
                
                # Small delay between searches to avoid overwhelming the server
                time.sleep(3)
                
            except Exception as e:
                print_with_timestamp(f"  [ERROR] Error processing {horse_name}: {e}")
                import traceback
                traceback.print_exc()
                failed_count += 1
                conn.rollback()
                continue
        
        print_with_timestamp(f"\n{'='*60}")
        print_with_timestamp(f"Update complete!")
        print_with_timestamp(f"  Successfully updated: {updated_count} horses")
        print_with_timestamp(f"  Failed/Skipped: {failed_count} horses")
        print_with_timestamp(f"{'='*60}\n")
        
        return updated_count, driver
        
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error updating horses: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return 0, driver
    finally:
        cursor.close()

def main(headless=True, start_from_horse=None):
    """Main function to update all horses in Horse table with USEF information
    
    Args:
        headless: Run browser in headless mode (default: True)
        start_from_horse: Horse name to start from when updating all horses
    """
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("USEF Horse Search Scraper")
    print_with_timestamp("=" * 60 + "\n")
    
    driver = None
    conn = None
    
    try:
        # Setup driver
        print_with_timestamp("Initializing browser...")
        driver = setup_driver(headless=headless)
        print_with_timestamp("  [OK] Browser initialized\n")
        
        # Connect to database
        print_with_timestamp("Connecting to database...")
        conn = get_db_connection()
        print_with_timestamp("[OK] Connected to database\n")
        
        # Update all horses
        updated_count, driver = update_horses_from_usef(conn, driver, headless=headless, start_from_horse=start_from_horse)
        
    except KeyboardInterrupt:
        print_with_timestamp("\n\n[WARNING] Scraping interrupted by user")
    except Exception as e:
        print_with_timestamp(f"\n[ERROR] Fatal Error: {e}")
        import traceback
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
                print_with_timestamp(f"[WARNING] Error closing browser: {e}")

if __name__ == '__main__':
    import sys
    
    # Default values
    headless = True
    start_from_horse = None
    
    # Parse command-line arguments
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i].lower()
        
        if arg in ['--no-headless', '--visible']:
            headless = False
        elif arg in ['--start-from', '--skip-to', '-s']:
            if i + 1 < len(sys.argv):
                start_from_horse = sys.argv[i + 1]
                i += 1
            else:
                print_with_timestamp("[ERROR] --start-from requires a horse name")
                sys.exit(1)
        elif arg in ['--help', '-h']:
            print_with_timestamp("Usage: python scrape_usef_horse.py [OPTIONS]")
            print_with_timestamp("Options:")
            print_with_timestamp("  --no-headless, --visible: Run browser in visible mode (default: headless)")
            print_with_timestamp("  --start-from HORSE, --skip-to HORSE, -s HORSE: Start processing from this horse name")
            sys.exit(0)
        
        i += 1
    
    main(headless=headless, start_from_horse=start_from_horse)

