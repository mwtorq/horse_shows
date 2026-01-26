"""
Scraper to search for a person on USEF website and extract their ID
Navigates to https://www.usef.org/search/people
Handles authentication if required
Searches for a person by First Name and Last Name
Extracts and displays the person's ID from the results
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from urllib3.exceptions import ReadTimeoutError, MaxRetryError
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
        # Still navigate to People search page in case we're not there yet
        success = navigate_to_people_search(driver, url, sleep_short, sleep_medium)
        return success, username, password
    
    # If we found a login link, click it first to reveal the login form
    if login_link_found:
        try:
            print_with_timestamp("  Clicking Log In link...")
            # Scroll into view first
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", login_link_found)
            time.sleep(sleep_short / 2)
            # Try JavaScript click first
            driver.execute_script("arguments[0].click();", login_link_found)
            print_with_timestamp("  Log In link clicked via JavaScript")
            time.sleep(sleep_medium)  # Wait for login form to appear
            print_with_timestamp("  Waiting for login form to appear...")
        except Exception as e:
            print_with_timestamp(f"  [WARNING] Error clicking login link with JavaScript: {e}, trying normal click...")
            try:
                login_link_found.click()
                print_with_timestamp("  Log In link clicked via normal click")
                time.sleep(sleep_medium)
            except Exception as e2:
                print_with_timestamp(f"  [ERROR] Error clicking login link: {e2}")
                return False
    
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
    
    # Wait a moment for login form to appear (if we clicked a link)
    if login_link_found:
        time.sleep(sleep_short)
    
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
            time.sleep(sleep_medium)
            
            # Check if login was successful (URL changed or no login form visible)
            current_url = driver.current_url
            try:
                # Check if password field is still visible (login failed)
                driver.find_element(By.XPATH, "//input[@type='password']")
                print_with_timestamp("  [WARNING] Login may have failed - password field still visible")
                return False, username, password
            except NoSuchElementException:
                print_with_timestamp("  [OK] Login appears successful")
                # Navigate to People search page after login
                success = navigate_to_people_search(driver, url, sleep_short, sleep_medium)
                return success, username, password
        else:
            print_with_timestamp("  [ERROR] Could not find login/submit button")
            return False, username, password
            
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error during authentication: {e}")
        return False, username, password

def navigate_to_people_search(driver, target_url, sleep_short=2, sleep_medium=3):
    """Navigate to People search page after login
    Tries Compete dropdown first, then direct navigation
    
    Args:
        driver: WebDriver instance
        target_url: Target URL (https://www.usef.org/search/people)
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    
    Returns:
        True if navigation successful, False otherwise
    """
    print_with_timestamp("  Navigating to People search page...")
    
    # Check if we're already on the target page
    current_url = driver.current_url
    if 'search/people' in current_url.lower():
        print_with_timestamp("  Already on People search page")
        return True
    
    # Try to navigate via Compete dropdown menu
    try:
        print_with_timestamp("  Looking for Compete dropdown menu...")
        
        # Find Compete menu/dropdown
        compete_selectors = [
            "//a[contains(text(), 'Compete')]",
            "//*[contains(text(), 'Compete')]",
            "//button[contains(text(), 'Compete')]",
            "//li[contains(@class, 'dropdown')]//a[contains(text(), 'Compete')]",
            "//nav//a[contains(text(), 'Compete')]",
        ]
        
        compete_link = None
        for selector in compete_selectors:
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for elem in elements:
                    if elem.is_displayed():
                        compete_link = elem
                        print_with_timestamp("  Found Compete menu item")
                        break
                if compete_link:
                    break
            except:
                continue
        
        if compete_link:
            # Hover over or click Compete to open dropdown
            try:
                actions = ActionChains(driver)
                actions.move_to_element(compete_link).perform()
                time.sleep(sleep_short)
                print_with_timestamp("  Hovered over Compete menu")
            except:
                try:
                    compete_link.click()
                    time.sleep(sleep_short)
                    print_with_timestamp("  Clicked Compete menu")
                except:
                    pass
            
            # Look for "People" option in dropdown
            people_selectors = [
                "//a[contains(text(), 'People')]",
                "//a[contains(@href, 'search/people')]",
                "//a[contains(@href, 'People')]",
                "//li//a[contains(text(), 'People')]",
                "//dropdown//a[contains(text(), 'People')]",
            ]
            
            for selector in people_selectors:
                try:
                    people_links = driver.find_elements(By.XPATH, selector)
                    for link in people_links:
                        if link.is_displayed():
                            href = link.get_attribute('href') or ''
                            if 'people' in href.lower() or link.text.strip().lower() == 'people':
                                print_with_timestamp("  Found People link in dropdown, clicking...")
                                driver.execute_script("arguments[0].click();", link)
                                time.sleep(sleep_medium)
                                
                                # Verify we're on the right page
                                current_url = driver.current_url
                                if 'search/people' in current_url.lower():
                                    print_with_timestamp("  [OK] Successfully navigated to People search page via dropdown")
                                    return True
                                break
                except:
                    continue
        
        print_with_timestamp("  Could not navigate via dropdown, trying direct URL...")
        
    except Exception as e:
        print_with_timestamp(f"  [DEBUG] Error with dropdown navigation: {e}")
    
    # Fallback: Navigate directly to the URL
    try:
        print_with_timestamp(f"  Navigating directly to {target_url}...")
        driver.get(target_url)
        time.sleep(sleep_medium)
        
        # Verify we're on the right page
        current_url = driver.current_url
        if 'search/people' in current_url.lower():
            print_with_timestamp("  [OK] Successfully navigated to People search page")
            return True
        else:
            print_with_timestamp(f"  [WARNING] Navigation may have failed, current URL: {current_url}")
            return True  # Continue anyway
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error navigating to People search page: {e}")
        return False

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
    print_with_timestamp("  [RECONNECT] Quitting hung/crashed browser session...")
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
    except Exception as e:
        print_with_timestamp(f"  [RECONNECT] Error creating new browser session: {e}")
        return None

def search_person(driver, first_name, last_name, sleep_short=2, sleep_medium=3, retry_auth=None, headless=True):
    """Search for a person by first and last name
    
    Args:
        driver: WebDriver instance (may be replaced if reconnection occurs)
        first_name: First name to search for
        last_name: Last name to search for
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
        retry_auth: Optional tuple of (url, username, password, headless) for re-authentication on timeout
        headless: Run browser in headless mode (default: True)
    
    Returns:
        Tuple of (success: bool, new_driver: WebDriver or None). If reconnection occurred, new_driver will be the new instance.
    """
    print_with_timestamp(f"\nSearching for {first_name} {last_name}...")
    
    try:
        # Wait for page to load
        time.sleep(sleep_medium)
        
        # Handle cookie banner if present
        try:
            # Look for common cookie accept buttons
            cookie_selectors = [
                "//button[contains(text(), 'Accept') or contains(text(), 'Accept All')]",
                "//button[contains(text(), 'I Accept')]",
                "//a[contains(text(), 'Accept')]",
                "//button[@id='CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll']",
                "//button[contains(@class, 'cookie') and contains(@class, 'accept')]"
            ]
            for selector in cookie_selectors:
                try:
                    cookie_button = driver.find_element(By.XPATH, selector)
                    if cookie_button.is_displayed():
                        cookie_button.click()
                        print_with_timestamp("  Accepted cookies")
                        time.sleep(sleep_short)
                        break
                except:
                    continue
        except:
            pass
        
        # Wait a bit more for page to fully render
        time.sleep(sleep_short)
        
        # Debug: Print page title and URL (with error handling for tab crashes)
        try:
            print_with_timestamp(f"  Page title: {driver.title}")
            print_with_timestamp(f"  Current URL: {driver.current_url}")
        except WebDriverException as e:
            error_msg = str(e).lower()
            if 'tab crashed' in error_msg or 'session' in error_msg:
                print_with_timestamp(f"  [WARNING] Browser tab crashed while accessing page info: {e}")
                # Will be caught by outer exception handler
                raise
            else:
                # Other WebDriverException, log and continue
                print_with_timestamp(f"  [WARNING] Error accessing page info: {e}")
                print_with_timestamp(f"  Current URL: {driver.current_url if hasattr(driver, 'current_url') else 'unknown'}")
        
        # Debug: Find all input fields on the page (including hidden)
        try:
            all_inputs = driver.find_elements(By.TAG_NAME, "input")
            print_with_timestamp(f"  Found {len(all_inputs)} input fields on page")
            
            # Check page source for FirstName and LastName
            page_source = driver.page_source
            if 'FirstName' in page_source:
                print_with_timestamp("  [DEBUG] 'FirstName' found in page source")
            if 'LastName' in page_source:
                print_with_timestamp("  [DEBUG] 'LastName' found in page source")
            
            # List all inputs with their attributes
            text_inputs_found = []
            for i, inp in enumerate(all_inputs):
                try:
                    inp_id = inp.get_attribute('id') or 'no-id'
                    inp_name = inp.get_attribute('name') or 'no-name'
                    inp_type = inp.get_attribute('type') or 'no-type'
                    inp_placeholder = inp.get_attribute('placeholder') or 'no-placeholder'
                    is_displayed = inp.is_displayed()
                    
                    # Look for FirstName or LastName specifically
                    if 'FirstName' in inp_id or 'FirstName' in inp_name or 'firstname' in inp_id.lower() or 'firstname' in inp_name.lower():
                        print_with_timestamp(f"    >>> FIRST NAME CANDIDATE: id='{inp_id}', name='{inp_name}', type='{inp_type}', displayed={is_displayed}")
                        text_inputs_found.append(inp)
                    elif 'LastName' in inp_id or 'LastName' in inp_name or 'lastname' in inp_id.lower() or 'lastname' in inp_name.lower():
                        print_with_timestamp(f"    >>> LAST NAME CANDIDATE: id='{inp_id}', name='{inp_name}', type='{inp_type}', displayed={is_displayed}")
                        text_inputs_found.append(inp)
                    elif inp_type in ['text', 'search'] and i < 15:  # Print first 15 text inputs
                        print_with_timestamp(f"    Input {i+1}: id='{inp_id}', name='{inp_name}', type='{inp_type}', placeholder='{inp_placeholder}', displayed={is_displayed}")
                        text_inputs_found.append(inp)
                except:
                    pass
            
            # Try JavaScript to find the fields
            try:
                first_name_js = driver.execute_script("return document.getElementById('FirstName');")
                if first_name_js:
                    print_with_timestamp("  [DEBUG] Found FirstName via JavaScript")
                last_name_js = driver.execute_script("return document.getElementById('LastName');")
                if last_name_js:
                    print_with_timestamp("  [DEBUG] Found LastName via JavaScript")
            except:
                pass
                
        except Exception as e:
            print_with_timestamp(f"  [DEBUG] Error listing inputs: {e}")
        
        # Scroll to top to ensure page is fully loaded
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(sleep_short)
        
        # Check for "Advanced Search" or similar links/buttons that might reveal the form
        try:
            advanced_search_selectors = [
                "//a[contains(text(), 'Advanced') or contains(text(), 'advanced')]",
                "//button[contains(text(), 'Advanced')]",
                "//a[contains(@href, 'advanced') or contains(@href, 'Advanced')]",
                "//*[contains(text(), 'Advanced Search')]",
                "//*[contains(text(), 'More Options')]",
                "//*[contains(text(), 'More Filters')]"
            ]
            for selector in advanced_search_selectors:
                try:
                    advanced_link = driver.find_element(By.XPATH, selector)
                    if advanced_link.is_displayed():
                        print_with_timestamp("  Found advanced search link, clicking...")
                        driver.execute_script("arguments[0].click();", advanced_link)
                        time.sleep(sleep_medium)
                        break
                except:
                    continue
        except:
            pass
        
        # Scroll down a bit to trigger any lazy loading
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(sleep_short)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(sleep_short)
        
        # Check for iframes that might contain the form
        try:
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            if iframes:
                print_with_timestamp(f"  Found {len(iframes)} iframe(s), checking for form fields inside...")
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        try:
                            first_in_iframe = driver.find_element(By.ID, "FirstName")
                            print_with_timestamp("  Found FirstName in iframe!")
                            driver.switch_to.default_content()
                            driver.switch_to.frame(iframe)
                            break
                        except:
                            driver.switch_to.default_content()
                    except:
                        driver.switch_to.default_content()
        except:
            pass
        
        # Wait for form fields to be visible (they might load dynamically)
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "FirstName"))
            )
            print_with_timestamp("  Form fields loaded")
        except TimeoutException:
            # Try case-insensitive search
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//input[translate(@id, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='firstname']"))
                )
                print_with_timestamp("  Form fields loaded (case-insensitive)")
            except TimeoutException:
                # Try JavaScript to check if element exists in DOM
                try:
                    exists = driver.execute_script("return document.getElementById('FirstName') !== null;")
                    if exists:
                        print_with_timestamp("  FirstName exists in DOM (may be hidden)")
                    else:
                        print_with_timestamp("  [WARNING] FirstName field not found after wait, continuing anyway...")
                except:
                    print_with_timestamp("  [WARNING] FirstName field not found after wait, continuing anyway...")
        
        # Find first name field with comprehensive selectors
        first_name_field = None
        first_name_selectors = [
            (By.ID, "FirstName"),  # Exact match from USEF site
            (By.NAME, "FirstName"),  # Exact match from USEF site
            (By.ID, "firstName"),
            (By.ID, "first_name"),
            (By.ID, "firstname"),
            (By.ID, "first-name"),
            (By.NAME, "firstName"),
            (By.NAME, "first_name"),
            (By.NAME, "firstname"),
            (By.NAME, "first-name"),
            (By.XPATH, "//input[contains(@placeholder, 'First') or contains(@placeholder, 'first')]"),
            (By.XPATH, "//input[contains(@name, 'first') or contains(@id, 'first')]"),
            (By.XPATH, "//label[contains(text(), 'First Name') or contains(text(), 'First')]/following::input[1]"),
            (By.XPATH, "//label[contains(text(), 'First Name') or contains(text(), 'First')]/preceding::input[1]"),
            (By.XPATH, "//label[contains(., 'First Name') or contains(., 'First')]/ancestor::div[1]//input"),
            (By.XPATH, "//input[@type='text' or @type='search'][position()=1]"),  # First text input as fallback
        ]
        
        for by, value in first_name_selectors:
            try:
                elements = driver.find_elements(by, value)
                for elem in elements:
                    if elem.is_displayed() and elem.get_attribute('type') in [None, 'text', 'search']:
                        first_name_field = elem
                        print_with_timestamp(f"  Found first name field using: {by}={value}")
                        break
                if first_name_field:
                    break
            except Exception as e:
                continue
        
        # Try JavaScript as fallback - use JavaScript to find and interact with field directly
        if not first_name_field:
            try:
                # Check if element exists in DOM
                exists = driver.execute_script("return document.getElementById('FirstName') !== null;")
                if exists:
                    print_with_timestamp("  FirstName exists in DOM, using JavaScript to interact")
                    # Use JavaScript to set value directly
                    driver.execute_script("document.getElementById('FirstName').value = arguments[0];", first_name)
                    driver.execute_script("document.getElementById('FirstName').dispatchEvent(new Event('input', {bubbles: true}));")
                    driver.execute_script("document.getElementById('FirstName').dispatchEvent(new Event('change', {bubbles: true}));")
                    print_with_timestamp(f"  Set first name via JavaScript: {first_name}")
                    # Create a dummy element reference for consistency
                    first_name_field = driver.execute_script("return document.getElementById('FirstName');")
                else:
                    # Try other selectors
                    first_name_field = driver.execute_script("return document.querySelector('input[name=\"FirstName\"]') || document.querySelector('input#FirstName');")
                    if first_name_field:
                        print_with_timestamp("  Found first name field via JavaScript (alternative selector)")
            except Exception as e:
                print_with_timestamp(f"  [DEBUG] JavaScript fallback error: {e}")
                pass
        
        if not first_name_field:
            print_with_timestamp("  [ERROR] Could not find first name field")
            print_with_timestamp("  [DEBUG] Trying to find all text inputs...")
            try:
                text_inputs = driver.find_elements(By.XPATH, "//input[@type='text' or @type='search' or not(@type)]")
                print_with_timestamp(f"  [DEBUG] Found {len(text_inputs)} text inputs")
                if text_inputs:
                    print_with_timestamp("  [DEBUG] Using first text input as first name field")
                    first_name_field = text_inputs[0]
            except:
                pass
        
        if not first_name_field:
            print_with_timestamp("  [ERROR] Could not find first name field after all attempts")
            return False, None
        
        # Find last name field with comprehensive selectors
        last_name_field = None
        last_name_selectors = [
            (By.ID, "LastName"),  # Exact match from USEF site
            (By.NAME, "LastName"),  # Exact match from USEF site
            (By.ID, "lastName"),
            (By.ID, "last_name"),
            (By.ID, "lastname"),
            (By.ID, "last-name"),
            (By.NAME, "lastName"),
            (By.NAME, "last_name"),
            (By.NAME, "lastname"),
            (By.NAME, "last-name"),
            (By.XPATH, "//input[contains(@placeholder, 'Last') or contains(@placeholder, 'last')]"),
            (By.XPATH, "//input[contains(@name, 'last') or contains(@id, 'last')]"),
            (By.XPATH, "//label[contains(text(), 'Last Name') or contains(text(), 'Last')]/following::input[1]"),
            (By.XPATH, "//label[contains(text(), 'Last Name') or contains(text(), 'Last')]/preceding::input[1]"),
            (By.XPATH, "//label[contains(., 'Last Name') or contains(., 'Last')]/ancestor::div[1]//input"),
        ]
        
        for by, value in last_name_selectors:
            try:
                elements = driver.find_elements(by, value)
                for elem in elements:
                    if elem.is_displayed() and elem.get_attribute('type') in [None, 'text', 'search']:
                        # Make sure it's not the same field as first_name_field
                        if elem != first_name_field:
                            last_name_field = elem
                            print_with_timestamp(f"  Found last name field using: {by}={value}")
                            break
                if last_name_field:
                    break
            except Exception as e:
                continue
        
        # Try JavaScript as fallback
        if not last_name_field:
            try:
                last_name_field = driver.execute_script("return document.getElementById('LastName') || document.querySelector('input[name=\"LastName\"]') || document.querySelector('input#LastName');")
                if last_name_field:
                    print_with_timestamp("  Found last name field via JavaScript")
            except:
                pass
        
        # Fallback: if we have first_name_field, try to find the next text input
        if not last_name_field and first_name_field:
            try:
                # Get all text inputs and find the one after first_name_field
                text_inputs = driver.find_elements(By.XPATH, "//input[@type='text' or @type='search' or not(@type)]")
                first_idx = -1
                for i, inp in enumerate(text_inputs):
                    if inp == first_name_field:
                        first_idx = i
                        break
                if first_idx >= 0 and first_idx + 1 < len(text_inputs):
                    last_name_field = text_inputs[first_idx + 1]
                    print_with_timestamp(f"  Using second text input as last name field")
            except:
                pass
        
        if not last_name_field:
            print_with_timestamp("  [ERROR] Could not find last name field")
            return False, None
        
        # Fill in the fields
        # Check if we already set first name via JavaScript
        if first_name_field and hasattr(first_name_field, 'get_attribute'):
            try:
                current_value = first_name_field.get_attribute('value')
                if current_value != first_name:
                    first_name_field.clear()
                    first_name_field.send_keys(first_name)
                    print_with_timestamp(f"  Entered first name: {first_name}")
                else:
                    print_with_timestamp(f"  First name already set: {first_name}")
            except:
                # If Selenium interaction fails, use JavaScript
                driver.execute_script("document.getElementById('FirstName').value = arguments[0];", first_name)
                driver.execute_script("document.getElementById('FirstName').dispatchEvent(new Event('input', {bubbles: true}));")
                driver.execute_script("document.getElementById('FirstName').dispatchEvent(new Event('change', {bubbles: true}));")
                print_with_timestamp(f"  Set first name via JavaScript: {first_name}")
        else:
            # Use JavaScript directly
            driver.execute_script("document.getElementById('FirstName').value = arguments[0];", first_name)
            driver.execute_script("document.getElementById('FirstName').dispatchEvent(new Event('input', {bubbles: true}));")
            driver.execute_script("document.getElementById('FirstName').dispatchEvent(new Event('change', {bubbles: true}));")
            print_with_timestamp(f"  Set first name via JavaScript: {first_name}")
        
        # Set last name
        try:
            # Try JavaScript first
            exists = driver.execute_script("return document.getElementById('LastName') !== null;")
            if exists:
                driver.execute_script("document.getElementById('LastName').value = arguments[0];", last_name)
                driver.execute_script("document.getElementById('LastName').dispatchEvent(new Event('input', {bubbles: true}));")
                driver.execute_script("document.getElementById('LastName').dispatchEvent(new Event('change', {bubbles: true}));")
                print_with_timestamp(f"  Set last name via JavaScript: {last_name}")
            else:
                # Fallback to Selenium
                last_name_field.clear()
                last_name_field.send_keys(last_name)
                print_with_timestamp(f"  Entered last name: {last_name}")
        except:
            # Use JavaScript as final fallback
            driver.execute_script("document.getElementById('LastName').value = arguments[0];", last_name)
            driver.execute_script("document.getElementById('LastName').dispatchEvent(new Event('input', {bubbles: true}));")
            driver.execute_script("document.getElementById('LastName').dispatchEvent(new Event('change', {bubbles: true}));")
            print_with_timestamp(f"  Set last name via JavaScript: {last_name}")
        
        time.sleep(sleep_short)
        
        # Find and click search button
        search_button = None
        search_selectors = [
            (By.XPATH, "//input[@type='submit' and @value='Search' and @name='action']"),  # Exact match from USEF site
            (By.XPATH, "//input[@type='submit' and (@value='Search' or @value='search')]"),
            (By.XPATH, "//button[contains(text(), 'Search') or contains(text(), 'search')]"),
            (By.XPATH, "//button[@type='submit']"),
            (By.ID, "search"),
            (By.NAME, "search"),
            (By.XPATH, "//input[@type='submit']")
        ]
        
        for by, value in search_selectors:
            try:
                search_button = driver.find_element(by, value)
                if search_button.is_displayed():
                    break
            except NoSuchElementException:
                continue
        
        if not search_button:
            # Try JavaScript to find and click search button
            try:
                search_button_js = driver.execute_script("return document.querySelector('input[type=\"submit\"][value=\"Search\"][name=\"action\"]');")
                if search_button_js:
                    print_with_timestamp("  Found search button via JavaScript, clicking...")
                    driver.execute_script("arguments[0].click();", search_button_js)
                    print_with_timestamp("  Clicked search button via JavaScript")
                    time.sleep(sleep_medium)
                    return True
                else:
                    print_with_timestamp("  [ERROR] Could not find search button")
                    return False, None
            except Exception as e:
                print_with_timestamp(f"  [ERROR] Could not find search button: {e}")
                return False, None
        
        try:
            search_button.click()
            print_with_timestamp("  Clicked search button")
        except:
            # Fallback to JavaScript click
            try:
                driver.execute_script("arguments[0].click();", search_button)
                print_with_timestamp("  Clicked search button via JavaScript (fallback)")
            except:
                print_with_timestamp("  [ERROR] Could not click search button")
                return False, None
        
        time.sleep(sleep_medium)
        
        return True, None
        
    except (ReadTimeoutError, MaxRetryError, TimeoutError, WebDriverException) as e:
        error_msg = str(e).lower()
        is_tab_crash = 'tab crashed' in error_msg or 'session' in error_msg
        is_timeout = isinstance(e, (ReadTimeoutError, MaxRetryError, TimeoutError))
        
        if is_tab_crash:
            print_with_timestamp(f"  [WARNING] Browser tab crashed: {e}")
        elif is_timeout:
            print_with_timestamp(f"  [WARNING] Timeout error during search: {e}")
        else:
            print_with_timestamp(f"  [WARNING] WebDriver error during search: {e}")
        
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
                    return search_person(new_driver, first_name, last_name, sleep_short, sleep_medium, retry_auth=None, headless=headless)
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

def extract_person_info(driver, first_name, last_name, sleep_short=2, sleep_medium=3):
    """Extract person ID, state, and USEF status from the search results page
    
    Args:
        driver: WebDriver instance
        first_name: First name of the person to find ID for
        last_name: Last name of the person to find ID for
        sleep_short: Short sleep duration in seconds (default: 2)
        sleep_medium: Medium sleep duration in seconds (default: 3)
    
    Returns:
        Dictionary with 'id', 'state', and 'usef_status' keys, or None if not found
    """
    print_with_timestamp(f"\nExtracting person information from results for {first_name} {last_name}...")
    
    try:
        # Wait for results to load
        time.sleep(sleep_medium)
        
        # Try various strategies to find the person info
        person_info = {
            'id': None,
            'state': None,
            'usef_status': None
        }
        
        # Strategy 0: Look for result rows matching the person's name, then extract ID from first <td>
        # The ID is in the first column of the table row
        try:
            # Look for table rows in tbody that contain the person's name
            # Note: Name format might be "LASTNAME, FIRSTNAME" or "FIRSTNAME LASTNAME"
            result_row_selectors = [
                f"//table//tbody//tr[contains(., '{last_name}') and contains(., '{first_name}')]",
                f"//tr[contains(., '{last_name}') and contains(., '{first_name}')]",
                f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{last_name.lower()}') and contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{first_name.lower()}')]/ancestor::tr[1]",
            ]
            
            result_row = None
            for selector in result_row_selectors:
                try:
                    rows = driver.find_elements(By.XPATH, selector)
                    for row in rows:
                        try:
                            row_text = row.text
                            row_text_upper = row_text.upper()
                            
                            # Name format is "LASTNAME, FIRSTNAME" followed by "State: <state>"
                            # Must match last name exactly (case-insensitive)
                            # First name can be partial match (e.g., "Ari" matches "Arianna")
                            last_name_upper = last_name.upper()
                            first_name_upper = first_name.upper()
                            
                            # Check if last name is present (must be exact match, case-insensitive)
                            has_last_name = last_name_upper in row_text_upper
                            
                            # Check if first name is present (partial match OK, e.g., "ARI" matches "ARIANNA")
                            has_first_name = first_name_upper in row_text_upper
                            
                            # Also check for comma-separated format "LASTNAME, FIRSTNAME"
                            # The row should contain "LASTNAME," (with comma) followed by first name
                            comma_format = f"{last_name_upper}," in row_text_upper or f", {first_name_upper}" in row_text_upper
                            
                            if has_last_name and has_first_name:
                                result_row = row
                                print_with_timestamp(f"  Found result row for {first_name} {last_name} (matched in: {row_text[:100]})")
                                break
                        except Exception as e:
                            print_with_timestamp(f"  [DEBUG] Error checking row: {e}")
                            continue
                    if result_row:
                        break
                except:
                    continue
            
            if result_row:
                # Extract ID from the first <td> element in the row
                try:
                    first_td = result_row.find_element(By.XPATH, "./td[1]")
                    if first_td:
                        id_text = first_td.text.strip()
                        # Extract numeric ID (remove any whitespace)
                        id_match = re.search(r'(\d+)', id_text)
                        if id_match:
                            person_info['id'] = id_match.group(1)
                            print_with_timestamp(f"  Found ID from first table cell: {person_info['id']}")
                        else:
                            print_with_timestamp(f"  [DEBUG] First TD text doesn't contain numeric ID: '{id_text}'")
                except Exception as e:
                    print_with_timestamp(f"  [DEBUG] Error extracting ID from first TD: {e}")
                    pass
                
                # Extract State from the second <td> element (column 2: Name/Location)
                # Format: "LASTNAME, FIRSTNAME\nState: <state>"
                try:
                    second_td = result_row.find_element(By.XPATH, "./td[2]")
                    if second_td:
                        location_text = second_td.text
                        # Look for "State: <state>" pattern
                        state_match = re.search(r'State:\s*([A-Z]{2})', location_text, re.IGNORECASE)
                        if state_match:
                            person_info['state'] = state_match.group(1).upper()
                            print_with_timestamp(f"  Found State: {person_info['state']}")
                        else:
                            print_with_timestamp(f"  [DEBUG] Could not extract state from: '{location_text[:100]}'")
                except Exception as e:
                    print_with_timestamp(f"  [DEBUG] Error extracting State from second TD: {e}")
                    pass
                
                # Extract USEF Status from the fourth <td> element (column 4: USEF Status)
                try:
                    fourth_td = result_row.find_element(By.XPATH, "./td[4]")
                    if fourth_td:
                        status_text = fourth_td.text.strip()
                        if status_text:
                            person_info['usef_status'] = status_text
                            print_with_timestamp(f"  Found USEF Status: {person_info['usef_status'][:80]}")
                        else:
                            print_with_timestamp(f"  [DEBUG] USEF Status column is empty")
                except Exception as e:
                    print_with_timestamp(f"  [DEBUG] Error extracting USEF Status from fourth TD: {e}")
                    pass
                
                # If ID not found in first TD, try other methods as fallback
                if not person_info['id']:
                    # Look for links in the row that contain ID
                    try:
                        links = result_row.find_elements(By.XPATH, ".//a[contains(@href, 'id=') or contains(@href, 'ID=')]")
                        for link in links:
                            href = link.get_attribute('href')
                            if href:
                                parsed = urllib.parse.urlparse(href)
                                params = urllib.parse.parse_qs(parsed.query)
                                if 'id' in params:
                                    person_info['id'] = params['id'][0]
                                    print_with_timestamp(f"  Found ID from result row link: {person_info['id']}")
                                    break
                                elif 'ID' in params:
                                    person_info['id'] = params['ID'][0]
                                    print_with_timestamp(f"  Found ID from result row link: {person_info['id']}")
                                    break
                    except:
                        pass
        except Exception as e:
            print_with_timestamp(f"  [DEBUG] Error in result row strategy: {e}")
        
        # Strategy 1: Look for ID in URL parameters (only if not found via result row)
        if not person_info['id']:
            current_url = driver.current_url
            if 'id=' in current_url or 'ID=' in current_url:
                parsed = urllib.parse.urlparse(current_url)
                params = urllib.parse.parse_qs(parsed.query)
                if 'id' in params:
                    person_info['id'] = params['id'][0]
                elif 'ID' in params:
                    person_info['id'] = params['ID'][0]
        
        # Strategy 2: Look for ID in page source (common patterns)
        if not person_info['id']:
            page_source = driver.page_source
            # Look for patterns like: "ID: 12345" or "Person ID: 12345" or data-id="12345"
            id_patterns = [
                r'(?:Person\s+)?ID[:\s]+(\d+)',
                r'data-id=["\'](\d+)["\']',
                r'id["\']?\s*[:=]\s*["\']?(\d+)["\']?',
                r'"id"\s*:\s*"?(\d+)"?'
            ]
            for pattern in id_patterns:
                match = re.search(pattern, page_source, re.IGNORECASE)
                if match:
                    person_info['id'] = match.group(1)
                    break
        
        # Strategy 3: Look for ID in visible text elements
        if not person_info['id']:
            try:
                # Look for elements containing "ID" followed by numbers
                id_elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'ID')]")
                for elem in id_elements:
                    text = elem.text
                    match = re.search(r'ID[:\s]+(\d+)', text, re.IGNORECASE)
                    if match:
                        person_info['id'] = match.group(1)
                        break
            except:
                pass
        
        # Strategy 4: Look for ID in table cells or data attributes
        if not person_info['id']:
            try:
                # Look for data attributes
                id_elem = driver.find_element(By.XPATH, "//*[@data-id or @data-person-id or @data-user-id]")
                person_info['id'] = (id_elem.get_attribute('data-id') or 
                           id_elem.get_attribute('data-person-id') or 
                           id_elem.get_attribute('data-user-id'))
            except:
                pass
        
        # Strategy 5: Look for ID in result links
        if not person_info['id']:
            try:
                result_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'id=') or contains(@href, 'ID=')]")
                for link in result_links:
                    href = link.get_attribute('href')
                    if href and ('id=' in href or 'ID=' in href):
                        parsed = urllib.parse.urlparse(href)
                        params = urllib.parse.parse_qs(parsed.query)
                        if 'id' in params:
                            person_info['id'] = params['id'][0]
                            break
                        elif 'ID' in params:
                            person_info['id'] = params['ID'][0]
                            break
            except:
                pass
        
        if person_info['id']:
            print_with_timestamp(f"  [OK] Found person information:")
            print_with_timestamp(f"    ID: {person_info['id']}")
            if person_info['state']:
                print_with_timestamp(f"    State: {person_info['state']}")
            if person_info['usef_status']:
                usef_status_str = person_info['usef_status']
                if usef_status_str:
                    print_with_timestamp(f"    USEF Status: {usef_status_str[:80]}")
            return person_info
        else:
            print_with_timestamp("  [WARNING] Could not extract person ID from results")
            print_with_timestamp(f"  Current URL: {driver.current_url}")
            # Print page title for debugging
            try:
                print_with_timestamp(f"  Page title: {driver.title}")
            except:
                pass
            return None
            
    except Exception as e:
        print_with_timestamp(f"  [ERROR] Error extracting person ID: {e}")
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

def parse_name_into_first_last(full_name):
    """Parse a full name into first and last name
    
    Note: Competitors table stores Rider names as "LastName, FirstName" format
    
    Args:
        full_name: Full name string in "LastName, FirstName" format (e.g., "Smith, John")
                   Also handles "FirstName LastName" format as fallback
    
    Returns:
        Tuple of (first_name, last_name) or (None, None) if parsing fails
    """
    if not full_name or not full_name.strip():
        return None, None
    
    full_name = full_name.strip()
    
    # Primary format: "LastName, FirstName" (used in Competitors table)
    if ',' in full_name:
        parts = [p.strip() for p in full_name.split(',', 1)]
        if len(parts) == 2:
            last_name = parts[0]  # Part before comma is LastName
            first_name = parts[1]  # Part after comma is FirstName
            if first_name and last_name:
                return first_name, last_name
    
    # Fallback format: "FirstName LastName" (in case some entries don't use comma)
    parts = full_name.split()
    if len(parts) == 1:
        # Only one name provided, treat as last name
        return None, parts[0]
    elif len(parts) >= 2:
        # Take first part as first name, rest as last name
        # This handles "Mary Jane Watson" -> "Mary Jane", "Watson"
        first_name = parts[0]
        last_name = ' '.join(parts[1:])
        return first_name, last_name
    
    return None, None

def ensure_rider_usef_columns_exist(conn):
    """Ensure RiderUSEFID, RiderState, and RiderUSEFStatus columns exist in Competitors table
    
    Args:
        conn: Database connection
    
    Returns:
        True if columns exist or were created, False otherwise
    """
    cursor = conn.cursor()
    try:
        # Check if RiderUSEFID column exists
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
                # Add columns after Rider column
                cursor.execute("""
                    ALTER TABLE sResults.Competitors 
                    ADD RiderUSEFID NVARCHAR(50),
                        RiderState NVARCHAR(10),
                        RiderUSEFStatus NVARCHAR(500)
                """)
                conn.commit()
                print_with_timestamp("[OK] Added RiderUSEFID, RiderState, and RiderUSEFStatus columns")
                return True
            except Exception as e:
                print_with_timestamp(f"[ERROR] Error adding new columns: {e}")
                conn.rollback()
                return False
        else:
            print_with_timestamp("[OK] RiderUSEFID, RiderState, and RiderUSEFStatus columns already exist")
            return True
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error checking/creating columns: {e}")
        return False
    finally:
        cursor.close()

def update_competitors_from_usef(conn, driver, headless=True, start_from_rider=None):
    """Update Competitors table with USEF information for all riders
    
    Args:
        conn: Database connection
        driver: WebDriver instance (will be created if None)
        headless: Run browser in headless mode (default: True)
        start_from_rider: Rider name to start from (format: "LastName, FirstName"). 
                         All riders before this one will be skipped.
    
    Returns:
        Tuple of (number of riders updated, driver instance). Driver may be replaced if reconnection occurred.
    """
    print_with_timestamp("\nUpdating Competitors table with USEF information...")
    
    # Ensure columns exist before proceeding
    if not ensure_rider_usef_columns_exist(conn):
        print_with_timestamp("[ERROR] Could not ensure columns exist, aborting")
        return 0, driver
    
    cursor = conn.cursor()
    try:
        # Get all unique Rider names from Competitors table
        # Rider format: "LastName, FirstName"
        # Skip rows where Rider is NULL
        cursor.execute("""
            SELECT DISTINCT Rider 
            FROM sResults.Competitors 
            WHERE Rider IS NOT NULL AND Rider != ''
            ORDER BY Rider
        """)
        
        riders = [row[0] for row in cursor.fetchall()]
        print_with_timestamp(f"Found {len(riders)} unique riders to process (format: LastName, FirstName)")
        
        if len(riders) == 0:
            print_with_timestamp("No riders found in Competitors table")
            return 0, driver
        
        # Skip to start_from_rider if specified
        start_index = 0
        total_riders = len(riders)
        if start_from_rider:
            try:
                start_index = riders.index(start_from_rider)
                riders = riders[start_index:]
                print_with_timestamp(f"Starting from rider: {start_from_rider} (skipped {start_index} riders)")
            except ValueError:
                print_with_timestamp(f"[WARNING] Rider '{start_from_rider}' not found in list. Starting from beginning.")
                print_with_timestamp(f"  Available riders start with: {riders[0] if riders else 'N/A'}")
                start_index = 0
        
        updated_count = 0
        failed_count = 0
        
        # Navigate to USEF search page and authenticate once
        search_url = "https://www.usef.org/search/people"
        auth_success, auth_username, auth_password = check_and_authenticate(driver, search_url)
        
        if not auth_success:
            print_with_timestamp("[ERROR] Authentication failed, cannot continue")
            return 0, driver
        
                # Store credentials for retry on timeout (include headless flag)
        retry_auth = (search_url, auth_username, auth_password)
        
        # Calculate starting index for display
        start_display_idx = start_index + 1
        
        # Process each rider
        for idx, rider_name in enumerate(riders, start_display_idx):
            try:
                print_with_timestamp(f"\n[{idx}/{total_riders}] Processing rider: {rider_name}")
                
                # Skip if already has USEF ID
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM sResults.Competitors 
                    WHERE Rider = ? AND RiderUSEFID IS NOT NULL AND RiderUSEFID != ''
                """, rider_name)
                
                if cursor.fetchone()[0] > 0:
                    print_with_timestamp(f"  Skipping {rider_name} - already has USEF ID")
                    continue
                
                # Parse name into first and last
                first_name, last_name = parse_name_into_first_last(rider_name)
                
                if not first_name or not last_name:
                    print_with_timestamp(f"  [WARNING] Could not parse name '{rider_name}' into first/last name")
                    failed_count += 1
                    continue
                
                print_with_timestamp(f"  Parsed as: First='{first_name}', Last='{last_name}'")
                
                # Search for the person (with retry auth info)
                search_success, new_driver = search_person(driver, first_name, last_name, retry_auth=retry_auth, headless=headless)
                if new_driver:
                    driver = new_driver  # Update driver reference if reconnection occurred
                if not search_success:
                    print_with_timestamp(f"  [WARNING] Search failed for {rider_name}, trying reversed names...")
                    # Try reversing first and last name
                    first_name_reversed = last_name
                    last_name_reversed = first_name
                    print_with_timestamp(f"  Trying reversed: First='{first_name_reversed}', Last='{last_name_reversed}'")
                    search_success, new_driver = search_person(driver, first_name_reversed, last_name_reversed, retry_auth=retry_auth, headless=headless)
                    if new_driver:
                        driver = new_driver  # Update driver reference if reconnection occurred
                    if search_success:
                        first_name = first_name_reversed
                        last_name = last_name_reversed
                    else:
                        print_with_timestamp(f"  [WARNING] Search failed for {rider_name} with reversed names")
                        failed_count += 1
                        time.sleep(2)
                        continue
                
                # Extract person information
                person_info = extract_person_info(driver, first_name, last_name)
                
                # Check if we got valid person info and reject dummy ID 5340935
                person_id = person_info.get('id') if person_info else None
                tried_reversed = False
                
                if person_id == '5340935':
                    print_with_timestamp(f"  [WARNING] Rejected dummy USEF ID 5340935 for {rider_name}, trying reversed names...")
                    # Try reversing first and last name
                    first_name_reversed = last_name
                    last_name_reversed = first_name
                    print_with_timestamp(f"  Trying reversed: First='{first_name_reversed}', Last='{last_name_reversed}'")
                    search_success, new_driver = search_person(driver, first_name_reversed, last_name_reversed, retry_auth=retry_auth, headless=headless)
                    if new_driver:
                        driver = new_driver  # Update driver reference if reconnection occurred
                    if search_success:
                        first_name = first_name_reversed
                        last_name = last_name_reversed
                        tried_reversed = True
                        # Extract person information again with reversed names
                        person_info = extract_person_info(driver, first_name, last_name)
                        person_id = person_info.get('id') if person_info else None
                        # Check again if we still got the dummy ID
                        if person_id == '5340935':
                            print_with_timestamp(f"  [WARNING] Still got dummy USEF ID 5340935 with reversed names")
                            person_info = None
                    else:
                        print_with_timestamp(f"  [WARNING] Search failed for {rider_name} with reversed names")
                        person_info = None
                
                if person_info and person_id and person_id != '5340935':
                    # Update all rows with this rider name
                    usef_status = person_info.get('usef_status') or ''
                    cursor.execute("""
                        UPDATE sResults.Competitors 
                        SET RiderUSEFID = ?,
                            RiderState = ?,
                            RiderUSEFStatus = ?,
                            UpdatedDate = GETDATE()
                        WHERE Rider = ?
                    """, 
                        person_id,
                        person_info.get('state'),
                        usef_status,
                        rider_name
                    )
                    conn.commit()
                    updated_rows = cursor.rowcount
                    updated_count += updated_rows
                    status_display = usef_status[:50] if usef_status else '(empty)'
                    reversal_note = " (with reversed names)" if tried_reversed else ""
                    print_with_timestamp(f"  [OK] Updated {updated_rows} row(s) for {rider_name}{reversal_note}")
                    print_with_timestamp(f"    USEF ID: {person_id}, State: {person_info.get('state')}, Status: {status_display}")
                else:
                    print_with_timestamp(f"  [WARNING] Could not find valid USEF information for {rider_name}")
                    failed_count += 1
                
                # Small delay between searches to avoid overwhelming the server
                time.sleep(3)
                
            except Exception as e:
                print_with_timestamp(f"  [ERROR] Error processing {rider_name}: {e}")
                import traceback
                traceback.print_exc()
                failed_count += 1
                conn.rollback()
                continue
        
        print_with_timestamp(f"\n{'='*60}")
        print_with_timestamp(f"Update complete!")
        print_with_timestamp(f"  Successfully updated: {updated_count} riders")
        print_with_timestamp(f"  Failed/Skipped: {failed_count} riders")
        print_with_timestamp(f"{'='*60}\n")
        
        return updated_count, driver
        
    except Exception as e:
        print_with_timestamp(f"[ERROR] Error updating competitors: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        return 0, driver
    finally:
        cursor.close()

def main(first_name="Ari", last_name="Waelterman", headless=True, update_all_riders=False, start_from_rider=None):
    """Main function to search for a person on USEF website or update all riders in Competitors table
    
    Args:
        first_name: First name to search for (default: "Ari")
        last_name: Last name to search for (default: "Waelterman")
        headless: Run browser in headless mode (default: True)
        update_all_riders: If True, update all riders in Competitors table with USEF information (default: False)
        start_from_rider: Rider name to start from when updating all riders (format: "LastName, FirstName")
    """
    print_with_timestamp("\n" + "=" * 60)
    print_with_timestamp("USEF Person Search Scraper")
    print_with_timestamp("=" * 60 + "\n")
    
    driver = None
    conn = None
    
    try:
        # Setup driver
        print_with_timestamp("Initializing browser...")
        driver = setup_driver(headless=headless)
        print_with_timestamp("  [OK] Browser initialized\n")
        
        # If update_all_riders is True, connect to database and update all riders
        if update_all_riders:
            print_with_timestamp("Connecting to database...")
            conn = get_db_connection()
            print_with_timestamp("[OK] Connected to database\n")
            
            # Update all riders
            updated_count, driver = update_competitors_from_usef(conn, driver, headless=headless, start_from_rider=start_from_rider)
            return
        
        # Otherwise, do single person search
        # Navigate to search page and handle authentication
        search_url = "https://www.usef.org/search/people"
        auth_success, auth_username, auth_password = check_and_authenticate(driver, search_url)
        
        # If authentication was not needed (already logged in), ensure we're on the right page
        if auth_success:
            current_url = driver.current_url
            if 'search/people' not in current_url.lower():
                print_with_timestamp("  Ensuring we're on People search page...")
                navigate_to_people_search(driver, search_url)
        else:
            print_with_timestamp("[ERROR] Authentication failed")
            return
        
        # Search for the person (with retry auth info)
        retry_auth = (search_url, auth_username, auth_password)
        search_success, new_driver = search_person(driver, first_name, last_name, retry_auth=retry_auth, headless=headless)
        if new_driver:
            driver = new_driver  # Update driver reference if reconnection occurred
        if not search_success:
            print_with_timestamp("[ERROR] Search failed")
            return
        
        # Extract person information (ID, state, USEF status)
        person_info = extract_person_info(driver, first_name, last_name)
        
        if person_info and person_info.get('id'):
            print_with_timestamp(f"\n{'='*60}")
            print_with_timestamp(f"Person Information:")
            print_with_timestamp(f"  ID: {person_info['id']}")
            if person_info.get('state'):
                print_with_timestamp(f"  State: {person_info['state']}")
            if person_info.get('usef_status'):
                print_with_timestamp(f"  USEF Status: {person_info['usef_status']}")
            print_with_timestamp(f"{'='*60}\n")
            return person_info
        else:
            print_with_timestamp("\n[WARNING] Could not find person information")
            return None
            
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
    first_name = "Ari"
    last_name = "Waelterman"
    headless = True
    update_all_riders = False
    start_from_rider = None
    
    # Parse command-line arguments
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i].lower()
        
        if arg in ['--first-name', '-f']:
            if i + 1 < len(sys.argv):
                first_name = sys.argv[i + 1]
                i += 1
            else:
                print_with_timestamp("[ERROR] --first-name requires a value")
                sys.exit(1)
        elif arg in ['--last-name', '-l']:
            if i + 1 < len(sys.argv):
                last_name = sys.argv[i + 1]
                i += 1
            else:
                print_with_timestamp("[ERROR] --last-name requires a value")
                sys.exit(1)
        elif arg in ['--no-headless', '--visible']:
            headless = False
        elif arg in ['--update-all', '--update-riders', '-u']:
            update_all_riders = True
        elif arg in ['--start-from', '--skip-to', '-s']:
            if i + 1 < len(sys.argv):
                start_from_rider = sys.argv[i + 1]
                i += 1
            else:
                print_with_timestamp("[ERROR] --start-from requires a rider name (format: 'LastName, FirstName')")
                sys.exit(1)
        elif arg in ['--help', '-h']:
            print_with_timestamp("Usage: python scrape_usef_person.py [OPTIONS]")
            print_with_timestamp("Options:")
            print_with_timestamp("  --first-name NAME, -f NAME: First name to search for (default: Ari)")
            print_with_timestamp("  --last-name NAME, -l NAME: Last name to search for (default: Waelterman)")
            print_with_timestamp("  --no-headless, --visible: Run browser in visible mode (default: headless)")
            print_with_timestamp("  --update-all, --update-riders, -u: Update all riders in Competitors table with USEF information")
            print_with_timestamp("  --start-from RIDER, --skip-to RIDER, -s RIDER: Start processing from this rider (format: 'LastName, FirstName')")
            sys.exit(0)
        
        i += 1
    
    main(first_name=first_name, last_name=last_name, headless=headless, update_all_riders=update_all_riders, start_from_rider=start_from_rider)

