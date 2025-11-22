"""
Enhanced browser automation service with Playwright MCP integration
"""

from typing import Dict, Any, Optional, Union, List
from pathlib import Path
import time
import json
import asyncio
import inspect

# Playwright imports
try:
    from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None
    Browser = None
    BrowserContext = None

# Selenium imports (fallback)
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from ..core.config import ConfigManager


class PlaywrightMCPBridge:
    """Bridge for Playwright MCP integration"""
    
    def __init__(self, page: Page = None):
        self.page = page
        self.recording_actions = []
        self.mcp_mode = False
    
    def enable_mcp_mode(self):
        """Enable MCP mode for enhanced automation"""
        self.mcp_mode = True
        self.recording_actions = []
    
    def disable_mcp_mode(self):
        """Disable MCP mode"""
        self.mcp_mode = False
    
    def record_action(self, action: str, **kwargs):
        """Record action for MCP integration"""
        if self.mcp_mode:
            action_data = {
                'action': action,
                'timestamp': time.time(),
                'parameters': kwargs
            }
            self.recording_actions.append(action_data)
    
    def get_recorded_actions(self) -> List[Dict[str, Any]]:
        """Get all recorded actions"""
        return self.recording_actions.copy()
    
    def export_to_easy_bdd(self) -> Dict[str, Any]:
        """Export recorded actions to Easy BDD format"""
        steps = []
        
        for action_data in self.recording_actions:
            action = action_data['action']
            params = action_data['parameters']
            
            if action == 'navigate':
                steps.append({
                    'action': 'Open browser',
                    'url': params.get('url')
                })
            elif action == 'click':
                step = {'action': 'Click element'}
                if 'selector' in params:
                    step['selector'] = params['selector']
                elif 'text' in params:
                    step['text'] = params['text']
                steps.append(step)
            elif action == 'fill':
                steps.append({
                    'action': 'Fill form field',
                    'field': params.get('field', params.get('selector')),
                    'value': params.get('value')
                })
            elif action == 'screenshot':
                steps.append({
                    'action': 'Take screenshot',
                    'name': params.get('name', 'screenshot')
                })
        
        return {
            'name': 'Recorded Test',
            'description': 'Auto-generated from MCP recording',
            'tags': ['browser', 'mcp-recorded'],
            'steps': steps
        }


class BrowserService:
    """Enhanced service for browser automation with MCP integration"""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.selenium_driver: Optional[webdriver.Remote] = None
        self.playwright_browser: Optional[Browser] = None
        self.playwright_page: Optional[Page] = None
        self.playwright_context: Optional[BrowserContext] = None
        self.playwright_playwright = None
        self.screenshots_dir = Path(config.get("reporting.output_dir")) / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # MCP Bridge
        self.mcp_bridge = PlaywrightMCPBridge()
        
        # Preferred browser engine
        self.preferred_engine = "playwright" if PLAYWRIGHT_AVAILABLE else "selenium"
    
    def set_mcp_mode(self, enabled: bool = True):
        """Enable or disable MCP mode for recording"""
        if enabled:
            self.mcp_bridge.enable_mcp_mode()
        else:
            self.mcp_bridge.disable_mcp_mode()
    
    def get_mcp_recording(self) -> Dict[str, Any]:
        """Get MCP recording in Easy BDD format"""
        return self.mcp_bridge.export_to_easy_bdd()
    
    def save_mcp_recording(self, file_path: Union[str, Path]):
        """Save MCP recording to file"""
        recording = self.get_mcp_recording()
        
        file_path = Path(file_path)
        if file_path.suffix.lower() == '.json':
            with open(file_path, 'w') as f:
                json.dump(recording, f, indent=2)
        else:
            # Save as YAML
            import yaml
            with open(file_path, 'w') as f:
                yaml.dump(recording, f, default_flow_style=False)
    
    def open_browser(self, url: str, browser: str = None, use_playwright: bool = None) -> None:
        """Open browser and navigate to URL"""
        browser = browser or getattr(self.config.browser, 'default', 'chrome')
        
        # Auto-detect best engine
        if use_playwright is None:
            use_playwright = self.preferred_engine == "playwright"
        
        if use_playwright and PLAYWRIGHT_AVAILABLE:
            self._open_playwright_browser(url, browser)
        elif SELENIUM_AVAILABLE:
            self._open_selenium_browser(url, browser)
        else:
            raise RuntimeError("No browser automation library available. Install Playwright or Selenium.")
        
        # Record action for MCP
        self.mcp_bridge.record_action('navigate', url=url, browser=browser)
    
    def _open_playwright_browser(self, url: str, browser: str) -> None:
        """Open browser using Playwright with enhanced MCP integration"""
        if self.playwright_browser:
            self.playwright_browser.close()
        
        self.playwright_playwright = sync_playwright().start()
        
        # Browser launch options
        launch_options = {
            'headless': getattr(self.config.browser, 'headless', False),
            'args': [
                '--no-sandbox',
                '--disable-dev-shm-usage',  # Better Docker compatibility
            ]
        }
        
        # Add HTTPS certificate handling
        ignore_https = (getattr(self.config.browser, 'ignore_https_errors', False) or 
                       getattr(self.config.browser, 'ignore_certificate_errors', False))
        if ignore_https:
            launch_options['args'].extend([
                '--ignore-certificate-errors',
                '--ignore-ssl-errors',
                '--ignore-certificate-errors-spki-list',
                '--ignore-ssl-errors-on-localhost',
                '--allow-running-insecure-content',
                '--disable-web-security'
            ])
        
        # Add configured browser args
        browser_args = getattr(self.config.browser, 'args', [])
        if browser_args:
            launch_options['args'].extend(browser_args)
        
        # Add debugging options for MCP mode
        if self.mcp_bridge.mcp_mode:
            launch_options['slow_mo'] = 50  # Slow down for better observation
            launch_options['devtools'] = not getattr(self.config.browser, 'headless', False)
        
        browser_type = getattr(self.playwright_playwright, self._get_playwright_browser_name(browser))
        self.playwright_browser = browser_type.launch(**launch_options)
        
        # Create context with enhanced options
        context_options = {
            'viewport': {
                "width": getattr(self.config.browser, 'window_size', [1920, 1080])[0],
                "height": getattr(self.config.browser, 'window_size', [1920, 1080])[1]
            },
            'record_video_dir': str(self.screenshots_dir / "videos") if getattr(self.config.reporting, 'video', False) else None,
            'record_har_path': str(self.screenshots_dir / "network.har") if self.mcp_bridge.mcp_mode else None,
            'ignore_https_errors': getattr(self.config.browser, 'ignore_https_errors', True),
            'accept_downloads': True
        }
        
        self.playwright_context = self.playwright_browser.new_context(**context_options)
        
        # Enable request/response interception for MCP mode
        if self.mcp_bridge.mcp_mode:
            self.playwright_context.route("**/*", self._handle_route)
        
        self.playwright_page = self.playwright_context.new_page()
        
        # Set MCP bridge page reference
        self.mcp_bridge.page = self.playwright_page
        
        # Enhanced error handling and retry logic
        try:
            self.playwright_page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception as e:
            print(f"Navigation warning: {e}")
            # Fallback navigation
            self.playwright_page.goto(url, wait_until='domcontentloaded')
    
    def _handle_route(self, route, request):
        """Handle network routes for MCP mode"""
        # Log network requests in MCP mode
        if self.mcp_bridge.mcp_mode:
            self.mcp_bridge.record_action('network_request', 
                                        url=request.url, 
                                        method=request.method,
                                        resource_type=request.resource_type)
        
        # Continue with the request
        route.continue_()
    
    def _open_selenium_browser(self, url: str, browser: str) -> None:
        """Open browser using Selenium (fallback)"""
        if self.selenium_driver:
            self.selenium_driver.quit()
        
        if browser.lower() == "chrome":
            options = ChromeOptions()
            
            # Headless mode
            if self.config.get("browser.headless", False):
                options.add_argument("--headless")
            
            # Window size
            window_size = self.config.get("browser.window_size", [1920, 1080])
            options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
            
            # HTTPS certificate handling
            if self.config.get("browser.ignore_https_errors", False) or self.config.get("browser.ignore_certificate_errors", False):
                options.add_argument("--ignore-certificate-errors")
                options.add_argument("--ignore-ssl-errors")
                options.add_argument("--ignore-certificate-errors-spki-list")
                options.add_argument("--allow-running-insecure-content")
                options.add_argument("--disable-web-security")
            
            # Add configured browser args
            browser_args = self.config.get("browser.args", [])
            for arg in browser_args:
                options.add_argument(arg)
            
            self.selenium_driver = webdriver.Chrome(options=options)
            
        elif browser.lower() == "firefox":
            options = FirefoxOptions()
            
            # Headless mode
            if self.config.get("browser.headless", False):
                options.add_argument("--headless")
            
            # HTTPS certificate handling
            if self.config.get("browser.ignore_https_errors", False) or self.config.get("browser.ignore_certificate_errors", False):
                options.set_preference("security.tls.insecure_fallback_hosts", "*")
                options.set_preference("security.tls.unrestricted_rc4_fallback", True)
                options.set_preference("security.mixed_content.block_active_content", False)
                options.set_preference("security.mixed_content.block_display_content", False)
            
            self.selenium_driver = webdriver.Firefox(options=options)
            
        else:
            raise ValueError(f"Unsupported browser: {browser}")
        
        self.selenium_driver.implicitly_wait(self.config.get("browser.implicit_wait", 10))
        self.selenium_driver.get(url)
    
    def _get_playwright_browser_name(self, browser: str) -> str:
        """Map browser names to Playwright browser types"""
        browser_map = {
            'chrome': 'chromium',
            'chromium': 'chromium', 
            'firefox': 'firefox',
            'safari': 'webkit',
            'edge': 'chromium',
            'webkit': 'webkit'
        }
        return browser_map.get(browser.lower(), 'chromium')
    
    def _is_xpath_selector(self, selector: str) -> bool:
        """Check if selector is an XPath expression"""
        if not selector:
            return False
        
        # Common XPath indicators
        xpath_indicators = [
            selector.startswith('//'),
            selector.startswith('./'),
            selector.startswith('(//'),
            selector.startswith('(.//'),
            '//' in selector,
            'normalize-space(' in selector,
            'following::' in selector,
            'preceding::' in selector,
            'ancestor::' in selector,
            'descendant::' in selector
        ]
        
        return any(xpath_indicators)
    
    def _normalize_xpath_selector(self, selector: str) -> str:
        """Normalize XPath selector for Playwright"""
        if not selector:
            return selector
        
        # Remove xpath= prefix if present
        if selector.startswith('xpath='):
            selector = selector[6:]
        
        # Ensure XPath starts with // or . if it's a relative path
        if not selector.startswith(('/', '.', '(')):
            selector = f'//{selector}'
        
        return selector
    
    def _suggest_alternative_selectors(self, failed_selector: str) -> None:
        """Suggest alternative selectors when XPath fails"""
        try:
            # Look for text content that might help
            if 'STOPPED' in failed_selector:
                # Try to find elements containing "STOPPED"
                elements = self.playwright_page.query_selector_all('text="STOPPED"')
                if elements:
                    print(f"      Found {len(elements)} elements with 'STOPPED' text")
            
            # Get all clickable elements for debugging
            clickable = self.playwright_page.query_selector_all('a, button, [role="button"], [onclick]')
            if clickable:
                texts = []
                for elem in clickable[:5]:  # Limit to first 5
                    text = elem.text_content()
                    if text and text.strip():
                        texts.append(text.strip()[:20])  # Limit text length
                if texts:
                    print(f"      Available clickable elements: {', '.join(texts)}")
        except Exception:
            pass
    
    def click_element(self, selector: str = None, text: str = None, button: str = None, **kwargs) -> None:
        """Enhanced click with multiple selector strategies"""
        if self.playwright_page:
            self._playwright_click(selector, text, button, **kwargs)
        elif self.selenium_driver:
            self._selenium_click(selector, text, button)
        else:
            raise RuntimeError("No browser session active")
        
        # Record action for MCP
        self.mcp_bridge.record_action('click', selector=selector, text=text, button=button, **kwargs)
    
    def _playwright_click(self, selector: str = None, text: str = None, button: str = None, **kwargs) -> None:
        """Enhanced Playwright click with XPath support"""
        click_options = kwargs.copy()
        
        if button:
            click_options['button'] = button
        
        try:
            if selector:
                print(f"      Processing selector: {selector}")
                print(f"      Is XPath: {self._is_xpath_selector(selector)}")
                
                # Handle XPath selectors
                if self._is_xpath_selector(selector):
                    xpath_selector = self._normalize_xpath_selector(selector)
                    print(f"      Using XPath: {xpath_selector}")
                    self.playwright_page.click(f"xpath={xpath_selector}", timeout=10000, **click_options)
                    return
                else:
                    # Try direct CSS selector
                    self.playwright_page.click(selector, timeout=5000, **click_options)
                    return
                    
            elif text:
                # Click by text content
                self.playwright_page.click(f"text={text}", **click_options)
                return
                
            elif button:
                # Try multiple button selectors
                selectors_to_try = [
                    f"button:has-text('{button}')",
                    f"input[type='submit'][value='{button}']",
                    f"input[type='button'][value='{button}']",
                    f"[role='button']:has-text('{button}')",
                    f"a:has-text('{button}')",
                    f"*:has-text('{button}'):visible"
                ]
                
                for sel in selectors_to_try:
                    try:
                        self.playwright_page.click(sel, timeout=2000, **click_options)
                        return
                    except Exception:
                        continue
                
                raise ValueError(f"Button not found: {button}")
            else:
                raise ValueError("Must specify selector, text, or button")
                
        except Exception as e:
            # Enhanced error handling with suggestions
            visible_elements = self.playwright_page.query_selector_all('button, input[type="submit"], input[type="button"], a')
            suggestions = []
            for elem in visible_elements[:5]:  # Limit to first 5
                elem_text = elem.text_content() or elem.get_attribute('value') or elem.get_attribute('title')
                if elem_text:
                    suggestions.append(elem_text.strip())
            
            error_msg = f"Click failed: {e}"
            if suggestions:
                error_msg += f"\\nSuggested clickable elements: {', '.join(suggestions)}"
            raise RuntimeError(error_msg)
    
    def _selenium_click(self, selector: str = None, text: str = None, button: str = None) -> None:
        """Selenium click implementation (unchanged for compatibility)"""
        element = None
        
        if selector:
            element = WebDriverWait(self.selenium_driver, self.config.get("browser.timeout")).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        elif text:
            element = WebDriverWait(self.selenium_driver, self.config.get("browser.timeout")).until(
                EC.element_to_be_clickable((By.XPATH, f"//*[contains(text(), '{text}')]"))
            )
        elif button:
            selectors = [
                f"//button[contains(text(), '{button}')]",
                f"//input[@type='submit' and @value='{button}']",
                f"//input[@type='button' and @value='{button}']",
                f"//a[contains(text(), '{button}')]"
            ]
            
            for sel in selectors:
                try:
                    element = WebDriverWait(self.selenium_driver, 2).until(
                        EC.element_to_be_clickable((By.XPATH, sel))
                    )
                    break
                except:
                    continue
        
        if element:
            element.click()
        else:
            raise ValueError(f"Element not found: selector={selector}, text={text}, button={button}")
    
    def fill_form_field(self, field: str, value: str, **kwargs) -> None:
        """Enhanced form filling with smart field detection"""
        if self.playwright_page:
            self._playwright_fill_field(field, value, **kwargs)
        elif self.selenium_driver:
            self._selenium_fill_field(field, value)
        else:
            raise RuntimeError("No browser session active")
        
        # Record action for MCP
        self.mcp_bridge.record_action('fill', field=field, value=value, **kwargs)
    
    def _playwright_fill_field(self, field: str, value: str, **kwargs) -> None:
        """Enhanced Playwright form filling"""
        # Try direct selector first (for complex selectors like [role="textbox"][name="Name"])
        try:
            self.playwright_page.fill(field, value, timeout=5000, **kwargs)
            print(f"      ✓ Filled field using direct selector: {field}")
            return
        except Exception as e:
            print(f"      Direct selector failed: {e}")
        
        # Extract field name for smart detection
        field_name = field
        if '[name="' in field:
            # Extract name from selector like [role="textbox"][name="Name"]
            import re
            match = re.search(r'name="([^"]+)"', field)
            if match:
                field_name = match.group(1)
        
        # Smart field detection strategies
        selectors_to_try = [
            f"[name='{field_name}']",
            f"[id='{field_name}']",
            f"[data-testid='{field_name}']",
            f"[placeholder*='{field_name}' i]",
            f"[aria-label*='{field_name}' i]",
            f"label:has-text('{field_name}') input",
            f"input[type='text']:near(:text('{field_name}'))",
            f"input[type='email']:near(:text('{field_name}'))",
            f"input[type='password']:near(:text('{field_name}'))"
        ]
        
        print(f"      Trying alternative selectors for field: {field_name}")
        for selector in selectors_to_try:
            try:
                print(f"        Trying: {selector}")
                self.playwright_page.fill(selector, value, timeout=2000, **kwargs)
                print(f"      ✓ Filled field using: {selector}")
                return
            except Exception:
                continue
        
        # Show available input fields for debugging
        try:
            inputs = self.playwright_page.query_selector_all('input, textarea, [contenteditable="true"]')
            if inputs:
                print(f"      Available input fields on page:")
                for i, input_elem in enumerate(inputs[:10]):  # Limit to first 10
                    name_attr = input_elem.get_attribute('name') or 'no-name'
                    id_attr = input_elem.get_attribute('id') or 'no-id'  
                    placeholder = input_elem.get_attribute('placeholder') or 'no-placeholder'
                    field_type = input_elem.get_attribute('type') or 'text'
                    role_attr = input_elem.get_attribute('role') or 'no-role'
                    print(f"        {i+1}. type='{field_type}' name='{name_attr}' id='{id_attr}' role='{role_attr}' placeholder='{placeholder}'")
        except Exception:
            pass
        
        raise ValueError(f"Form field not found: {field}")
    
    def _selenium_fill_field(self, field: str, value: str) -> None:
        """Selenium form filling (enhanced)"""
        selectors = [
            (By.NAME, field),
            (By.ID, field),
            (By.CSS_SELECTOR, f"[data-testid='{field}']"),
            (By.CSS_SELECTOR, f"[placeholder*='{field}']"),
            (By.XPATH, f"//label[contains(text(), '{field}')]//input")
        ]
        
        for by, selector in selectors:
            try:
                element = WebDriverWait(self.selenium_driver, 5).until(
                    EC.presence_of_element_located((by, selector))
                )
                element.clear()
                element.send_keys(value)
                return
            except:
                continue
        
        raise ValueError(f"Form field not found: {field}")
    
    def verify_page_contains(self, text: str, **kwargs) -> bool:
        """Enhanced page content verification"""
        result = False
        
        if self.playwright_page:
            try:
                timeout = kwargs.get('timeout', 5000)
                self.playwright_page.wait_for_selector(f"text={text}", timeout=timeout)
                result = True
            except:
                result = False
        elif self.selenium_driver:
            try:
                timeout = kwargs.get('timeout', 5)
                WebDriverWait(self.selenium_driver, timeout).until(
                    EC.presence_of_element_located((By.XPATH, f"//*[contains(text(), '{text}')]"))
                )
                result = True
            except:
                result = False
        else:
            raise RuntimeError("No browser session active")
        
        # Record verification for MCP
        self.mcp_bridge.record_action('verify', text=text, result=result, **kwargs)
        return result
    
    def take_screenshot(self, name: str = None, **kwargs) -> Path:
        """Enhanced screenshot with MCP integration"""
        if not name:
            name = f"screenshot_{int(time.time())}"
        
        screenshot_path = self.screenshots_dir / f"{name}.png"
        
        if self.playwright_page:
            screenshot_options = kwargs.copy()
            self.playwright_page.screenshot(path=str(screenshot_path), **screenshot_options)
        elif self.selenium_driver:
            self.selenium_driver.save_screenshot(str(screenshot_path))
        else:
            raise RuntimeError("No browser session active")
        
        # Record screenshot for MCP
        self.mcp_bridge.record_action('screenshot', name=name, path=str(screenshot_path))
        return screenshot_path
    
    def wait_for_element(self, selector: str, timeout: int = None, **kwargs) -> None:
        """Enhanced element waiting"""
        timeout = timeout or self.config.get("browser.timeout")
        
        if self.playwright_page:
            self.playwright_page.wait_for_selector(selector, timeout=timeout * 1000, **kwargs)
        elif self.selenium_driver:
            WebDriverWait(self.selenium_driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        else:
            raise RuntimeError("No browser session active")
        
        # Record wait for MCP
        self.mcp_bridge.record_action('wait', selector=selector, timeout=timeout, **kwargs)
    
    def execute_playwright_code(self, code: str) -> Any:
        """Execute raw Playwright code for advanced scenarios"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
        
        # Create a safe execution context
        context = {
            'page': self.playwright_page,
            'browser': self.playwright_browser,
            'context': self.playwright_context
        }
        
        try:
            # Execute the code
            if inspect.iscoroutinefunction(eval(f"lambda: {code}")):
                # Handle async code
                result = asyncio.run(eval(f"async def _exec(): {code}; return await _exec()"))
            else:
                result = eval(code, {"__builtins__": {}}, context)
            
            # Record custom code execution
            self.mcp_bridge.record_action('custom_code', code=code, result=str(result))
            return result
        except Exception as e:
            error_msg = f"Playwright code execution failed: {e}"
            self.mcp_bridge.record_action('error', code=code, error=str(e))
            raise RuntimeError(error_msg)
    
    def get_page_info(self) -> Dict[str, Any]:
        """Get comprehensive page information for debugging"""
        if self.playwright_page:
            return {
                'url': self.playwright_page.url,
                'title': self.playwright_page.title(),
                'viewport': self.playwright_page.viewport_size,
                'user_agent': self.playwright_page.evaluate("navigator.userAgent"),
                'cookies': self.playwright_context.cookies() if self.playwright_context else [],
                'local_storage': self.playwright_page.evaluate("Object.entries(localStorage)"),
                'session_storage': self.playwright_page.evaluate("Object.entries(sessionStorage)")
            }
        elif self.selenium_driver:
            return {
                'url': self.selenium_driver.current_url,
                'title': self.selenium_driver.title,
                'window_size': self.selenium_driver.get_window_size(),
                'cookies': self.selenium_driver.get_cookies()
            }
        else:
            return {}
    
    def verify_text(self, text: str, timeout: int = 10000) -> None:
        """Verify text appears on the page using Playwright's native expect API"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                # Use Playwright's standard expect pattern - matches the original recording
                expect(self.playwright_page.locator("html")).to_contain_text(
                    text, timeout=timeout
                )
                print(f"      ✓ Verified text '{text}' appears on page")
            except Exception as e:
                # Enhanced debugging when verification fails
                try:
                    print(f"      Text verification failed for: '{text}'")
                    
                    # Check if text exists anywhere on page (case-insensitive)
                    page_text = self.playwright_page.text_content("body") or ""
                    if text.lower() in page_text.lower():
                        print(f"        Found text with different casing")
                    
                    # Check input field values 
                    inputs = self.playwright_page.query_selector_all("input")
                    for inp in inputs[:3]:  # Check first 3 inputs
                        value = inp.input_value() or ""
                        if value and text in value:
                            print(f"        Found in input field: '{value}'")
                            break
                    
                    # Show page content preview for debugging
                    content_preview = page_text.strip()[:150].replace('\n', ' ')
                    print(f"        Page content: {content_preview}...")
                    
                except Exception:
                    pass
                    
                raise AssertionError(f"Text '{text}' not found on page: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.text_to_be_present_in_element(
                        (By.TAG_NAME, "body"), text
                    )
                )
                print(f"      ✓ Verified text '{text}' appears on page")
            except Exception as e:
                raise AssertionError(f"Text '{text}' not found on page: {e}")
        else:
            raise RuntimeError("No browser session active")
        
        # Record action for MCP
        self.mcp_bridge.record_action('verify_text', text=text)
    
    def refresh_browser(self) -> None:
        """Refresh the current page"""
        if self.playwright_page:
            self.playwright_page.reload()
            print(f"      ✓ Page refreshed")
        elif self.selenium_driver:
            self.selenium_driver.refresh()
            print(f"      ✓ Page refreshed")
        else:
            raise RuntimeError("No browser session active")
        
        # Record action for MCP
        self.mcp_bridge.record_action('refresh')
    
    # ===== PLAYWRIGHT NATIVE API INTEGRATION =====
    
    def get_by_role(self, role: str, name: str = None, **kwargs) -> None:
        """Playwright get_by_role equivalent - click element by role"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
        
        locator_kwargs = kwargs.copy()
        if name:
            locator_kwargs['name'] = name
            
        try:
            locator = self.playwright_page.get_by_role(role, **locator_kwargs)
            locator.click()
            print(f"      ✓ Clicked element with role '{role}' name '{name}'")
        except Exception as e:
            raise RuntimeError(f"Failed to click role '{role}': {e}")
    
    def get_by_text(self, text: str, exact: bool = False, **kwargs) -> None:
        """Playwright get_by_text equivalent - click element by text"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            if exact:
                locator = self.playwright_page.get_by_text(text, exact=True)
            else:
                locator = self.playwright_page.get_by_text(text)
            locator.click(**kwargs)
            print(f"      ✓ Clicked element with text '{text}'")
        except Exception as e:
            raise RuntimeError(f"Failed to click text '{text}': {e}")
    
    def get_by_label(self, label: str, exact: bool = False, **kwargs) -> None:
        """Playwright get_by_label equivalent - interact with form field by label"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            locator = self.playwright_page.get_by_label(label, exact=exact)
            action = kwargs.pop('action', 'click')
            
            if action == 'fill':
                value = kwargs.pop('value', '')
                locator.fill(value)
                print(f"      ✓ Filled field labeled '{label}' with '{value}'")
            else:
                locator.click(**kwargs)
                print(f"      ✓ Clicked field labeled '{label}'")
        except Exception as e:
            raise RuntimeError(f"Failed to interact with label '{label}': {e}")
    
    def get_by_placeholder(self, placeholder: str, **kwargs) -> None:
        """Playwright get_by_placeholder equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            locator = self.playwright_page.get_by_placeholder(placeholder)
            action = kwargs.pop('action', 'click')
            
            if action == 'fill':
                value = kwargs.pop('value', '')
                locator.fill(value)
                print(f"      ✓ Filled field with placeholder '{placeholder}'")
            else:
                locator.click(**kwargs)
        except Exception as e:
            raise RuntimeError(f"Failed to interact with placeholder '{placeholder}': {e}")
    
    def get_by_test_id(self, test_id: str, **kwargs) -> None:
        """Playwright get_by_test_id equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            locator = self.playwright_page.get_by_test_id(test_id)
            action = kwargs.pop('action', 'click')
            
            if action == 'fill':
                value = kwargs.pop('value', '')
                locator.fill(value)
                print(f"      ✓ Filled field with test-id '{test_id}'")
            else:
                locator.click(**kwargs)
                print(f"      ✓ Clicked element with test-id '{test_id}'")
        except Exception as e:
            raise RuntimeError(f"Failed to interact with test-id '{test_id}': {e}")
    
    def hover_element(self, selector: str = None, **kwargs) -> None:
        """Playwright hover equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            if selector:
                self.playwright_page.hover(selector, **kwargs)
            print(f"      ✓ Hovered over element '{selector}'")
        except Exception as e:
            raise RuntimeError(f"Failed to hover over '{selector}': {e}")
    
    def double_click_element(self, selector: str = None, **kwargs) -> None:
        """Playwright double click equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            if selector:
                self.playwright_page.dblclick(selector, **kwargs)
            print(f"      ✓ Double-clicked element '{selector}'")
        except Exception as e:
            raise RuntimeError(f"Failed to double-click '{selector}': {e}")
    
    def press_key(self, key: str, selector: str = None, **kwargs) -> None:
        """Playwright keyboard press equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            if selector:
                self.playwright_page.press(selector, key, **kwargs)
            else:
                self.playwright_page.keyboard.press(key)
            print(f"      ✓ Pressed key '{key}'")
        except Exception as e:
            raise RuntimeError(f"Failed to press key '{key}': {e}")
    
    def type_text(self, text: str, selector: str = None, **kwargs) -> None:
        """Playwright type equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            if selector:
                self.playwright_page.type(selector, text, **kwargs)
            else:
                self.playwright_page.keyboard.type(text)
            print(f"      ✓ Typed text '{text}'")
        except Exception as e:
            raise RuntimeError(f"Failed to type text '{text}': {e}")
    
    def select_option(self, selector: str, value: str = None, label: str = None, **kwargs) -> None:
        """Playwright select option equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            select_kwargs = {}
            if value:
                select_kwargs['value'] = value
            elif label:
                select_kwargs['label'] = label
                
            self.playwright_page.select_option(selector, **select_kwargs)
            print(f"      ✓ Selected option in '{selector}'")
        except Exception as e:
            raise RuntimeError(f"Failed to select option in '{selector}': {e}")
    
    def check_checkbox(self, selector: str, checked: bool = True, **kwargs) -> None:
        """Playwright check/uncheck equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            if checked:
                self.playwright_page.check(selector, **kwargs)
                print(f"      ✓ Checked checkbox '{selector}'")
            else:
                self.playwright_page.uncheck(selector, **kwargs)
                print(f"      ✓ Unchecked checkbox '{selector}'")
        except Exception as e:
            action = "check" if checked else "uncheck"
            raise RuntimeError(f"Failed to {action} '{selector}': {e}")
    
    def wait_for_element(self, selector: str = None, state: str = "visible", timeout: int = None, **kwargs) -> None:
        """Enhanced Playwright wait_for_selector equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        timeout = timeout or self.config.get("browser.timeout", 30) * 1000
        
        try:
            if selector:
                self.playwright_page.wait_for_selector(
                    selector, state=state, timeout=timeout, **kwargs
                )
                print(f"      ✓ Element '{selector}' is {state}")
            else:
                # Wait for page load states
                load_state = kwargs.get('load_state', 'networkidle')
                self.playwright_page.wait_for_load_state(load_state, timeout=timeout)
                print(f"      ✓ Page reached {load_state} state")
        except Exception as e:
            raise RuntimeError(f"Wait failed for '{selector}': {e}")
    
    def wait_for_text(self, text: str, timeout: int = None, **kwargs) -> None:
        """Wait for specific text to appear on page"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        timeout = timeout or self.config.get("browser.timeout", 30) * 1000
        
        try:
            self.playwright_page.wait_for_selector(
                f"text={text}", timeout=timeout, **kwargs
            )
            print(f"      ✓ Text '{text}' appeared on page")
        except Exception as e:
            raise RuntimeError(f"Text '{text}' did not appear: {e}")
    
    def get_element_text(self, selector: str) -> str:
        """Get text content from element"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            text = self.playwright_page.text_content(selector)
            print(f"      ✓ Retrieved text from '{selector}': '{text}'")
            return text or ""
        except Exception as e:
            raise RuntimeError(f"Failed to get text from '{selector}': {e}")
    
    def get_element_attribute(self, selector: str, attribute: str) -> str:
        """Get attribute value from element"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            value = self.playwright_page.get_attribute(selector, attribute)
            print(f"      ✓ Retrieved {attribute} from '{selector}': '{value}'")
            return value or ""
        except Exception as e:
            raise RuntimeError(f"Failed to get {attribute} from '{selector}': {e}")
    
    def execute_script(self, script: str, *args) -> Any:
        """Execute JavaScript on the page"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            result = self.playwright_page.evaluate(script, *args)
            print(f"      ✓ Executed JavaScript")
            return result
        except Exception as e:
            raise RuntimeError(f"JavaScript execution failed: {e}")
    
    def drag_and_drop(self, source: str, target: str, **kwargs) -> None:
        """Playwright drag and drop equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            self.playwright_page.drag_and_drop(source, target, **kwargs)
            print(f"      ✓ Dragged '{source}' to '{target}'")
        except Exception as e:
            raise RuntimeError(f"Drag and drop failed: {e}")
    
    def upload_file(self, selector: str, file_path: str, **kwargs) -> None:
        """Playwright file upload equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            self.playwright_page.set_input_files(selector, file_path, **kwargs)
            print(f"      ✓ Uploaded file '{file_path}' to '{selector}'")
        except Exception as e:
            raise RuntimeError(f"File upload failed: {e}")
    
    def navigate_back(self) -> None:
        """Navigate back in browser history"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            self.playwright_page.go_back()
            print(f"      ✓ Navigated back")
        except Exception as e:
            raise RuntimeError(f"Navigation back failed: {e}")
    
    def navigate_forward(self) -> None:
        """Navigate forward in browser history"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            self.playwright_page.go_forward()
            print(f"      ✓ Navigated forward")
        except Exception as e:
            raise RuntimeError(f"Navigation forward failed: {e}")
    
    def set_viewport(self, width: int, height: int) -> None:
        """Set browser viewport size"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")
            
        try:
            self.playwright_page.set_viewport_size({"width": width, "height": height})
            print(f"      ✓ Set viewport to {width}x{height}")
        except Exception as e:
            raise RuntimeError(f"Failed to set viewport: {e}")
    
    def add_cookie(self, name: str, value: str, domain: str = None, path: str = "/", **kwargs) -> None:
        """Add cookie to browser context"""
        if not self.playwright_context:
            raise RuntimeError("Playwright context not active")
            
        try:
            cookie = {"name": name, "value": value, "path": path}
            if domain:
                cookie["domain"] = domain
            cookie.update(kwargs)
            
            self.playwright_context.add_cookies([cookie])
            print(f"      ✓ Added cookie '{name}'")
        except Exception as e:
            raise RuntimeError(f"Failed to add cookie: {e}")
    
    def clear_cookies(self) -> None:
        """Clear all cookies"""
        if not self.playwright_context:
            raise RuntimeError("Playwright context not active")
            
        try:
            self.playwright_context.clear_cookies()
            print(f"      ✓ Cleared all cookies")
        except Exception as e:
            raise RuntimeError(f"Failed to clear cookies: {e}")

    def close_browser(self) -> None:
        """Close the browser and clean up resources"""
        if self.playwright_page:
            self.playwright_page.close()
            self.playwright_page = None
        
        if self.playwright_context:
            self.playwright_context.close()
            self.playwright_context = None
        
        if self.playwright_browser:
            self.playwright_browser.close()
            self.playwright_browser = None
        
        if self.playwright_playwright:
            self.playwright_playwright.stop()
            self.playwright_playwright = None
        
        if self.selenium_driver:
            self.selenium_driver.quit()
            self.selenium_driver = None
    
    def close(self) -> None:
        """Alias for close_browser for compatibility"""
        self.close_browser()
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        self.close_browser()