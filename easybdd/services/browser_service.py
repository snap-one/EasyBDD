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
from .api_service import APIService


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
                "action": action,
                "timestamp": time.time(),
                "parameters": kwargs,
            }
            self.recording_actions.append(action_data)

    def get_recorded_actions(self) -> List[Dict[str, Any]]:
        """Get all recorded actions"""
        return self.recording_actions.copy()

    def export_to_easybdd(self) -> Dict[str, Any]:
        """Export recorded actions to Easy BDD format"""
        steps = []

        for action_data in self.recording_actions:
            action = action_data["action"]
            params = action_data["parameters"]

            if action == "navigate":
                steps.append({"action": "Open browser", "url": params.get("url")})
            elif action == "click":
                step = {"action": "Click element"}
                if "selector" in params:
                    step["selector"] = params["selector"]
                elif "text" in params:
                    step["text"] = params["text"]
                steps.append(step)
            elif action == "fill":
                steps.append(
                    {
                        "action": "Fill form field",
                        "field": params.get("field", params.get("selector")),
                        "value": params.get("value"),
                    }
                )
            elif action == "screenshot":
                steps.append(
                    {
                        "action": "Take screenshot",
                        "name": params.get("name", "screenshot"),
                    }
                )

        return {
            "name": "Recorded Test",
            "description": "Auto-generated from MCP recording",
            "tags": ["browser", "mcp-recorded"],
            "steps": steps,
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
        # Get reporting directory with compatibility for both config types
        if hasattr(config, "get_variable"):
            # GlobalConfigManager
            self.screenshots_dir = (
                Path(config.get_variable("reporting_output_dir", "reports"))
                / "screenshots"
            )
        else:
            # Legacy ConfigManager
            self.screenshots_dir = (
                Path(config.get("reporting.output_dir", "reports")) / "screenshots"
            )
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Video recording directory
        video_dir = self._get_browser_config("video_recording.dir", "reports/videos")
        self.videos_dir = Path(video_dir)
        self.videos_dir.mkdir(parents=True, exist_ok=True)

        # Track current video path for cleanup
        self.current_video_path: Optional[Path] = None

        # MCP Bridge
        self.mcp_bridge = PlaywrightMCPBridge()

        # Preferred browser engine
        self.preferred_engine = "playwright" if PLAYWRIGHT_AVAILABLE else "selenium"

    def _get_config_value(self, config, key: str, default=None):
        """Get config value with compatibility for both config types"""
        if hasattr(config, "get_variable"):
            # GlobalConfigManager
            return config.get_variable(key, default)
        else:
            # Legacy ConfigManager
            return config.get(key.replace("_", "."), default)

    @staticmethod
    def _coerce_bool(value):
        """Convert string 'true'/'false' to bool; pass other types through unchanged."""
        if isinstance(value, str):
            lower = value.lower()
            if lower in ("true", "yes", "1"):
                return True
            if lower in ("false", "no", "0"):
                return False
        return value

    def _get_browser_config(self, key: str, default=None):
        """Get browser-specific configuration value"""
        full_key = f"browser.{key}"
        value = self._get_config_value(self.config, full_key, default)

        # Also check test variables if not found in config (for slow_mo, etc.)
        if value is None or value == default:
            if hasattr(self.config, "get_variable"):
                test_var_value = self.config.get_variable(key, None)
                if test_var_value is not None:
                    return self._coerce_bool(test_var_value)

        return self._coerce_bool(value)

    def _try_heal_selector(
        self,
        selector: str,
        action: str,
        value: str = None,
        **kwargs,
    ) -> bool:
        """
        When a CSS/XPath selector fails, attempt semantic fallbacks in priority order:
          1. aria-label / placeholder → get_by_label
          2. button/link text → get_by_role
          3. visible text → get_by_text
        Logs which fallback succeeded so users know what to update.
        Returns True if a fallback worked, False otherwise.
        action is "click" or "fill".
        """
        import re as _re

        if not self.playwright_page or not selector:
            return False

        healed_via = None

        # Extract candidates from the selector string
        aria = _re.search(r'\[aria-label=["\']([^"\']+)["\']\]', selector)
        placeholder = _re.search(r'\[placeholder=["\']([^"\']+)["\']\]', selector)
        has_text = _re.search(r':has-text\(["\']([^"\']+)["\']\)', selector)
        btn_value = _re.search(r'\[value=["\']([^"\']+)["\']\]', selector)
        is_button = bool(_re.search(r'^button\b|\[type=["\']?submit["\']?\]|\[type=["\']?button["\']?\]', selector, _re.I))
        is_link = bool(_re.match(r'^a\b', selector, _re.I))

        fallbacks = []

        if aria:
            fallbacks.append(("label", aria.group(1)))
        if placeholder:
            fallbacks.append(("label", placeholder.group(1)))
        if has_text and is_button:
            fallbacks.append(("role_button", has_text.group(1)))
        if has_text and is_link:
            fallbacks.append(("role_link", has_text.group(1)))
        if btn_value and is_button:
            fallbacks.append(("role_button", btn_value.group(1)))
        if has_text:
            fallbacks.append(("text", has_text.group(1)))

        for kind, text in fallbacks:
            try:
                if action == "click":
                    if kind == "label":
                        self.playwright_page.get_by_label(text).click(timeout=3000, **kwargs)
                    elif kind == "role_button":
                        self.playwright_page.get_by_role("button", name=text).click(timeout=3000, **kwargs)
                    elif kind == "role_link":
                        self.playwright_page.get_by_role("link", name=text).click(timeout=3000, **kwargs)
                    else:
                        self.playwright_page.get_by_text(text, exact=False).click(timeout=3000, **kwargs)
                else:  # fill
                    fill_val = value or ""
                    if kind == "label":
                        self.playwright_page.get_by_label(text).fill(fill_val, timeout=3000)
                    elif kind in ("role_button", "role_link"):
                        continue  # buttons/links aren't fillable
                    else:
                        self.playwright_page.get_by_text(text, exact=False).fill(fill_val, timeout=3000)

                healed_via = f"{kind}={text!r}"
                break
            except Exception:
                continue

        if healed_via:
            print(f"      [HEALED] Selector {selector!r} failed; used {healed_via} instead.")
            print(f"      [HEALED] Consider updating the selector to avoid future healing.")
            return True

        # ── Tier 2+: delegate to the advanced SelfHealer (AI + visual) ───────
        return self._try_advanced_heal(selector, action, value, **kwargs)

    def _try_advanced_heal(
        self,
        selector: str,
        action: str,
        value: str = None,
        ranked_selectors: list = None,
        element_description: str = "",
        stored_bbox: dict = None,
        **kwargs,
    ) -> bool:
        """
        Advanced self-healing via the crawler's SelfHealer:
          - Ranked fallback chain from test metadata
          - AI re-locate (Claude or Ollama)
          - Visual similarity (bbox proximity)

        Returns True if a working selector was found and the action succeeded.
        """
        try:
            from ..crawler.self_healer import SelfHealer
            from ..crawler.ai_client import build_ai_client
            from ..crawler.models import RankedSelector
        except ImportError:
            return False  # Crawler module not available

        import os

        # Build AI client only if provider creds are configured
        ai = None
        try:
            provider = os.getenv("CRAWLER_AI_PROVIDER", "claude")
            ai = build_ai_client(provider=provider)
        except Exception:
            pass

        # Convert raw dicts → RankedSelector objects
        ranked: list = []
        if ranked_selectors:
            for r in ranked_selectors:
                if isinstance(r, dict):
                    try:
                        ranked.append(RankedSelector(**r))
                    except Exception:
                        pass
                elif hasattr(r, "selector"):
                    ranked.append(r)

        healer = SelfHealer(ai_client=ai)
        page_html = ""
        try:
            if self.playwright_page:
                page_html = self.playwright_page.content()
        except Exception:
            pass

        new_selector = healer.heal(
            broken_selector=selector,
            element_description=element_description or f"Element targeted by {selector!r}",
            page_html=page_html,
            page=self.playwright_page if self.playwright_page else None,
            ranked_selectors=ranked or None,
            stored_bbox=stored_bbox,
        )

        if not new_selector:
            return False

        try:
            if action == "click":
                self.playwright_page.locator(new_selector).click(timeout=5000, **kwargs)
            else:
                self.playwright_page.locator(new_selector).fill(value or "", timeout=5000)
            print(f"      [HEAL-ADV] Used healed selector: {new_selector!r}")
            return True
        except Exception:
            return False

    def _resolve_iframe_selector(self, selector: str):
        """
        Resolve an iframe-prefixed selector (e.g. 'iframe#id >> #button').

        Returns (frame_locator, inner_selector) when an iframe prefix is detected,
        or (None, original_selector) for plain selectors.

        Usage in click/fill methods:
            frame_loc, inner = self._resolve_iframe_selector(selector)
            if frame_loc:
                frame_loc.locator(inner).click()
            else:
                self.playwright_page.locator(inner).click()
        """
        if not self.playwright_page:
            return None, selector

        import re as _re
        m = _re.match(r'^(iframe[^>]*?)\s*>>\s*(.+)$', selector.strip())
        if not m:
            return None, selector

        iframe_sel = m.group(1).strip()
        inner_sel  = m.group(2).strip()

        try:
            frame_loc = self.playwright_page.frame_locator(iframe_sel)
            return frame_loc, inner_sel
        except Exception as e:
            print(f"      [IFRAME] Could not get frame_locator for {iframe_sel!r}: {e}")
            return None, selector

    def set_mcp_mode(self, enabled: bool = True):
        """Enable or disable MCP mode for recording"""
        if enabled:
            self.mcp_bridge.enable_mcp_mode()
        else:
            self.mcp_bridge.disable_mcp_mode()

    def get_mcp_recording(self) -> Dict[str, Any]:
        """Get MCP recording in Easy BDD format"""
        return self.mcp_bridge.export_to_easybdd()

    def save_mcp_recording(self, file_path: Union[str, Path]):
        """Save MCP recording to file"""
        recording = self.get_mcp_recording()

        file_path = Path(file_path)
        if file_path.suffix.lower() == ".json":
            with open(file_path, "w") as f:
                json.dump(recording, f, indent=2)
        else:
            # Save as YAML
            import yaml

            with open(file_path, "w") as f:
                yaml.dump(recording, f, default_flow_style=False)

    def open_browser(
        self, url: str, browser: str = None, use_playwright: bool = None
    ) -> None:
        """Open browser and navigate to URL"""
        # If browser is already open, just navigate to the new URL
        if self.playwright_page and PLAYWRIGHT_AVAILABLE:
            try:
                print(f"      Browser already open, navigating to: '{url}'")
                self.playwright_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Record action for MCP
                self.mcp_bridge.record_action("navigate", url=url, browser=browser)
                return
            except Exception as e:
                print(f"      Navigation failed, will open new browser: {e}")
                # If navigation fails, close existing browser and open new one
                if self.playwright_browser:
                    try:
                        self.playwright_browser.close()
                    except:
                        pass
                self.playwright_browser = None
                self.playwright_page = None
                self.playwright_context = None
        elif self.selenium_driver and SELENIUM_AVAILABLE:
            try:
                print(f"      Browser already open, navigating to: '{url}'")
                self.selenium_driver.get(url)
                return
            except Exception as e:
                print(f"      Navigation failed, will open new browser: {e}")
                # If navigation fails, close existing browser and open new one
                try:
                    self.selenium_driver.quit()
                except:
                    pass
                self.selenium_driver = None

        # Get browser preference from config
        if browser is None:
            # Check for per-run browser override injected by multi-browser execution
            if hasattr(self.config, "get_variable"):
                browser = (
                    self.config.get_variable("_browser_override", None)
                    or self.config.get_variable("browser.default", "chrome")
                )
            else:
                browser = self.config.get("browser.default", "chrome")

        # Auto-detect best engine
        if use_playwright is None:
            use_playwright = self.preferred_engine == "playwright"

        if use_playwright and PLAYWRIGHT_AVAILABLE:
            self._open_playwright_browser(url, browser)
        elif SELENIUM_AVAILABLE:
            self._open_selenium_browser(url, browser)
        else:
            raise RuntimeError(
                "No browser automation library available. Install Playwright or Selenium."
            )

        # Record action for MCP
        self.mcp_bridge.record_action("navigate", url=url, browser=browser)

    def _open_playwright_browser(self, url: str, browser: str) -> None:
        """Open browser using Playwright with enhanced MCP integration"""
        # If browser is already open, just navigate
        if self.playwright_browser and self.playwright_page:
            try:
                self.playwright_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return
            except Exception as e:
                print(f"      Navigation failed, closing existing browser: {e}")
                # Close existing browser and create new one
                try:
                    self.playwright_browser.close()
                except:
                    pass
                self.playwright_browser = None
                self.playwright_page = None
                self.playwright_context = None
                self.playwright_playwright = None

        # Create new Playwright instance only if needed
        if self.playwright_playwright is None:
            self.playwright_playwright = sync_playwright().start()

        # Browser launch options
        launch_options = {
            "headless": self._get_browser_config("headless", True),
            "args": [
                "--no-sandbox",
                "--disable-dev-shm-usage",  # Better Docker compatibility
            ],
        }

        # Add HTTPS certificate handling
        ignore_https = self._get_browser_config(
            "ignore_https_errors", False
        ) or self._get_browser_config("ignore_certificate_errors", False)
        if ignore_https:
            launch_options["args"].extend(
                [
                    "--ignore-certificate-errors",
                    "--ignore-ssl-errors",
                    "--ignore-certificate-errors-spki-list",
                    "--ignore-ssl-errors-on-localhost",
                    "--allow-running-insecure-content",
                    "--disable-web-security",
                ]
            )

        # Add configured browser args
        browser_args = self._get_browser_config("args", [])
        if browser_args:
            launch_options["args"].extend(browser_args)

        # Add slow_mo option from config (applies to all browser actions)
        slow_mo = self._get_browser_config("slow_mo", None)
        if slow_mo is not None:
            # Convert to int if it's a string
            if isinstance(slow_mo, str):
                try:
                    slow_mo = int(slow_mo)
                except ValueError:
                    slow_mo = None
            if slow_mo is not None and slow_mo >= 0:  # Allow 0 to disable
                launch_options["slow_mo"] = slow_mo
                print(f"      ⏱️  Browser slow_mo set to {slow_mo}ms")
        # Fallback to MCP mode default if not configured
        elif self.mcp_bridge.mcp_mode:
            launch_options["slow_mo"] = 50  # Slow down for better observation
            print(f"      ⏱️  Browser slow_mo set to 50ms (MCP mode default)")
        
        # Add debugging options for MCP mode
        if self.mcp_bridge.mcp_mode:
            launch_options["devtools"] = not self._get_browser_config("headless", True)

        browser_type = getattr(
            self.playwright_playwright, self._get_playwright_browser_name(browser)
        )
        self.playwright_browser = browser_type.launch(**launch_options)

        # Create context with enhanced options
        # Get window size from config, or use a reasonable default (1280x720) instead of 1920x1080
        default_width = 1280
        default_height = 720
        window_size = self._get_browser_config("window_size", [default_width, default_height])
        if isinstance(window_size, list) and len(window_size) >= 2:
            viewport_width = window_size[0]
            viewport_height = window_size[1]
        else:
            viewport_width = default_width
            viewport_height = default_height
        
        context_options = {
            "viewport": {
                "width": viewport_width,
                "height": viewport_height,
            },
            "ignore_https_errors": self._get_browser_config(
                "ignore_https_errors", True
            ),
            "accept_downloads": True,
        }

        # Configure video recording
        video_enabled_raw = self._get_browser_config("video_recording.enabled", False)
        # Handle string "true"/"false" and boolean
        if isinstance(video_enabled_raw, str):
            video_enabled = video_enabled_raw.lower() == "true"
        else:
            video_enabled = (
                bool(video_enabled_raw) if video_enabled_raw is not None else False
            )

        video_mode = self._get_browser_config("video_recording.mode", "on-failure")

        if video_enabled and video_mode in ["always", "on-failure"]:
            video_width = self._get_browser_config("video_recording.size.width", 1280)
            video_height = self._get_browser_config("video_recording.size.height", 720)

            context_options["record_video_dir"] = str(self.videos_dir)
            context_options["record_video_size"] = {
                "width": video_width,
                "height": video_height,
            }

        # Add HAR recording for MCP mode
        if self.mcp_bridge.mcp_mode:
            context_options["record_har_path"] = str(
                self.screenshots_dir / "network.har"
            )

        self.playwright_context = self.playwright_browser.new_context(**context_options)

        # Enable request/response interception for MCP mode
        if self.mcp_bridge.mcp_mode:
            self.playwright_context.route("**/*", self._handle_route)

        self.playwright_page = self.playwright_context.new_page()

        # Set MCP bridge page reference
        self.mcp_bridge.page = self.playwright_page

        # Maximize browser window (only in headed mode)
        if not self._get_browser_config("headless", False):
            try:
                # Get the first page and maximize it
                # Playwright doesn't have a direct maximize, so we set viewport to screen size
                # or use window.maximize() via JavaScript
                self.playwright_page.evaluate("window.moveTo(0, 0); window.resizeTo(screen.width, screen.height);")
            except Exception as e:
                print(f"      ⚠️  Could not maximize browser window: {e}")

        # Enhanced error handling and retry logic
        try:
            self.playwright_page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Navigation warning: {e}")
            # Fallback navigation
            self.playwright_page.goto(url, wait_until="domcontentloaded")

    def _handle_route(self, route, request):
        """Handle network routes for MCP mode"""
        # Log network requests in MCP mode
        if self.mcp_bridge.mcp_mode:
            self.mcp_bridge.record_action(
                "network_request",
                url=request.url,
                method=request.method,
                resource_type=request.resource_type,
            )

        # Continue with the request
        route.continue_()

    def _open_selenium_browser(self, url: str, browser: str) -> None:
        """Open browser using Selenium (fallback)"""
        if self.selenium_driver:
            self.selenium_driver.quit()

        if browser.lower() == "chrome":
            options = ChromeOptions()

            # Headless mode
            if self.config.get("browser.headless", True):
                options.add_argument("--headless")

            # Window size
            window_size = self.config.get("browser.window_size", [1920, 1080])
            options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")

            # HTTPS certificate handling
            if self.config.get("browser.ignore_https_errors", False) or self.config.get(
                "browser.ignore_certificate_errors", False
            ):
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
            if self.config.get("browser.headless", True):
                options.add_argument("--headless")

            # HTTPS certificate handling
            if self.config.get("browser.ignore_https_errors", False) or self.config.get(
                "browser.ignore_certificate_errors", False
            ):
                options.set_preference("security.tls.insecure_fallback_hosts", "*")
                options.set_preference("security.tls.unrestricted_rc4_fallback", True)
                options.set_preference(
                    "security.mixed_content.block_active_content", False
                )
                options.set_preference(
                    "security.mixed_content.block_display_content", False
                )

            self.selenium_driver = webdriver.Firefox(options=options)

        else:
            raise ValueError(f"Unsupported browser: {browser}")

        self.selenium_driver.implicitly_wait(
            self.config.get("browser.implicit_wait", 10)
        )
        self.selenium_driver.get(url)

    def _get_playwright_browser_name(self, browser: str) -> str:
        """Map browser names to Playwright browser types"""
        browser_map = {
            "chrome": "chromium",
            "chromium": "chromium",
            "firefox": "firefox",
            "safari": "webkit",
            "edge": "chromium",
            "webkit": "webkit",
        }
        return browser_map.get(browser.lower(), "chromium")

    def _is_xpath_selector(self, selector: str) -> bool:
        """Check if selector is an XPath expression"""
        if not selector:
            return False

        # Common XPath indicators
        xpath_indicators = [
            selector.startswith("//"),
            selector.startswith("./"),
            selector.startswith("(//"),
            selector.startswith("(.//"),
            selector.startswith("/html"),  # absolute XPath
            selector.startswith("/body"),  # absolute XPath
            "//" in selector,
            "normalize-space(" in selector,
            "following::" in selector,
            "preceding::" in selector,
            "ancestor::" in selector,
            "descendant::" in selector,
        ]

        return any(xpath_indicators)

    def _normalize_xpath_selector(self, selector: str) -> str:
        """Normalize XPath selector for Playwright"""
        if not selector:
            return selector

        # Remove xpath= prefix if present
        if selector.startswith("xpath="):
            selector = selector[6:]

        # Ensure XPath starts with // or . if it's a relative path
        if not selector.startswith(("/", ".", "(")):
            selector = f"//{selector}"

        return selector

    def _suggest_alternative_selectors(self, failed_selector: str) -> None:
        """Suggest alternative selectors when XPath fails"""
        try:
            # Look for text content that might help
            if "STOPPED" in failed_selector:
                # Try to find elements containing "STOPPED"
                elements = self.playwright_page.query_selector_all('text="STOPPED"')
                if elements:
                    print(f"      Found {len(elements)} elements with 'STOPPED' text")

            # Get all clickable elements for debugging
            clickable = self.playwright_page.query_selector_all(
                'a, button, [role="button"], [onclick]'
            )
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

    def click_element(
        self,
        selector: str = None,
        text: str = None,
        button: str = None,
        role: str = None,
        name: str = None,
        label: str = None,
        **kwargs,
    ) -> None:
        """Enhanced click with multiple selector strategies"""
        if self.playwright_page:
            self._playwright_click(selector, text, button, role, name, label=label, **kwargs)
        elif self.selenium_driver:
            self._selenium_click(selector, text, button)
        else:
            raise RuntimeError("No browser session active")

        # Record action for MCP
        self.mcp_bridge.record_action(
            "click",
            selector=selector,
            text=text,
            button=button,
            role=role,
            name=name,
            label=label,
            **kwargs,
        )

    def _playwright_click(
        self,
        selector: str = None,
        text: str = None,
        button: str = None,
        role: str = None,
        name: str = None,
        label: str = None,
        **kwargs,
    ) -> None:
        """Enhanced Playwright click with XPath support"""
        click_options = kwargs.copy()

        if button:
            click_options["button"] = button

        try:
            # Handle get_by_label (e.g., page.get_by_label("SourceAnalogTosLinkCoaxHDMI"))
            if label:
                print(f"      Finding element by label: {label}")
                exact = kwargs.get("exact", False)
                self.playwright_page.get_by_label(label, exact=exact).click(
                    timeout=5000, **click_options
                )
                print(f"      ✓ Clicked element with label: {label}")
                return

            # Handle get_by_role (e.g., page.get_by_role("link", name="...") or just role)
            if role:
                exact = kwargs.get("exact", False)
                if name:
                    # Role with name (more specific)
                    print(f"      Finding element by role '{role}' with name: {name}")
                    self.playwright_page.get_by_role(role, name=name, exact=exact).click(
                        timeout=5000, **click_options
                    )
                    print(f"      ✓ Clicked {role}: {name}")
                else:
                    # Role alone (clicks first element with that role)
                    print(f"      Finding element by role: {role}")
                    self.playwright_page.get_by_role(role).first.click(
                        timeout=5000, **click_options
                    )
                    print(f"      ✓ Clicked first element with role: {role}")
                return

            # Handle get_by_label — explicit label= param or 'label:Text' selector prefix
            _label = label or (selector[len("label:"):].strip() if selector and selector.startswith("label:") else None)
            if _label:
                print(f"      Finding element by label: {_label}")
                self.playwright_page.get_by_label(_label).click(timeout=5000)
                print(f"      ✓ Clicked element labeled '{_label}'")
                return

            if selector:
                print(f"      Processing selector: {selector}")

                # Handle iframe selector syntax: 'iframe >> #selector'
                if ">>" in selector:
                    parts = selector.split(">>")
                    iframe_sel = parts[0].strip()
                    element_sel = parts[1].strip()
                    print(f"      Clicking in iframe: {iframe_sel} >> {element_sel}")

                    # Get the frame
                    frames = self.playwright_page.frames
                    target_frame = None

                    for frame in frames:
                        if frame != self.playwright_page.main_frame:
                            target_frame = frame
                            break

                    if target_frame:
                        target_frame.click(element_sel, timeout=5000, **click_options)
                        print(f"      ✓ Clicked element in iframe")
                        return
                    else:
                        raise RuntimeError("Could not find iframe")

                # Handle Chrome Recorder aria/ format
                if selector.startswith("aria/"):
                    aria_label = selector.replace("aria/", "", 1)
                    print(f"      Using ARIA label: {aria_label}")
                    # Try multiple ARIA-based strategies
                    try:
                        # First try exact role match
                        self.playwright_page.get_by_role(
                            "button", name=aria_label
                        ).click(timeout=5000, **click_options)
                        return
                    except:
                        try:
                            # Try as text input
                            self.playwright_page.get_by_label(aria_label).click(
                                timeout=5000, **click_options
                            )
                            return
                        except:
                            # Fall back to text match
                            self.playwright_page.get_by_text(aria_label).click(
                                timeout=5000, **click_options
                            )
                            return

                print(f"      Is XPath: {self._is_xpath_selector(selector)}")

                # Handle XPath selectors
                if self._is_xpath_selector(selector):
                    xpath_selector = self._normalize_xpath_selector(selector)
                    print(f"      Using XPath: {xpath_selector}")
                    self.playwright_page.click(
                        f"xpath={xpath_selector}", timeout=10000, **click_options
                    )
                    return
                else:
                    # Resolve iframe prefix first (e.g. "iframe#id >> #btn")
                    frame_loc, resolved_sel = self._resolve_iframe_selector(selector)
                    try:
                        if frame_loc:
                            frame_loc.locator(resolved_sel).click(timeout=5000, **click_options)
                        else:
                            self.playwright_page.click(resolved_sel, timeout=5000, **click_options)
                    except Exception:
                        if not self._try_heal_selector(selector, "click", **click_options):
                            raise
                    return

            elif text:
                # Click by text content
                self.playwright_page.click(f"text={text}", **click_options)
                return

            elif button:
                # Use Playwright's get_by_role for reliable button finding
                print(f"      Finding button by role with name: {button}")
                try:
                    self.playwright_page.get_by_role("button", name=button).click(
                        timeout=5000
                    )
                    print(f"      ✓ Clicked button: {button}")
                    return
                except Exception as first_error:
                    # Fallback to text-based selectors
                    print(f"      get_by_role failed, trying alternative selectors")
                    selectors_to_try = [
                        f"button:has-text('{button}')",
                        f"input[type='submit'][value='{button}']",
                        f"input[type='button'][value='{button}']",
                        f"[role='button']:has-text('{button}')",
                    ]

                    for sel in selectors_to_try:
                        try:
                            self.playwright_page.click(
                                sel, timeout=2000, **click_options
                            )
                            print(f"      ✓ Clicked using: {sel}")
                            return
                        except Exception:
                            continue

                    raise ValueError(
                        f"Button not found: {button}. Original error: {first_error}"
                    )
            else:
                raise ValueError("Must specify selector, text, or button")

        except Exception as e:
            # Enhanced error handling with suggestions
            visible_elements = self.playwright_page.query_selector_all(
                'button, input[type="submit"], input[type="button"], a'
            )
            suggestions = []
            for elem in visible_elements[:5]:  # Limit to first 5
                elem_text = (
                    elem.text_content()
                    or elem.get_attribute("value")
                    or elem.get_attribute("title")
                )
                if elem_text:
                    suggestions.append(elem_text.strip())

            error_msg = f"Click failed: {e}"
            if suggestions:
                error_msg += (
                    f"\\nSuggested clickable elements: {', '.join(suggestions)}"
                )
            raise RuntimeError(error_msg)

    def _selenium_click(
        self, selector: str = None, text: str = None, button: str = None
    ) -> None:
        """Selenium click implementation (unchanged for compatibility)"""
        element = None

        if selector:
            element = WebDriverWait(
                self.selenium_driver, self.config.get("browser.timeout")
            ).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        elif text:
            element = WebDriverWait(
                self.selenium_driver, self.config.get("browser.timeout")
            ).until(
                EC.element_to_be_clickable(
                    (By.XPATH, f"//*[contains(text(), '{text}')]")
                )
            )
        elif button:
            selectors = [
                f"//button[contains(text(), '{button}')]",
                f"//input[@type='submit' and @value='{button}']",
                f"//input[@type='button' and @value='{button}']",
                f"//a[contains(text(), '{button}')]",
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
            raise ValueError(
                f"Element not found: selector={selector}, text={text}, button={button}"
            )

    def fill_form_field(
        self,
        field: str,
        value: str,
        role: str = None,
        name: str = None,
        label: str = None,
        **kwargs,
    ) -> None:
        """Enhanced form filling with smart field detection"""
        if self.playwright_page:
            self._playwright_fill_field(
                field, value, role=role, name=name, label=label, **kwargs
            )
        elif self.selenium_driver:
            self._selenium_fill_field(field, value)
        else:
            raise RuntimeError("No browser session active")

        # Record action for MCP
        self.mcp_bridge.record_action("fill", field=field, value=value, **kwargs)

    def _playwright_fill_field(
        self,
        field: str,
        value: str,
        role: str = None,
        name: str = None,
        label: str = None,
        **kwargs,
    ) -> None:
        """Enhanced Playwright form filling"""

        # Handle get_by_role with name
        if role and name:
            try:
                self.playwright_page.get_by_role(role, name=name).fill(
                    value, timeout=5000
                )
                print(f"      ✓ Filled {role} '{name}' with value")
                return
            except Exception as e:
                print(f"      get_by_role failed: {e}")

        # Handle get_by_label
        if label:
            try:
                self.playwright_page.get_by_label(label).fill(value, timeout=5000)
                print(f"      ✓ Filled field by label: {label}")
                return
            except Exception as e:
                print(f"      get_by_label failed: {e}")

        # Handle Chrome Recorder aria/ format
        if field and field.startswith("aria/"):
            aria_label = field.replace("aria/", "", 1)
            print(f"      Using ARIA label for fill: {aria_label}")
            try:
                self.playwright_page.get_by_label(aria_label).fill(value, timeout=5000)
                print(f"      ✓ Filled field using ARIA label: {aria_label}")
                return
            except Exception as e:
                print(f"      ARIA label failed: {e}")

        # Try direct selector first — with iframe prefix support
        frame_loc, resolved_field = self._resolve_iframe_selector(field)
        try:
            if frame_loc:
                frame_loc.locator(resolved_field).fill(value, timeout=5000)
            else:
                self.playwright_page.fill(resolved_field, value, timeout=5000, **kwargs)
            print(f"      ✓ Filled field using direct selector: {field}")
            return
        except Exception as e:
            print(f"      Direct selector failed: {e}")
            if self._try_heal_selector(field, "fill", value=value):
                return

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
            f"input[type='password']:near(:text('{field_name}'))",
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
            inputs = self.playwright_page.query_selector_all(
                'input, textarea, [contenteditable="true"]'
            )
            if inputs:
                print(f"      Available input fields on page:")
                for i, input_elem in enumerate(inputs[:10]):  # Limit to first 10
                    name_attr = input_elem.get_attribute("name") or "no-name"
                    id_attr = input_elem.get_attribute("id") or "no-id"
                    placeholder = (
                        input_elem.get_attribute("placeholder") or "no-placeholder"
                    )
                    field_type = input_elem.get_attribute("type") or "text"
                    role_attr = input_elem.get_attribute("role") or "no-role"
                    print(
                        f"        {i+1}. type='{field_type}' name='{name_attr}' id='{id_attr}' role='{role_attr}' placeholder='{placeholder}'"
                    )
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
            (By.XPATH, f"//label[contains(text(), '{field}')]//input"),
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
                timeout = kwargs.get("timeout", 5000)
                self.playwright_page.wait_for_selector(f"text={text}", timeout=timeout)
                result = True
            except:
                result = False
        elif self.selenium_driver:
            try:
                timeout = kwargs.get("timeout", 5)
                WebDriverWait(self.selenium_driver, timeout).until(
                    EC.presence_of_element_located(
                        (By.XPATH, f"//*[contains(text(), '{text}')]")
                    )
                )
                result = True
            except:
                result = False
        else:
            raise RuntimeError("No browser session active")

        # Record verification for MCP
        self.mcp_bridge.record_action("verify", text=text, result=result, **kwargs)
        return result

    def take_screenshot(self, name: str = None, **kwargs) -> Path:
        """Enhanced screenshot with MCP integration"""
        if not name:
            name = f"screenshot_{int(time.time())}"

        screenshot_path = self.screenshots_dir / f"{name}.png"

        if self.playwright_page:
            screenshot_options = kwargs.copy()
            self.playwright_page.screenshot(
                path=str(screenshot_path), **screenshot_options
            )
        elif self.selenium_driver:
            self.selenium_driver.save_screenshot(str(screenshot_path))
        else:
            raise RuntimeError("No browser session active")

        # Record screenshot for MCP
        self.mcp_bridge.record_action(
            "screenshot", name=name, path=str(screenshot_path)
        )
        return screenshot_path

    def wait_for_element(self, selector: str, timeout: int = None, **kwargs) -> None:
        """Enhanced element waiting"""
        timeout = timeout or self.config.get("browser.timeout")

        if self.playwright_page:
            self.playwright_page.wait_for_selector(
                selector, timeout=timeout * 1000, **kwargs
            )
        elif self.selenium_driver:
            WebDriverWait(self.selenium_driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
        else:
            raise RuntimeError("No browser session active")

        # Record wait for MCP
        self.mcp_bridge.record_action(
            "wait", selector=selector, timeout=timeout, **kwargs
        )

    def execute_playwright_code(self, code: str) -> Any:
        """Execute raw Playwright code for advanced scenarios"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")

        # Create a safe execution context
        context = {
            "page": self.playwright_page,
            "browser": self.playwright_browser,
            "context": self.playwright_context,
        }

        try:
            # Execute the code
            if inspect.iscoroutinefunction(eval(f"lambda: {code}")):
                # Handle async code
                result = asyncio.run(
                    eval(f"async def _exec(): {code}; return await _exec()")
                )
            else:
                result = eval(code, {"__builtins__": {}}, context)

            # Record custom code execution
            self.mcp_bridge.record_action("custom_code", code=code, result=str(result))
            return result
        except Exception as e:
            error_msg = f"Playwright code execution failed: {e}"
            self.mcp_bridge.record_action("error", code=code, error=str(e))
            raise RuntimeError(error_msg)

    def get_page_info(self) -> Dict[str, Any]:
        """Get comprehensive page information for debugging"""
        if self.playwright_page:
            return {
                "url": self.playwright_page.url,
                "title": self.playwright_page.title(),
                "viewport": self.playwright_page.viewport_size,
                "user_agent": self.playwright_page.evaluate("navigator.userAgent"),
                "cookies": (
                    self.playwright_context.cookies() if self.playwright_context else []
                ),
                "local_storage": self.playwright_page.evaluate(
                    "Object.entries(localStorage)"
                ),
                "session_storage": self.playwright_page.evaluate(
                    "Object.entries(sessionStorage)"
                ),
            }
        elif self.selenium_driver:
            return {
                "url": self.selenium_driver.current_url,
                "title": self.selenium_driver.title,
                "window_size": self.selenium_driver.get_window_size(),
                "cookies": self.selenium_driver.get_cookies(),
            }
        else:
            return {}

    def verify_text(
        self,
        text: str,
        timeout: int = 10000,
        soft_assert: bool = False,
        soft_assert_manager=None,
        step_number: int = 0,
    ) -> None:
        """Verify text appears on the page using Playwright's native expect API"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect

                # Use Playwright's standard expect pattern
                expect(self.playwright_page.locator("html")).to_contain_text(
                    text, timeout=timeout
                )
                print(f"      ✓ Verified text '{text}' appears on page")
            except Exception as e:
                # Enhanced debugging when verification fails
                page_text = ""
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
                    content_preview = page_text.strip()[:150].replace("\n", " ")
                    print(f"        Page content: {content_preview}...")

                except Exception:
                    pass

                # Handle soft assertion
                if soft_assert and soft_assert_manager:
                    error_msg = f"Text '{text}' not found on page"
                    soft_assert_manager.add_failure(
                        step_number=step_number,
                        action="Verify text",
                        message=error_msg,
                        expected=text,
                        actual=page_text[:100] if page_text else "Empty page",
                    )
                    return  # Don't raise, continue test execution

                # Truncate Playwright's verbose HTML dump to first meaningful line
                err_lines = [ln for ln in str(e).splitlines() if ln.strip() and "<" not in ln]
                err_summary = err_lines[0].strip() if err_lines else str(e)[:120]
                raise AssertionError(f"Text '{text}' not found on page. {err_summary}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait

                WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.text_to_be_present_in_element((By.TAG_NAME, "body"), text)
                )
                print(f"      ✓ Verified text '{text}' appears on page")
            except Exception as e:
                raise AssertionError(f"Text '{text}' not found on page: {e}")
        else:
            raise RuntimeError("No browser session active")

        # Record action for MCP
        self.mcp_bridge.record_action("verify_text", text=text)

    def verify_element(
        self,
        selector: str,
        timeout: int = 10000,
        soft_assert: bool = False,
        soft_assert_manager=None,
        step_number: int = 0,
    ) -> None:
        """Verify element exists and is visible on the page"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect

                locator = self.playwright_page.locator(selector)
                expect(locator).to_be_visible(timeout=timeout)
                print(f"      ✓ Verified element '{selector}' is visible")
            except Exception as e:
                error_msg = f"Element '{selector}' not found or not visible"

                # Handle soft assertion
                if soft_assert and soft_assert_manager:
                    soft_assert_manager.add_failure(
                        step_number=step_number,
                        action="Verify element",
                        message=error_msg,
                        expected=f"Element '{selector}' visible",
                        actual="Element not found or not visible",
                    )
                    return  # Don't raise, continue test execution

                raise AssertionError(f"{error_msg}: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By

                WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"      ✓ Verified element '{selector}' is visible")
            except Exception as e:
                error_msg = f"Element '{selector}' not found or not visible"

                # Handle soft assertion
                if soft_assert and soft_assert_manager:
                    soft_assert_manager.add_failure(
                        step_number=step_number,
                        action="Verify element",
                        message=error_msg,
                        expected=f"Element '{selector}' visible",
                        actual="Element not found or not visible",
                    )
                    return

                raise AssertionError(f"{error_msg}: {e}")
        else:
            raise RuntimeError("No browser session active")

        # Record action for MCP
        self.mcp_bridge.record_action("verify_element", selector=selector)

    def assert_text_contains(self, selector: str, text: str, timeout: int = 10000) -> None:
        """Assert that an element's text contains the expected value"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                
                # Handle label= selector syntax for select elements
                label_text = None
                if selector and selector.startswith("label="):
                    label_text = selector.replace("label=", "", 1).strip()
                    locator = self.playwright_page.get_by_label(label_text)
                else:
                    locator = self.playwright_page.locator(selector)
                
                # Wait for element to be visible
                locator.wait_for(state="visible", timeout=timeout)
                
                # Check if it's a select element - if so, get the selected option's text
                is_select = locator.evaluate("el => el.tagName === 'SELECT'")
                
                if is_select:
                    # For select elements, get the selected option's text
                    selected_text = locator.evaluate("""
                        el => {
                            const selectedOption = el.options[el.selectedIndex];
                            return selectedOption ? selectedOption.textContent.trim() : '';
                        }
                    """)
                    
                    if text not in selected_text:
                        raise AssertionError(
                            f"Select element '{selector}' selected option text does not contain '{text}'. "
                            f"Actual selected text: '{selected_text}'"
                        )
                    print(f"      ✓ Asserted select element '{selector}' selected option contains text '{text}'")
                else:
                    # For non-select elements, use normal text content check
                    if ":has-text(" in selector:
                        pass  # Already using the selector as-is
                    else:
                        # Try to find the element that contains the text
                        all_elements = locator.all()
                        found = False
                        for elem in all_elements:
                            try:
                                elem_text = elem.text_content() or ""
                                if text in elem_text:
                                    found = True
                                    locator = elem
                                    break
                            except:
                                continue
                        if not found:
                            # Fall back to expect which will wait and retry
                            pass
                    
                    expect(locator).to_contain_text(text, timeout=timeout)
                    print(f"      ✓ Asserted element '{selector}' contains text '{text}'")
            except Exception as e:
                actual_text = ""
                try:
                    # Handle label= selector
                    if selector and selector.startswith("label="):
                        label_text = selector.replace("label=", "", 1).strip()
                        locator = self.playwright_page.get_by_label(label_text)
                    else:
                        locator = self.playwright_page.locator(selector)
                    
                    # Check if it's a select element
                    is_select = locator.evaluate("el => el.tagName === 'SELECT'")
                    
                    if is_select:
                        # Get selected option text
                        actual_text = locator.evaluate("""
                            el => {
                                const selectedOption = el.options[el.selectedIndex];
                                return selectedOption ? selectedOption.textContent.trim() : '';
                            }
                        """)
                    else:
                        # Try to get text from the first matching element
                        if locator.count() > 0:
                            actual_text = locator.first.text_content() or ""
                        # If that's empty, try all elements
                        if not actual_text:
                            all_elements = locator.all()
                            texts = []
                            for elem in all_elements[:5]:  # Check first 5 elements
                                try:
                                    txt = elem.text_content() or ""
                                    if txt:
                                        texts.append(txt)
                                except:
                                    pass
                            if texts:
                                actual_text = f"[Found {len(texts)} elements with text: {', '.join(texts[:3])}]"
                except:
                    pass
                raise AssertionError(f"Element '{selector}' text does not contain '{text}'. Actual: '{actual_text}'")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                element = WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                actual_text = element.text
                if text not in actual_text:
                    raise AssertionError(f"Element '{selector}' text does not contain '{text}'. Actual: '{actual_text}'")
                print(f"      ✓ Asserted element '{selector}' contains text '{text}'")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' text assertion failed: {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_text_equals(self, selector: str, text: str, timeout: int = 10000) -> None:
        """Assert that an element's text exactly matches the expected value"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                
                # Handle label= selector syntax for select elements
                label_text = None
                if selector and selector.startswith("label="):
                    label_text = selector.replace("label=", "", 1).strip()
                    locator = self.playwright_page.get_by_label(label_text)
                else:
                    locator = self.playwright_page.locator(selector)
                
                # Wait for element to be visible
                locator.wait_for(state="visible", timeout=timeout)
                
                # Check if it's a select element - if so, get the selected option's text
                is_select = locator.evaluate("el => el.tagName === 'SELECT'")
                
                if is_select:
                    # For select elements, get the selected option's text
                    selected_text = locator.evaluate("""
                        el => {
                            const selectedOption = el.options[el.selectedIndex];
                            return selectedOption ? selectedOption.textContent.trim() : '';
                        }
                    """)
                    
                    if selected_text != text:
                        raise AssertionError(
                            f"Select element '{selector}' selected option text does not equal '{text}'. "
                            f"Actual selected text: '{selected_text}'"
                        )
                    print(f"      ✓ Asserted select element '{selector}' selected option text equals '{text}'")
                else:
                    # For non-select elements, use normal text check
                    expect(locator).to_have_text(text, timeout=timeout)
                    print(f"      ✓ Asserted element '{selector}' text equals '{text}'")
            except Exception as e:
                actual_text = ""
                try:
                    # Handle label= selector
                    if selector and selector.startswith("label="):
                        label_text = selector.replace("label=", "", 1).strip()
                        locator = self.playwright_page.get_by_label(label_text)
                    else:
                        locator = self.playwright_page.locator(selector)
                    
                    # Check if it's a select element
                    is_select = locator.evaluate("el => el.tagName === 'SELECT'")
                    
                    if is_select:
                        # Get selected option text
                        actual_text = locator.evaluate("""
                            el => {
                                const selectedOption = el.options[el.selectedIndex];
                                return selectedOption ? selectedOption.textContent.trim() : '';
                            }
                        """)
                    else:
                        actual_text = locator.text_content() or ""
                except:
                    pass
                raise AssertionError(f"Element '{selector}' text does not equal '{text}'. Actual: '{actual_text}'")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                element = WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                )
                actual_text = element.text.strip()
                if actual_text != text:
                    raise AssertionError(f"Element '{selector}' text does not equal '{text}'. Actual: '{actual_text}'")
                print(f"      ✓ Asserted element '{selector}' text equals '{text}'")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' text assertion failed: {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_element_visible(self, selector: str, timeout: int = 10000) -> None:
        """Assert that an element is visible on the page"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                locator = self.playwright_page.locator(selector)
                expect(locator).to_be_visible(timeout=timeout)
                print(f"      ✓ Asserted element '{selector}' is visible")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not visible: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"      ✓ Asserted element '{selector}' is visible")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not visible: {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_element_not_visible(self, selector: str, timeout: int = 10000) -> None:
        """Assert that an element is not visible on the page"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                locator = self.playwright_page.locator(selector)
                expect(locator).to_be_hidden(timeout=timeout)
                print(f"      ✓ Asserted element '{selector}' is not visible")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is visible (expected hidden): {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, selector))
                )
                print(f"      ✓ Asserted element '{selector}' is not visible")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is visible (expected hidden): {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_element_enabled(self, selector: str, timeout: int = 10000) -> None:
        """Assert that an element is enabled and interactive"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                locator = self.playwright_page.locator(selector)
                expect(locator).to_be_enabled(timeout=timeout)
                print(f"      ✓ Asserted element '{selector}' is enabled")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not enabled: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                element = WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                )
                if not element.is_enabled():
                    raise AssertionError(f"Element '{selector}' is not enabled")
                print(f"      ✓ Asserted element '{selector}' is enabled")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not enabled: {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_element_disabled(self, selector: str, timeout: int = 10000) -> None:
        """Assert that an element is disabled"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                locator = self.playwright_page.locator(selector)
                expect(locator).to_be_disabled(timeout=timeout)
                print(f"      ✓ Asserted element '{selector}' is disabled")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not disabled: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.common.by import By
                element = WebDriverWait(self.selenium_driver, timeout // 1000).until(
                    lambda d: d.find_element(By.CSS_SELECTOR, selector)
                )
                if element.is_enabled():
                    raise AssertionError(f"Element '{selector}' is enabled (expected disabled)")
                print(f"      ✓ Asserted element '{selector}' is disabled")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not disabled: {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_element_count(self, selector: str, count: int, timeout: int = 10000) -> None:
        """Assert that the number of elements matching the selector equals the expected count"""
        if self.playwright_page:
            try:
                locator = self.playwright_page.locator(selector)
                actual_count = locator.count()
                if actual_count != count:
                    raise AssertionError(f"Element count mismatch for '{selector}'. Expected: {count}, Actual: {actual_count}")
                print(f"      ✓ Asserted element '{selector}' count equals {count}")
            except Exception as e:
                raise AssertionError(f"Element count assertion failed for '{selector}': {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.common.by import By
                elements = self.selenium_driver.find_elements(By.CSS_SELECTOR, selector)
                actual_count = len(elements)
                if actual_count != count:
                    raise AssertionError(f"Element count mismatch for '{selector}'. Expected: {count}, Actual: {actual_count}")
                print(f"      ✓ Asserted element '{selector}' count equals {count}")
            except Exception as e:
                raise AssertionError(f"Element count assertion failed for '{selector}': {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_checked(self, selector: str, timeout: int = 10000) -> None:
        """Assert that a checkbox or radio button is checked"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                if selector.startswith("label:"):
                    locator = self.playwright_page.get_by_label(selector[len("label:"):].strip())
                else:
                    locator = self.playwright_page.locator(selector)
                expect(locator).to_be_checked(timeout=timeout)
                print(f"      ✓ Asserted element '{selector}' is checked")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not checked: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.common.by import By
                element = self.selenium_driver.find_element(By.CSS_SELECTOR, selector)
                if not element.is_selected():
                    raise AssertionError(f"Element '{selector}' is not checked")
                print(f"      ✓ Asserted element '{selector}' is checked")
            except AssertionError:
                raise
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not checked: {e}")
        else:
            raise RuntimeError("No browser session active")

    def assert_unchecked(self, selector: str, timeout: int = 10000) -> None:
        """Assert that a checkbox or radio button is unchecked"""
        if self.playwright_page:
            try:
                from playwright.sync_api import expect
                if selector.startswith("label:"):
                    locator = self.playwright_page.get_by_label(selector[len("label:"):].strip())
                else:
                    locator = self.playwright_page.locator(selector)
                expect(locator).not_to_be_checked(timeout=timeout)
                print(f"      ✓ Asserted element '{selector}' is unchecked")
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not unchecked: {e}")
        elif self.selenium_driver:
            try:
                from selenium.webdriver.common.by import By
                element = self.selenium_driver.find_element(By.CSS_SELECTOR, selector)
                if element.is_selected():
                    raise AssertionError(f"Element '{selector}' is checked (expected unchecked)")
                print(f"      ✓ Asserted element '{selector}' is unchecked")
            except AssertionError:
                raise
            except Exception as e:
                raise AssertionError(f"Element '{selector}' is not unchecked: {e}")
        else:
            raise RuntimeError("No browser session active")

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
        self.mcp_bridge.record_action("refresh")

    def show_step_indicator(self, step_number: int, total_steps: int, step_action: str, step_description: str = "") -> None:
        """Display a step indicator overlay in the browser showing current step
        
        This appears in the browser window (the page being tested), in the top-right corner.
        It shows which step is currently executing during UI tests.
        """
        if self.playwright_page:
            try:
                # Wait a moment for page to be ready if it just navigated
                import time
                time.sleep(0.1)
                
                import json
                # Escape strings for JavaScript
                step_action_js = json.dumps(step_action)
                step_description_js = json.dumps(step_description) if step_description else "''"
                
                # Create or update step indicator overlay
                script = f"""
                (function() {{
                    // Remove existing indicator
                    const existing = document.getElementById('__easybdd_step_indicator__');
                    if (existing) existing.remove();
                    
                    // Create indicator overlay
                    const indicator = document.createElement('div');
                    indicator.id = '__easybdd_step_indicator__';
                    indicator.style.cssText = `
                        position: fixed;
                        top: 20px;
                        left: 50%;
                        transform: translateX(-50%);
                        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
                        color: white;
                        padding: 16px 24px;
                        border-radius: 12px;
                        box-shadow: 0 8px 24px rgba(59, 130, 246, 0.6);
                        z-index: 999999;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        font-size: 14px;
                        line-height: 1.6;
                        min-width: 280px;
                        max-width: 500px;
                        pointer-events: none;
                        animation: slideIn 0.3s ease-out;
                        opacity: 0.95;
                    `;
                    
                    // Add animation
                    const style = document.createElement('style');
                    style.textContent = `
                        @keyframes slideIn {{
                            from {{
                                transform: translateX(-50%) translateY(-20px);
                                opacity: 0;
                            }}
                            to {{
                                transform: translateX(-50%) translateY(0);
                                opacity: 0.95;
                            }}
                        }}
                    `;
                    document.head.appendChild(style);
                    
                    // Build content
                    const stepInfo = document.createElement('div');
                    stepInfo.style.cssText = 'font-weight: 600; font-size: 16px; margin-bottom: 8px;';
                    stepInfo.textContent = 'Step {step_number}/{total_steps}';
                    
                    const actionInfo = document.createElement('div');
                    actionInfo.style.cssText = 'font-size: 13px; opacity: 0.95; margin-bottom: 4px;';
                    actionInfo.textContent = {step_action_js};
                    
                    indicator.appendChild(stepInfo);
                    indicator.appendChild(actionInfo);
                    
                    {f'''
                    if ({step_description_js}) {{
                        const descInfo = document.createElement('div');
                        descInfo.style.cssText = 'font-size: 12px; opacity: 0.85; margin-top: 4px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.2); word-break: break-word;';
                        descInfo.textContent = {step_description_js};
                        indicator.appendChild(descInfo);
                    }}
                    ''' if step_description else ''}
                    
                    document.body.appendChild(indicator);
                }})();
                """
                # Check if page is ready before injecting
                try:
                    # Wait for page to be ready
                    self.playwright_page.wait_for_load_state("domcontentloaded", timeout=2000)
                except:
                    pass  # Continue even if page isn't fully loaded
                
                self.playwright_page.evaluate(script)
                print(f"      📍 Step indicator displayed: Step {step_number}/{total_steps} - {step_action}")
            except Exception as e:
                # Log error for debugging
                print(f"      ⚠️  Could not display step indicator: {e}")

    def hide_step_indicator(self) -> None:
        """Hide the step indicator overlay"""
        if self.playwright_page:
            try:
                script = """
                (function() {
                    const indicator = document.getElementById('__easybdd_step_indicator__');
                    if (indicator) {
                        indicator.style.animation = 'slideOut 0.3s ease-out';
                        setTimeout(() => indicator.remove(), 300);
                    }
                })();
                """
                self.playwright_page.evaluate(script)
            except Exception:
                pass

    # ===== PLAYWRIGHT NATIVE API INTEGRATION =====

    def get_by_role(self, role: str, name: str = None, **kwargs) -> None:
        """Playwright get_by_role equivalent - click element by role"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")

        locator_kwargs = kwargs.copy()
        if name:
            locator_kwargs["name"] = name

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
            action = kwargs.pop("action", "click")

            if action == "fill":
                value = kwargs.pop("value", "")
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
            action = kwargs.pop("action", "click")

            if action == "fill":
                value = kwargs.pop("value", "")
                locator.fill(value)
                print(f"      ✓ Filled field with placeholder '{placeholder}'")
            else:
                locator.click(**kwargs)
        except Exception as e:
            raise RuntimeError(
                f"Failed to interact with placeholder '{placeholder}': {e}"
            )

    def get_by_test_id(self, test_id: str, **kwargs) -> None:
        """Playwright get_by_test_id equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")

        try:
            locator = self.playwright_page.get_by_test_id(test_id)
            action = kwargs.pop("action", "click")

            if action == "fill":
                value = kwargs.pop("value", "")
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

    def select_option(
        self, selector: str, value: str = None, label: str = None, **kwargs
    ) -> None:
        """Playwright select option equivalent with wildcard and label support"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")

        try:
            # Handle label= selector syntax (e.g., "label=SourceAnalogTosLinkCoaxHDMI")
            # Check for both "label=" prefix and also handle if selector parameter contains label
            label_text = None
            if selector:
                # Debug: print what we're checking
                if selector.startswith("label="):
                    label_text = selector.replace("label=", "", 1).strip()
                    print(f"      [DEBUG] Detected label= selector, extracted: '{label_text}'")
            elif not selector and kwargs.get("label"):
                label_text = kwargs.get("label")
                print(f"      [DEBUG] Using label from kwargs: '{label_text}'")
            
            if label_text:
                print(f"      Finding select element by label: '{label_text}'")
                
                # Use get_by_label to find the select element
                exact = kwargs.get("exact", False)
                select_locator = self.playwright_page.get_by_label(label_text, exact=exact)
                
                # Wait for the select element to be visible
                select_locator.wait_for(state="visible", timeout=10000)
                
                # Try to scroll into view
                try:
                    select_locator.scroll_into_view_if_needed(timeout=5000)
                except:
                    pass
                
                # Select the option
                select_kwargs = {}
                if value:
                    select_kwargs["value"] = value
                elif label:
                    select_kwargs["label"] = label
                
                select_locator.select_option(**select_kwargs)
                print(
                    f"      ✓ Selected option '{value or label}' in select with label '{label_text}'"
                )
                return

            # Convert wildcard selectors to CSS attribute selectors
            processed_selector = self._process_wildcard_selector(selector)
            print(f"      Selecting from: '{processed_selector}'")

            # Debug: Use JavaScript to find select elements directly
            js_result = self.playwright_page.evaluate(
                """
                () => {
                    const selects = Array.from(document.querySelectorAll('select'));
                    const iframes = Array.from(document.querySelectorAll('iframe'));
                    return {
                        selectCount: selects.length,
                        selects: selects.slice(0, 5).map(s => ({
                            id: s.id,
                            name: s.name,
                            className: s.className,
                            visible: s.offsetParent !== null
                        })),
                        iframeCount: iframes.length,
                        bodyHTML: document.body.innerHTML.substring(0, 500)
                    };
                }
            """
            )
            print(f"      JS Debug - Found {js_result['selectCount']} select elements")
            print(f"      JS Debug - Found {js_result['iframeCount']} iframes")
            if js_result["selectCount"] > 0:
                for i, sel in enumerate(js_result["selects"]):
                    print(
                        f"        [{i}] id='{sel['id']}', name='{sel['name']}', visible={sel['visible']}"
                    )
            else:
                print(f"      Page body preview: {js_result['bodyHTML'][:200]}...")

            # Wait for the select element to be visible and enabled
            locator = self.playwright_page.locator(processed_selector)
            locator.wait_for(state="visible", timeout=10000)

            # Try to scroll into view
            try:
                locator.scroll_into_view_if_needed(timeout=5000)
            except:
                pass

            select_kwargs = {}
            if value:
                select_kwargs["value"] = value
            elif label:
                select_kwargs["label"] = label

            # Use locator.select_option instead of page.select_option
            locator.select_option(**select_kwargs)
            print(
                f"      ✓ Selected option '{value or label}' in '{processed_selector}'"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to select option in '{selector}': {e}")

    def _process_wildcard_selector(self, selector: str) -> str:
        """Convert wildcard selectors to CSS attribute selectors

        Examples:
            select[id=":rg:*"] -> select[id^=":rg:"]
            input[name="field_*"] -> input[name^="field_"]
            div[class="*_container"] -> div[class*="_container"]
        """
        import re

        # Pattern: attribute[name="value*"] or attribute[name='value*']
        # Convert trailing wildcard to ^= (starts with)
        pattern_trailing = r'\[(\w+)=(["\'])([^"\']*)\*\2\]'
        selector = re.sub(pattern_trailing, r"[\1^=\2\3\2]", selector)

        # Pattern: attribute[name="*value"] or attribute[name='*value']
        # Convert leading wildcard to $= (ends with)
        pattern_leading = r'\[(\w+)=(["\'])\*([^"\']*)\2\]'
        selector = re.sub(pattern_leading, r"[\1$=\2\3\2]", selector)

        # Pattern: attribute[name="*value*"] or attribute[name='*value*']
        # Convert middle wildcard to *= (contains)
        pattern_middle = r'\[(\w+)=(["\'])\*([^"\']*)\*\2\]'
        selector = re.sub(pattern_middle, r"[\1*=\2\3\2]", selector)

        return selector

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

    def wait_for_element(
        self,
        selector: str = None,
        state: str = "visible",
        timeout: int = None,
        **kwargs,
    ) -> None:
        """Enhanced Playwright wait_for_selector equivalent"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")

        # Convert timeout to milliseconds if needed (assume seconds if < 1000)
        if timeout is not None and timeout < 1000:
            timeout = timeout * 1000
        else:
            timeout = timeout or self.config.get("browser.timeout", 30) * 1000

        try:
            if selector:
                self.playwright_page.wait_for_selector(
                    selector, state=state, timeout=timeout, **kwargs
                )
                print(f"      ✓ Element '{selector}' is {state}")
            else:
                # Wait for page load states
                load_state = kwargs.get("load_state", "networkidle")
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
        """Playwright file upload equivalent with iframe support"""
        if not self.playwright_page:
            raise RuntimeError("Playwright session not active")

        try:
            # Check if selector contains iframe context with >>
            if ">>" in selector:
                # Split iframe selector from element selector
                parts = selector.split(">>", 1)  # Split only on first >>
                iframe_sel = parts[0].strip()
                element_sel = parts[1].strip() if len(parts) > 1 else ""

                if element_sel:
                    # Get the actual frame element
                    frames = self.playwright_page.frames
                    target_frame = None

                    # Find the iframe by selector or just use first iframe
                    if iframe_sel == "iframe":
                        # Use first non-main frame
                        for frame in frames:
                            if frame != self.playwright_page.main_frame:
                                target_frame = frame
                                break
                    else:
                        # Try to match by iframe selector
                        for frame in frames:
                            if frame != self.playwright_page.main_frame:
                                target_frame = frame
                                break

                    if target_frame:
                        # Hidden file inputs need special handling
                        import os

                        # Resolve the file path (Path already imported at top)
                        path_obj = Path(file_path)
                        if not path_obj.is_absolute():
                            # Check if it exists relative to current dir
                            if path_obj.exists():
                                abs_path = str(path_obj.absolute())
                            else:
                                # Try relative to workspace root
                                abs_path = os.path.abspath(file_path)
                        else:
                            abs_path = file_path

                        # Verify file exists
                        if not os.path.exists(abs_path):
                            raise FileNotFoundError(f"File not found: {abs_path}")

                        # For hidden file inputs, use file chooser API
                        # Set up file chooser listener before triggering
                        print(f"      Setting up file chooser for: " f"{element_sel}")

                        # Start waiting for file chooser event
                        with self.playwright_page.expect_file_chooser() as fc:
                            # Trigger the file input (even if hidden)
                            target_frame.evaluate(
                                f"""
                                const input = document.querySelector(
                                    "{element_sel}");
                                if (input) {{
                                    // Make visible for Playwright
                                    input.style.display = 'block';
                                    input.style.visibility = 'visible';
                                    input.style.opacity = '1';
                                    input.removeAttribute('disabled');
                                    // Trigger click to open file chooser
                                    input.click();
                                }}
                            """
                            )

                        # Set the files when file chooser appears
                        file_chooser = fc.value
                        file_chooser.set_files(abs_path)
                        print("      ✓ Uploaded file via file chooser")
                    else:
                        raise RuntimeError("Could not find iframe")
                else:
                    msg = "Invalid iframe selector. Use: 'iframe >> #selector'"
                    raise ValueError(msg)
            else:
                # Regular file upload
                self.playwright_page.set_input_files(selector, file_path, **kwargs)
                print(f"      ✓ Uploaded file to '{selector}'")
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

    def add_cookie(
        self, name: str, value: str, domain: str = None, path: str = "/", **kwargs
    ) -> None:
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

    def get_video_path(self) -> Optional[Path]:
        """
        Get the path to the recorded video if available.
        The video is only available after the page is closed.
        """
        # Video is saved when context is closed, check if we have a saved path
        if self.current_video_path and self.current_video_path.exists():
            return self.current_video_path

        # Try to get video from page if still open
        if self.playwright_page:
            try:
                video = self.playwright_page.video
                if video:
                    video_path = Path(video.path())
                    self.current_video_path = video_path
                    return video_path
            except Exception as e:
                print(f"      Debug: Could not get video path: {e}")

        # Check videos directory for recently created files
        if self.videos_dir.exists():
            video_files = sorted(
                self.videos_dir.glob("*.webm"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if video_files:
                self.current_video_path = video_files[0]
                return video_files[0]

        return None

    def cleanup_video(self, video_path: Optional[Path] = None) -> bool:
        """Delete video file (for passing tests)"""
        if video_path is None:
            video_path = self.current_video_path

        if video_path and video_path.exists():
            try:
                video_path.unlink()
                return True
            except Exception as e:
                print(f"      Warning: Could not delete video: {e}")
                return False
        return False

    def close_browser(self) -> None:
        """Close the browser and clean up resources"""
        # Close page first to finalize video
        if self.playwright_page:
            self.playwright_page.close()
            self.playwright_page = None

        # Close context to save video
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
