"""
Action Definitions for Test Builder
Comprehensive catalog of all available actions with parameters, types, and validation
"""

from typing import Any, Dict, List

# Field types for form generation
FIELD_TYPES = {
    "text": "text",
    "number": "number",
    "boolean": "checkbox",
    "select": "select",
    "textarea": "textarea",
    "file": "file",
    "json": "json",
    "keyvalue": "keyvalue",
    "list": "list",
}

ACTION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # ==================== BROWSER ACTIONS ====================
    "browser.open": {
        "category": "Browser",
        "label": "Open Browser",
        "description": "Open browser and navigate to URL",
        "icon": "🌐",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://example.com",
                "help": "The URL to navigate to",
            },
            "browser": {
                "type": "select",
                "required": False,
                "label": "Browser Type",
                "options": ["chromium", "firefox", "webkit"],
                "default": "chromium",
                "help": "Browser engine to use",
            },
        },
    },
    "browser.navigate": {
        "category": "Browser",
        "label": "Navigate to URL",
        "description": "Navigate to a different URL in existing browser",
        "icon": "➡️",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://example.com/page",
                "help": "The URL to navigate to",
            }
        },
    },
    "browser.back": {
        "category": "Browser",
        "label": "Go Back",
        "description": "Navigate back in browser history",
        "icon": "⬅️",
        "parameters": {},
    },
    "browser.forward": {
        "category": "Browser",
        "label": "Go Forward",
        "description": "Navigate forward in browser history",
        "icon": "➡️",
        "parameters": {},
    },
    "browser.refresh": {
        "category": "Browser",
        "label": "Refresh Page",
        "description": "Reload the current page",
        "icon": "🔄",
        "parameters": {},
    },
    "browser.close": {
        "category": "Browser",
        "label": "Close Browser",
        "description": "Close the browser window",
        "icon": "❌",
        "parameters": {},
    },
    "browser.click": {
        "category": "Browser",
        "label": "Click Element",
        "description": "Click on an element",
        "icon": "👆",
        "parameters": {
            "selector": {
                "type": "text",
                "required": False,
                "label": "CSS Selector",
                "placeholder": "#submit-button",
                "help": "CSS selector for the element",
            },
            "text": {
                "type": "text",
                "required": False,
                "label": "Text Content",
                "placeholder": "Click here",
                "help": "Click element containing this text",
            },
            "button": {
                "type": "text",
                "required": False,
                "label": "Button Text/Name",
                "placeholder": "Submit",
                "help": "Button with this text or name",
            },
            "role": {
                "type": "select",
                "required": False,
                "label": "ARIA Role",
                "options": [
                    "button",
                    "link",
                    "checkbox",
                    "radio",
                    "textbox",
                    "tab",
                    "menuitem",
                ],
                "help": "Element with this ARIA role",
            },
            "name": {
                "type": "text",
                "required": False,
                "label": "Accessible Name",
                "placeholder": "Submit Form",
                "help": "Element with this accessible name",
            },
            "exact": {
                "type": "boolean",
                "required": False,
                "label": "Exact Match",
                "default": False,
                "help": "Require exact text match",
            },
            "force": {
                "type": "boolean",
                "required": False,
                "label": "Force Click",
                "default": False,
                "help": "Force click even if not visible",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (ms)",
                "placeholder": "30000",
                "help": "Maximum wait time in milliseconds",
            },
        },
    },
    "browser.fill": {
        "category": "Browser",
        "label": "Fill Input Field",
        "description": "Fill a form field with text",
        "icon": "✏️",
        "parameters": {
            "field": {
                "type": "text",
                "required": True,
                "label": "Field Selector",
                "placeholder": "#username",
                "help": "CSS selector for the input field",
            },
            "value": {
                "type": "text",
                "required": True,
                "label": "Value",
                "placeholder": "testuser",
                "help": "Text to fill in the field",
            },
            "clear": {
                "type": "boolean",
                "required": False,
                "label": "Clear First",
                "default": True,
                "help": "Clear field before filling",
            },
        },
    },
    "browser.upload": {
        "category": "Browser",
        "label": "Upload File",
        "description": "Upload a file to a file input",
        "icon": "📤",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Input Selector",
                "placeholder": "input[type='file']",
                "help": "CSS selector for file input",
            },
            "file_path": {
                "type": "file",
                "required": True,
                "label": "File Path",
                "placeholder": "/path/to/file.txt",
                "help": "Path to file to upload",
            },
        },
    },
    "browser.select": {
        "category": "Browser",
        "label": "Select Dropdown Option",
        "description": "Select an option from a dropdown",
        "icon": "📋",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Select Selector",
                "placeholder": "select#country",
                "help": "CSS selector for select element",
            },
            "value": {
                "type": "text",
                "required": False,
                "label": "Option Value",
                "placeholder": "us",
                "help": "Value attribute of option",
            },
            "label": {
                "type": "text",
                "required": False,
                "label": "Option Label",
                "placeholder": "United States",
                "help": "Visible text of option",
            },
            "index": {
                "type": "number",
                "required": False,
                "label": "Option Index",
                "placeholder": "0",
                "help": "Zero-based index of option",
            },
        },
    },
    "browser.check": {
        "category": "Browser",
        "label": "Check Checkbox",
        "description": "Check a checkbox or radio button",
        "icon": "☑️",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Checkbox Selector",
                "placeholder": "#agree-terms",
                "help": "CSS selector for checkbox",
            }
        },
    },
    "browser.uncheck": {
        "category": "Browser",
        "label": "Uncheck Checkbox",
        "description": "Uncheck a checkbox",
        "icon": "☐",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Checkbox Selector",
                "placeholder": "#newsletter",
                "help": "CSS selector for checkbox",
            }
        },
    },
    "browser.hover": {
        "category": "Browser",
        "label": "Hover Over Element",
        "description": "Move mouse over an element",
        "icon": "🖱️",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": ".dropdown-menu",
                "help": "CSS selector for element to hover",
            }
        },
    },
    "browser.drag": {
        "category": "Browser",
        "label": "Drag and Drop",
        "description": "Drag element from source to target",
        "icon": "🔀",
        "parameters": {
            "source": {
                "type": "text",
                "required": True,
                "label": "Source Selector",
                "placeholder": "#item1",
                "help": "Element to drag",
            },
            "target": {
                "type": "text",
                "required": True,
                "label": "Target Selector",
                "placeholder": "#dropzone",
                "help": "Element to drop onto",
            },
        },
    },
    "browser.press": {
        "category": "Browser",
        "label": "Press Key",
        "description": "Press a keyboard key",
        "icon": "⌨️",
        "parameters": {
            "key": {
                "type": "select",
                "required": True,
                "label": "Key",
                "options": [
                    "Enter",
                    "Escape",
                    "Tab",
                    "Backspace",
                    "Delete",
                    "ArrowUp",
                    "ArrowDown",
                    "ArrowLeft",
                    "ArrowRight",
                    "Space",
                    "PageUp",
                    "PageDown",
                    "Home",
                    "End",
                ],
                "help": "Key to press",
            },
            "selector": {
                "type": "text",
                "required": False,
                "label": "Element Selector",
                "placeholder": "#search-box",
                "help": "Press key on specific element (optional)",
            },
        },
    },
    "browser.type": {
        "category": "Browser",
        "label": "Type Text",
        "description": "Type text character by character",
        "icon": "⌨️",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#search",
                "help": "Element to type into",
            },
            "text": {
                "type": "text",
                "required": True,
                "label": "Text to Type",
                "placeholder": "Hello World",
                "help": "Text to type",
            },
            "delay": {
                "type": "number",
                "required": False,
                "label": "Delay (ms)",
                "placeholder": "100",
                "help": "Delay between keystrokes in milliseconds",
            },
        },
    },
    "browser.wait": {
        "category": "Browser",
        "label": "Wait",
        "description": "Wait for specified time",
        "icon": "⏱️",
        "parameters": {
            "timeout": {
                "type": "number",
                "required": True,
                "label": "Wait Time (seconds)",
                "placeholder": "5",
                "help": "Time to wait in seconds",
            }
        },
    },
    "browser.wait_for": {
        "category": "Browser",
        "label": "Wait for Element",
        "description": "Wait for element to appear/disappear",
        "icon": "⏳",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#loading-spinner",
                "help": "Element to wait for",
            },
            "state": {
                "type": "select",
                "required": False,
                "label": "State",
                "options": ["visible", "hidden", "attached", "detached"],
                "default": "visible",
                "help": "Wait for element to be in this state",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (ms)",
                "placeholder": "30000",
                "help": "Maximum wait time",
            },
        },
    },
    "browser.screenshot": {
        "category": "Browser",
        "label": "Take Screenshot",
        "description": "Capture screenshot of page or element",
        "icon": "📸",
        "parameters": {
            "name": {
                "type": "text",
                "required": True,
                "label": "Screenshot Name",
                "placeholder": "homepage",
                "help": "Name for the screenshot file",
            },
            "full_page": {
                "type": "boolean",
                "required": False,
                "label": "Full Page",
                "default": False,
                "help": "Capture entire page",
            },
            "selector": {
                "type": "text",
                "required": False,
                "label": "Element Selector",
                "placeholder": "#main-content",
                "help": "Capture specific element only",
            },
        },
    },
    "browser.get_text": {
        "category": "Browser",
        "label": "Get Element Text",
        "description": "Extract text from element",
        "icon": "📝",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#message",
                "help": "Element to get text from",
            },
            "store_as": {
                "type": "text",
                "required": True,
                "label": "Variable Name",
                "placeholder": "message_text",
                "help": "Store result in this variable",
            },
        },
    },
    "browser.get_attribute": {
        "category": "Browser",
        "label": "Get Element Attribute",
        "description": "Get attribute value from element",
        "icon": "🏷️",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#link",
                "help": "Element to get attribute from",
            },
            "attribute": {
                "type": "text",
                "required": True,
                "label": "Attribute Name",
                "placeholder": "href",
                "help": "Attribute to retrieve",
            },
            "store_as": {
                "type": "text",
                "required": True,
                "label": "Variable Name",
                "placeholder": "link_url",
                "help": "Store result in this variable",
            },
        },
    },
    "browser.execute": {
        "category": "Browser",
        "label": "Execute JavaScript",
        "description": "Run JavaScript code in browser",
        "icon": "💻",
        "parameters": {
            "script": {
                "type": "textarea",
                "required": True,
                "label": "JavaScript Code",
                "placeholder": "return document.title;",
                "help": "JavaScript code to execute",
            },
            "args": {
                "type": "json",
                "required": False,
                "label": "Arguments",
                "placeholder": "[]",
                "help": "Array of arguments to pass to script",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "result",
                "help": "Store return value in variable",
            },
        },
    },
    "browser.set_viewport": {
        "category": "Browser",
        "label": "Set Viewport Size",
        "description": "Set browser viewport dimensions",
        "icon": "📐",
        "parameters": {
            "width": {
                "type": "number",
                "required": True,
                "label": "Width (px)",
                "placeholder": "1920",
                "help": "Viewport width in pixels",
            },
            "height": {
                "type": "number",
                "required": True,
                "label": "Height (px)",
                "placeholder": "1080",
                "help": "Viewport height in pixels",
            },
        },
    },
    "browser.cookies": {
        "category": "Browser",
        "label": "Manage Cookies",
        "description": "Add, get, or clear cookies",
        "icon": "🍪",
        "parameters": {
            "action": {
                "type": "select",
                "required": True,
                "label": "Action",
                "options": ["add", "get", "clear"],
                "help": "Cookie operation",
            },
            "name": {
                "type": "text",
                "required": False,
                "label": "Cookie Name",
                "placeholder": "session_id",
                "help": "Name of cookie (for add/get)",
            },
            "value": {
                "type": "text",
                "required": False,
                "label": "Cookie Value",
                "placeholder": "abc123",
                "help": "Value of cookie (for add)",
            },
            "domain": {
                "type": "text",
                "required": False,
                "label": "Domain",
                "placeholder": "example.com",
                "help": "Cookie domain (optional)",
            },
        },
    },
    # ==================== API ACTIONS ====================
    "api.get": {
        "category": "API",
        "label": "GET Request",
        "description": "Send HTTP GET request",
        "icon": "🔍",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://api.example.com/users",
                "help": "API endpoint URL",
            },
            "headers": {
                "type": "json",
                "required": False,
                "label": "Headers",
                "placeholder": '{"Authorization": "Bearer token"}',
                "help": "HTTP headers as JSON object",
            },
            "params": {
                "type": "json",
                "required": False,
                "label": "Query Parameters",
                "placeholder": '{"page": 1, "limit": 10}',
                "help": "URL query parameters as JSON",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Request timeout",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "api_response",
                "help": "Store response in variable",
            },
        },
    },
    "api.post": {
        "category": "API",
        "label": "POST Request",
        "description": "Send HTTP POST request",
        "icon": "📤",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://api.example.com/users",
                "help": "API endpoint URL",
            },
            "headers": {
                "type": "json",
                "required": False,
                "label": "Headers",
                "placeholder": '{"Content-Type": "application/json"}',
                "help": "HTTP headers as JSON object",
            },
            "body": {
                "type": "json",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"name": "John", "email": "john@example.com"}',
                "help": "Request body as JSON",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Request timeout",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "api_response",
                "help": "Store response in variable",
            },
        },
    },
    "api.put": {
        "category": "API",
        "label": "PUT Request",
        "description": "Send HTTP PUT request",
        "icon": "🔄",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://api.example.com/users/123",
                "help": "API endpoint URL",
            },
            "headers": {
                "type": "json",
                "required": False,
                "label": "Headers",
                "placeholder": '{"Content-Type": "application/json"}',
                "help": "HTTP headers as JSON object",
            },
            "body": {
                "type": "json",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"name": "John Updated"}',
                "help": "Request body as JSON",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Request timeout",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "api_response",
                "help": "Store response in variable",
            },
        },
    },
    "api.patch": {
        "category": "API",
        "label": "PATCH Request",
        "description": "Send HTTP PATCH request",
        "icon": "🔧",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://api.example.com/users/123",
                "help": "API endpoint URL",
            },
            "headers": {
                "type": "json",
                "required": False,
                "label": "Headers",
                "placeholder": '{"Content-Type": "application/json"}',
                "help": "HTTP headers as JSON object",
            },
            "body": {
                "type": "json",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"email": "newemail@example.com"}',
                "help": "Request body as JSON",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Request timeout",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "api_response",
                "help": "Store response in variable",
            },
        },
    },
    "api.delete": {
        "category": "API",
        "label": "DELETE Request",
        "description": "Send HTTP DELETE request",
        "icon": "🗑️",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "URL",
                "placeholder": "https://api.example.com/users/123",
                "help": "API endpoint URL",
            },
            "headers": {
                "type": "json",
                "required": False,
                "label": "Headers",
                "placeholder": '{"Authorization": "Bearer token"}',
                "help": "HTTP headers as JSON object",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Request timeout",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "api_response",
                "help": "Store response in variable",
            },
        },
    },
    # ==================== AWS S3 ACTIONS ====================
    "aws.list_files": {
        "category": "AWS",
        "label": "List S3 Files",
        "description": "List files in S3 bucket",
        "icon": "📂",
        "parameters": {
            "bucket_name": {
                "type": "text",
                "required": True,
                "label": "Bucket Name",
                "placeholder": "my-bucket",
                "help": "S3 bucket name",
            },
            "folder_prefix": {
                "type": "text",
                "required": False,
                "label": "Folder Prefix",
                "placeholder": "firmware/",
                "help": "Filter by folder path",
            },
            "file_extension": {
                "type": "text",
                "required": False,
                "label": "File Extension",
                "placeholder": ".bin",
                "help": "Filter by file extension",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "file_list",
                "help": "Store results in variable",
            },
        },
    },
    "aws.get_latest": {
        "category": "AWS",
        "label": "Get Latest S3 File",
        "description": "Get most recent file from S3",
        "icon": "🆕",
        "parameters": {
            "bucket_name": {
                "type": "text",
                "required": True,
                "label": "Bucket Name",
                "placeholder": "my-bucket",
                "help": "S3 bucket name",
            },
            "folder_prefix": {
                "type": "text",
                "required": False,
                "label": "Folder Prefix",
                "placeholder": "firmware/",
                "help": "Filter by folder path",
            },
            "file_extension": {
                "type": "text",
                "required": False,
                "label": "File Extension",
                "placeholder": ".bin",
                "help": "Filter by file extension",
            },
            "store_as": {
                "type": "text",
                "required": True,
                "label": "Variable Name",
                "placeholder": "latest_firmware",
                "help": "Store file info in variable",
            },
        },
    },
    "aws.download": {
        "category": "AWS",
        "label": "Download from S3",
        "description": "Download file from S3 bucket",
        "icon": "⬇️",
        "parameters": {
            "bucket_name": {
                "type": "text",
                "required": True,
                "label": "Bucket Name",
                "placeholder": "my-bucket",
                "help": "S3 bucket name",
            },
            "key": {
                "type": "text",
                "required": True,
                "label": "Object Key",
                "placeholder": "firmware/file.bin",
                "help": "S3 object key (path)",
            },
            "local_path": {
                "type": "file",
                "required": True,
                "label": "Local Path",
                "placeholder": "/tmp/file.bin",
                "help": "Where to save the file",
            },
        },
    },
    "aws.upload": {
        "category": "AWS",
        "label": "Upload to S3",
        "description": "Upload file to S3 bucket",
        "icon": "⬆️",
        "parameters": {
            "bucket_name": {
                "type": "text",
                "required": True,
                "label": "Bucket Name",
                "placeholder": "my-bucket",
                "help": "S3 bucket name",
            },
            "key": {
                "type": "text",
                "required": True,
                "label": "Object Key",
                "placeholder": "uploads/file.bin",
                "help": "S3 object key (destination path)",
            },
            "file_path": {
                "type": "file",
                "required": True,
                "label": "Local File Path",
                "placeholder": "/path/to/file.bin",
                "help": "Local file to upload",
            },
        },
    },
    "aws.delete": {
        "category": "AWS",
        "label": "Delete from S3",
        "description": "Delete file from S3 bucket",
        "icon": "🗑️",
        "parameters": {
            "bucket_name": {
                "type": "text",
                "required": True,
                "label": "Bucket Name",
                "placeholder": "my-bucket",
                "help": "S3 bucket name",
            },
            "key": {
                "type": "text",
                "required": True,
                "label": "Object Key",
                "placeholder": "old/file.bin",
                "help": "S3 object key to delete",
            },
        },
    },
    # ==================== OVRC API ACTIONS ====================
    "ovrc.connect": {
        "category": "OvrC API",
        "label": "Connect OvrC API",
        "description": "Connect to OvrC API (WebSocket and/or HTTP)",
        "icon": "🔌",
        "parameters": {
            "server_url": {
                "type": "text",
                "required": True,
                "label": "WebSocket URL",
                "placeholder": "ws://192.168.1.100:8080",
                "help": "WebSocket server URL (optional)",
            },
            "api_base_url": {
                "type": "text",
                "required": False,
                "label": "API Base URL",
                "placeholder": "https://api.ovrc.com",
                "help": "HTTP API base URL (optional)",
            },
            "device_id": {
                "type": "text",
                "required": True,
                "label": "Device ID",
                "placeholder": "4B:00:00:00:00:15",
                "help": "Device MAC address (for WebSocket)",
            },
            "auth_type": {
                "type": "select",
                "required": False,
                "label": "Auth Type",
                "options": ["bearer", "basic", "api_key", "custom"],
                "default": "bearer",
                "help": "Authentication type for HTTP API",
            },
            "auth_token": {
                "type": "text",
                "required": False,
                "label": "Bearer Token",
                "placeholder": "your-token-here",
                "help": "Bearer token for authentication",
            },
            "api_key": {
                "type": "text",
                "required": False,
                "label": "API Key",
                "placeholder": "your-api-key",
                "help": "API key for authentication",
            },
            "auth_username": {
                "type": "text",
                "required": False,
                "label": "Username",
                "placeholder": "username",
                "help": "Username for basic auth",
            },
            "auth_password": {
                "type": "text",
                "required": False,
                "label": "Password",
                "placeholder": "password",
                "help": "Password for basic auth",
            },
            "verbose_logging": {
                "type": "boolean",
                "required": False,
                "label": "Verbose Logging",
                "default": False,
                "help": "Show full request/response details (headers, body, etc.). Can also be set via 'verbose_logging' or 'show_full_response' variable.",
            },
        },
    },
    "ovrc.http.request": {
        "category": "OvrC API",
        "label": "OvrC API Request",
        "description": "Make HTTP request (GET/POST/PUT/PATCH/DELETE) to OvrC API with automatic authentication",
        "icon": "📡",
        "parameters": {
            "method": {
                "type": "select",
                "required": True,
                "label": "HTTP Method",
                "options": [
                    {"value": "GET", "label": "GET"},
                    {"value": "POST", "label": "POST"},
                    {"value": "PUT", "label": "PUT"},
                    {"value": "PATCH", "label": "PATCH"},
                    {"value": "DELETE", "label": "DELETE"},
                ],
                "default": "GET",
                "help": "HTTP method for the request",
            },
            "endpoint": {
                "type": "text",
                "required": True,
                "label": "Endpoint",
                "placeholder": "/api/v1/devices",
                "help": "API endpoint path (e.g., /api/v1/devices, /api/v1/devices/{id})",
            },
            "query_params": {
                "type": "keyvalue",
                "required": False,
                "label": "Query Parameters",
                "placeholder": '{"key": "value"}',
                "help": "Query parameters (for GET requests) as key-value pairs",
            },
            "json_data": {
                "type": "keyvalue",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"key": "value"}',
                "help": "JSON body for POST/PUT/PATCH requests as key-value pairs",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response in variable",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "default": 30,
                "help": "Request timeout in seconds",
            },
        },
    },
    "ovrc.http.get": {
        "category": "OvrC API",
        "label": "OvrC API GET",
        "description": "Make GET request to OvrC API with automatic authentication",
        "icon": "📡",
        "parameters": {
            "endpoint": {
                "type": "text",
                "required": True,
                "label": "Endpoint",
                "placeholder": "/api/v1/devices",
                "help": "API endpoint path",
            },
            "params": {
                "type": "keyvalue",
                "required": False,
                "label": "Query Parameters",
                "placeholder": '{"key": "value"}',
                "help": "Query parameters as key-value pairs or JSON",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response in variable",
            },
        },
    },
    "ovrc.http.post": {
        "category": "OvrC API",
        "label": "OvrC API POST",
        "description": "Make POST request to OvrC API with automatic authentication",
        "icon": "📡",
        "parameters": {
            "endpoint": {
                "type": "text",
                "required": True,
                "label": "Endpoint",
                "placeholder": "/api/v1/devices",
                "help": "API endpoint path",
            },
            "json_data": {
                "type": "json",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"key": "value"}',
                "help": "JSON body for POST request",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response in variable",
            },
        },
    },
    "ovrc.http.put": {
        "category": "OvrC API",
        "label": "OvrC API PUT",
        "description": "Make PUT request to OvrC API with automatic authentication",
        "icon": "📡",
        "parameters": {
            "endpoint": {
                "type": "text",
                "required": True,
                "label": "Endpoint",
                "placeholder": "/api/v1/devices",
                "help": "API endpoint path",
            },
            "json_data": {
                "type": "json",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"key": "value"}',
                "help": "JSON body for PUT request",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response in variable",
            },
        },
    },
    "ovrc.http.patch": {
        "category": "OvrC API",
        "label": "OvrC API PATCH",
        "description": "Make PATCH request to OvrC API with automatic authentication",
        "icon": "📡",
        "parameters": {
            "endpoint": {
                "type": "text",
                "required": True,
                "label": "Endpoint",
                "placeholder": "/api/v1/devices",
                "help": "API endpoint path",
            },
            "json_data": {
                "type": "json",
                "required": False,
                "label": "Request Body",
                "placeholder": '{"key": "value"}',
                "help": "JSON body for PATCH request",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response in variable",
            },
        },
    },
    "ovrc.http.delete": {
        "category": "OvrC API",
        "label": "OvrC API DELETE",
        "description": "Make DELETE request to OvrC API with automatic authentication",
        "icon": "📡",
        "parameters": {
            "endpoint": {
                "type": "text",
                "required": True,
                "label": "Endpoint",
                "placeholder": "/api/v1/devices",
                "help": "API endpoint path",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response in variable",
            },
        },
    },
    "ovrc.disconnect": {
        "category": "OvrC API",
        "label": "Disconnect OvrC API",
        "description": "Disconnect from OvrC WebSocket server",
        "icon": "🔌",
        "parameters": {},
    },
    "ovrc.send": {
        "category": "OvrC API",
        "label": "Send OvrC Command",
        "description": "Send a custom JSON-RPC command to OvrC WebSocket (flexible method name)",
        "icon": "📤",
        "parameters": {
            "method": {
                "type": "text",
                "required": True,
                "label": "Method Name",
                "placeholder": "dxGetAbout",
                "help": "JSON-RPC method name (e.g., dxGetAbout, dsStartDeviceUpdates, dxGetNetworkSettings)",
                "suggestions": [
                    "dxGetAbout",
                    "dsStartDeviceUpdates",
                    "dsStopDeviceUpdates",
                    "dxGetNetworkSettings",
                    "dxSetNetworkSettings",
                    "dxGetTimeSettings",
                    "dxSetTimeSettings",
                    "dxGetStatusUpdateFrequency",
                    "dxSetStatusUpdateFrequency",
                    "dxEnableWebConnect",
                    "dxDisableWebConnect",
                    "dxSetCloudServerUrl",
                    "dxDisableCloud",
                    "dxUpdateFirmware",
                    "dxFindDeviceBySerial",
                    "dxResetDevice",
                ],
            },
            "params": {
                "type": "keyvalue",
                "required": False,
                "label": "Parameters",
                "placeholder": '{"deviceId": "D4:6A:91:E5:B7:3B", "version": 0}',
                "help": "Method parameters as key-value pairs or JSON object",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "response",
                "help": "Store response result in variable",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "10",
                "default": 10,
                "help": "Maximum time to wait for response",
            },
        },
    },
    "ovrc.start device updates": {
        "category": "OvrC API",
        "label": "Start Device Updates",
        "description": "Start receiving device status updates via WebSocket",
        "icon": "📊",
        "parameters": {
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "device_status",
                "help": "Store device status in variable",
            }
        },
    },
    "ovrc.stop device updates": {
        "category": "OvrC API",
        "label": "Stop Device Updates",
        "description": "Stop receiving device status updates",
        "icon": "⏹️",
        "parameters": {},
    },
    "ovrc.get about": {
        "category": "OvrC API",
        "label": "Get Device Info",
        "description": "Get device information (firmware, model, serial, etc.)",
        "icon": "ℹ️",
        "parameters": {
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "device_info",
                "help": "Store device information in variable",
            }
        },
    },
    "ovrc.reset device": {
        "category": "OvrC API",
        "label": "Reset Device",
        "description": "Reset device to factory defaults",
        "icon": "🔄",
        "parameters": {},
    },
    "ovrc.get network settings": {
        "category": "OvrC API",
        "label": "Get Network Settings",
        "description": "Retrieve current network configuration",
        "icon": "🌐",
        "parameters": {
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "network_settings",
                "help": "Store network settings in variable",
            }
        },
    },
    "ovrc.set network settings": {
        "category": "OvrC API",
        "label": "Set Network Settings",
        "description": "Configure device network settings",
        "icon": "⚙️",
        "parameters": {
            "device_name": {
                "type": "text",
                "required": False,
                "label": "Device Name",
                "placeholder": "My Device",
                "help": "Device name",
            },
            "device_ip": {
                "type": "text",
                "required": False,
                "label": "IP Address",
                "placeholder": "192.168.1.100",
                "help": "Device IP address",
            },
            "subnet_mask": {
                "type": "text",
                "required": False,
                "label": "Subnet Mask",
                "placeholder": "255.255.255.0",
                "help": "Subnet mask",
            },
            "gateway": {
                "type": "text",
                "required": False,
                "label": "Gateway",
                "placeholder": "192.168.1.1",
                "help": "Default gateway",
            },
            "dhcp_enabled": {
                "type": "boolean",
                "required": False,
                "label": "DHCP Enabled",
                "help": "Enable DHCP",
            },
        },
    },
    "ovrc.get time settings": {
        "category": "OvrC API",
        "label": "Get Time Settings",
        "description": "Retrieve time zone and current time",
        "icon": "🕐",
        "parameters": {
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "time_settings",
                "help": "Store time settings in variable",
            }
        },
    },
    "ovrc.set time settings": {
        "category": "OvrC API",
        "label": "Set Time Settings",
        "description": "Configure time zone and current time",
        "icon": "🕐",
        "parameters": {
            "timezone_name": {
                "type": "text",
                "required": True,
                "label": "Timezone Name",
                "placeholder": "America/New_York",
                "help": "Timezone name (e.g., America/New_York)",
            },
            "timezone_notes": {
                "type": "text",
                "required": False,
                "label": "Timezone Notes",
                "placeholder": "Eastern Time (US & Canada)",
                "help": "Timezone description",
            },
            "utc_offset_minutes": {
                "type": "number",
                "required": False,
                "label": "UTC Offset (minutes)",
                "placeholder": "300",
                "help": "UTC offset in minutes (e.g., 300 for UTC-5)",
            },
        },
    },
    # ==================== JSON-RPC ACTIONS (Backward Compatibility) ====================
    "jsonrpc.connect": {
        "category": "JSON-RPC",
        "label": "Connect WebSocket",
        "description": "Connect to JSON-RPC WebSocket server (deprecated: use OvrC API)",
        "icon": "🔌",
        "parameters": {
            "url": {
                "type": "text",
                "required": True,
                "label": "WebSocket URL",
                "placeholder": "ws://192.168.1.100:8080",
                "help": "WebSocket server URL",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Connection timeout",
            },
        },
    },
    "jsonrpc.disconnect": {
        "category": "JSON-RPC",
        "label": "Disconnect WebSocket",
        "description": "Close JSON-RPC WebSocket connection",
        "icon": "🔌",
        "parameters": {},
    },
    "jsonrpc.send": {
        "category": "JSON-RPC",
        "label": "Send JSON-RPC Request",
        "description": "Send JSON-RPC method call",
        "icon": "📡",
        "parameters": {
            "method": {
                "type": "text",
                "required": True,
                "label": "Method Name",
                "placeholder": "getAbout",
                "help": "JSON-RPC method to call",
            },
            "params": {
                "type": "json",
                "required": False,
                "label": "Parameters",
                "placeholder": '{"key": "value"}',
                "help": "Method parameters as JSON",
            },
            "store_as": {
                "type": "text",
                "required": False,
                "label": "Variable Name",
                "placeholder": "rpc_response",
                "help": "Store response in variable",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "30",
                "help": "Request timeout",
            },
        },
    },
    # ==================== TEST & ASSERTION ACTIONS ====================
    "log": {
        "category": "Test",
        "label": "Log Message",
        "description": "Print a message to the console (supports variable substitution)",
        "icon": "📝",
        "parameters": {
            "message": {
                "type": "textarea",
                "required": True,
                "label": "Message",
                "placeholder": "Network Settings: ${network_settings}",
                "help": "Message to log (use ${variable} for variable substitution)",
            }
        },
    },
    "test.assert": {
        "category": "Test",
        "label": "Assert Condition",
        "description": "Assert that condition is true",
        "icon": "✅",
        "parameters": {
            "expression": {
                "type": "text",
                "required": True,
                "label": "Expression",
                "placeholder": "status_code == 200",
                "help": "Python expression to evaluate",
            },
            "message": {
                "type": "text",
                "required": False,
                "label": "Error Message",
                "placeholder": "Status code should be 200",
                "help": "Message to show on failure",
            },
        },
    },
    "test.assert_schema": {
        "category": "Test",
        "label": "Validate JSON Schema",
        "description": "Validate response against JSON schema",
        "icon": "📋",
        "parameters": {
            "data": {
                "type": "text",
                "required": True,
                "label": "Data Variable",
                "placeholder": "api_response",
                "help": "Variable containing data to validate",
            },
            "schema": {
                "type": "json",
                "required": True,
                "label": "JSON Schema",
                "placeholder": '{"type": "object", "properties": {...}}',
                "help": "JSON schema to validate against",
            },
        },
    },
    "test.assert_response": {
        "category": "Test",
        "label": "Assert API Response",
        "description": "Assert API response properties",
        "icon": "🔍",
        "parameters": {
            "response": {
                "type": "text",
                "required": True,
                "label": "Response Variable",
                "placeholder": "api_response",
                "help": "Variable containing API response",
            },
            "status_code": {
                "type": "number",
                "required": False,
                "label": "Expected Status Code",
                "placeholder": "200",
                "help": "Expected HTTP status code",
            },
            "contains": {
                "type": "text",
                "required": False,
                "label": "Contains Text",
                "placeholder": "success",
                "help": "Response should contain this text",
            },
        },
    },
    "test.check_assertions": {
        "category": "Test",
        "label": "Check Soft Assertions",
        "description": "Check all collected soft assertions",
        "icon": "📊",
        "parameters": {},
    },
    "test.assert_element_visible": {
        "category": "Test",
        "label": "Assert Element Visible",
        "description": "Assert that an element is visible on the page",
        "icon": "👁️",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#submit-button",
                "help": "CSS selector for the element",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "10",
                "help": "Maximum time to wait for element",
            },
        },
    },
    "test.assert_element_not_visible": {
        "category": "Test",
        "label": "Assert Element Not Visible",
        "description": "Assert that an element is not visible on the page",
        "icon": "🚫",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#loading-spinner",
                "help": "CSS selector for the element",
            },
            "timeout": {
                "type": "number",
                "required": False,
                "label": "Timeout (seconds)",
                "placeholder": "10",
                "help": "Maximum time to wait for element to disappear",
            },
        },
    },
    "test.assert_element_enabled": {
        "category": "Test",
        "label": "Assert Element Enabled",
        "description": "Assert that an element is enabled and interactive",
        "icon": "✅",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#submit-button",
                "help": "CSS selector for the element",
            }
        },
    },
    "test.assert_element_disabled": {
        "category": "Test",
        "label": "Assert Element Disabled",
        "description": "Assert that an element is disabled",
        "icon": "❌",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#submit-button",
                "help": "CSS selector for the element",
            }
        },
    },
    "test.assert_text_contains": {
        "category": "Test",
        "label": "Assert Text Contains",
        "description": "Assert that an element's text contains expected value",
        "icon": "📝",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#message",
                "help": "CSS selector for the element",
            },
            "text": {
                "type": "text",
                "required": True,
                "label": "Expected Text",
                "placeholder": "Success",
                "help": "Text that should be contained in the element",
            },
        },
    },
    "test.assert_text_equals": {
        "category": "Test",
        "label": "Assert Text Equals",
        "description": "Assert that an element's text exactly matches expected value",
        "icon": "📋",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": "#title",
                "help": "CSS selector for the element",
            },
            "text": {
                "type": "text",
                "required": True,
                "label": "Expected Text",
                "placeholder": "Welcome",
                "help": "Exact text that should match",
            },
        },
    },
    "test.assert_element_count": {
        "category": "Test",
        "label": "Assert Element Count",
        "description": "Assert the number of matching elements",
        "icon": "🔢",
        "parameters": {
            "selector": {
                "type": "text",
                "required": True,
                "label": "Element Selector",
                "placeholder": ".list-item",
                "help": "CSS selector for the elements",
            },
            "count": {
                "type": "number",
                "required": True,
                "label": "Expected Count",
                "placeholder": "5",
                "help": "Number of elements that should match",
            },
        },
    },
    "test.run": {
        "category": "Test",
        "label": "Run Test as Step",
        "description": "Execute another test as a reusable step. Variables from the called test can be accessed in the current test.",
        "icon": "🔄",
        "parameters": {
            "test_path": {
                "type": "text",
                "required": True,
                "label": "Test Path",
                "placeholder": "OvrC/ovrc_api_websocket_test.yaml",
                "help": "Path to the test file relative to tests/cases/ directory (e.g., OvrC/ovrc_api_websocket_test.yaml)",
            },
            "variables": {
                "type": "keyvalue",
                "required": False,
                "label": "Input Variables",
                "placeholder": '{"device_ip": "192.168.1.100"}',
                "help": "Variables to pass to the called test (key-value pairs)",
            },
            "store_variables": {
                "type": "keyvalue",
                "required": False,
                "label": "Extract Variables",
                "placeholder": '{"firmware_version": "about_result.firmware"}',
                "help": 'Extract variables from the called test\'s results. Format: {"variable_name": "path.to.value"} (e.g., {"fw_version": "about_result.firmware"})',
            },
            "continue_on_failure": {
                "type": "boolean",
                "required": False,
                "label": "Continue on Failure",
                "default": False,
                "help": "If true, continue test execution even if the called test fails",
            },
        },
    },
}


def get_actions_by_category() -> Dict[str, List[Dict[str, Any]]]:
    """Group actions by category for display"""
    categories: Dict[str, List[Dict[str, Any]]] = {}

    for action_id, definition in ACTION_DEFINITIONS.items():
        category = definition.get("category", "Other")
        if category not in categories:
            categories[category] = []

        categories[category].append(
            {
                "id": action_id,
                "label": definition["label"],
                "description": definition["description"],
                "icon": definition.get("icon", "⚙️"),
                "parameters": definition["parameters"],
            }
        )

    return categories


def get_action_definition(action_id: str) -> Dict[str, Any]:
    """Get definition for a specific action"""
    return ACTION_DEFINITIONS.get(action_id, {})


def validate_action_parameters(
    action_id: str, params: Dict[str, Any]
) -> tuple[bool, List[str]]:
    """Validate parameters for an action"""
    errors = []
    definition = ACTION_DEFINITIONS.get(action_id)

    if not definition:
        return False, [f"Unknown action: {action_id}"]

    # Check required parameters
    for param_name, param_def in definition["parameters"].items():
        if param_def.get("required", False):
            if (
                param_name not in params
                or params[param_name] is None
                or params[param_name] == ""
            ):
                errors.append(f"Required parameter missing: {param_def['label']}")

    return len(errors) == 0, errors
