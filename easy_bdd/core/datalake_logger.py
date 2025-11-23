"""
Datalake Logger for Easy BDD Framework

Provides comprehensive logging with:
- Error hints and tracking
- Teams notifications
- Datalake metrics posting
- Console logging with Loguru

Author: Easy BDD Framework
Date: November 22, 2025
"""

import os
import sys
import io
import re
import json
import time
import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path

try:
    from loguru import logger as loguru_logger
    LOGURU_AVAILABLE = True
except ImportError:
    LOGURU_AVAILABLE = False
    print("Warning: loguru not installed. Install with: pip install loguru")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests not installed for Teams/Datalake posting")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class DatalakeLogger:
    """
    Comprehensive logger with error hints, Teams notifications, and datalake posting.
    """
    
    def __init__(
        self, 
        artifact_path: str = "reports/artifacts",
        post_results: bool = True,
        error_hint_subs: Optional[List[Tuple[str, str, str]]] = None
    ):
        """
        Initialize the datalake logger.
        
        Args:
            artifact_path: Path to store artifacts and logs
            post_results: Whether to post to Teams and Datalake
            error_hint_subs: Error hint substitutions (type, value, hint)
        """
        self.artifact_path = Path(artifact_path)
        self.artifact_path.mkdir(parents=True, exist_ok=True)
        
        self.post_results = post_results
        self.error_hint_subs = error_hint_subs or []
        self.skip_errors_type_set = set(["builtins.AssertionError"])
        
        self.logger = None
        if LOGURU_AVAILABLE:
            self.configure_logger()
        else:
            print("Loguru not available, using print fallback")
    
    def configure_logger(self):
        """Configure Loguru logger with custom sinks."""
        if not LOGURU_AVAILABLE:
            return
        
        self.logger = loguru_logger
        
        if self.post_results:
            # Remove default handler
            self.logger.remove()
            
            # Console output for INFO and WARNING
            self.logger.add(
                sys.stdout,
                level="INFO",
                filter=lambda record: record["level"].no <= self.logger.level("WARNING").no,
                colorize=True,
                format="{message}"
            )
            
            # Error sink with limited traceback
            self.logger.add(
                self.limited_traceback_sink,
                level='ERROR',
                format="{message}",
                backtrace=False,
                diagnose=True,
                colorize=True
            )
    
    def console2file(self):
        """Add file sink for console output."""
        if not LOGURU_AVAILABLE:
            return
        
        self.logger.add(
            self.artifact_path / "console.log",
            level="DEBUG",
            backtrace=True,
            diagnose=True,
            enqueue=True,
            retention="1 day",
        )
    
    def log(self, level: str, message: str):
        """Log a message at the specified level."""
        if self.logger:
            return self.logger.opt(depth=2).log(level, message)
        else:
            print(f"[{level}] {message}")
    
    def debug(self, message: str):
        """Log debug message."""
        self.log("DEBUG", message)
    
    def info(self, message: str):
        """Log info message."""
        self.log("INFO", message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.log("WARNING", message)
    
    def error(self, message: str):
        """Log error message."""
        self.log("ERROR", message)
    
    def critical(self, message: str):
        """Log critical message."""
        self.log("CRITICAL", message)
    
    def exception(self, message: str):
        """Log exception with traceback."""
        if self.logger:
            self.logger.opt(exception=True).error(message)
        else:
            print(f"[EXCEPTION] {message}")
    
    def opt(self, *args, **kwargs):
        """Pass through to logger.opt for advanced options."""
        if self.logger:
            return self.logger.opt(*args, **kwargs)
        return self
    
    def limited_traceback_sink(self, message):
        """
        Custom sink that logs errors with limited traceback to project files.
        Also posts to Teams if configured.
        """
        record = message.record
        exception_info = record.get("exception")
        
        exception_details = {}
        exception_type = str(message)
        exception_value = ""
        
        if exception_info:
            original_exception = exception_info.value
            exception_type = f"{type(original_exception).__module__}.{type(original_exception).__name__}"
            exception_value = str(original_exception)
            
            # Get project path
            project_path = os.getcwd()
            project_path = os.path.join(project_path, 'easy_bdd')
            
            if original_exception:
                tb = original_exception.__traceback__
                
                # Find last frame within project
                last_project_frame = None
                while tb:
                    frame = tb.tb_frame
                    filename = frame.f_code.co_filename
                    
                    if filename.startswith(project_path):
                        last_project_frame = tb
                    
                    tb = tb.tb_next
                
                if last_project_frame:
                    frame = last_project_frame.tb_frame
                    filename = frame.f_code.co_filename
                    line_number = last_project_frame.tb_lineno
                    function_name = frame.f_code.co_name
                    
                    formatted_frame = f'  File "{filename}", line {line_number}, in {function_name}'
                    exception_details.update({
                        "frame": formatted_frame,
                        "variables": dict(frame.f_locals.items())
                    })
        
        exception_raw = f"{exception_type}: {exception_value}"
        
        if self.logger:
            self.logger.opt(depth=0).log("WARNING", f"\n{exception_raw}")
        
        # Get error hint
        hint = self.error_hint(exception_type, exception_value)
        hint = hint if hint else "See console for details"
        
        if self.logger:
            self.logger.opt(depth=0).log("WARNING", f"\nHint: {hint}")
        
        # Post to Teams if not a duplicate error type
        if exception_type not in self.skip_errors_type_set:
            self.teams_post(
                message=f"{exception_raw}\n{hint}",
                request="Test execution",
                run_name="Easy BDD Test Run",
                object_id="TEST001"
            )
        
        self.skip_errors_type_set.add(exception_type)
    
    def error_hint(self, param1: str, param2: str) -> Optional[str]:
        """
        Get an error hint based on exception type and value.
        
        Args:
            param1: Exception type
            param2: Exception value
        
        Returns:
            Error hint string or None
        """
        ignore_case = True
        
        param1 = str(param1)
        param2 = str(param2)
        
        try:
            for col1, col2, col3 in self.error_hint_subs:
                # Check first column matches
                if col1 and (col1.lower() not in param1.lower() if ignore_case else col1 not in param1):
                    continue
                
                # Check second column
                match2 = not col2 or (col2.lower() in param2.lower() if ignore_case else col2 in param2)
                if match2:
                    try:
                        hint = eval(col3)
                    except:
                        hint = f"{col3}"
                    return hint + "."
            
            # Try GPT hint if available
            return self.gpt_hint(param1, param2)
        except:
            return None
    
    def gpt_hint(self, param1: str, param2: str) -> Optional[str]:
        """
        Get an error hint from GPT-3.5.
        
        Args:
            param1: Exception type
            param2: Exception value
        
        Returns:
            GPT-generated hint or None
        """
        if not OPENAI_AVAILABLE:
            return None
        
        if not os.environ.get('OPENAI_API_KEY'):
            return None
        
        try:
            client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
            
            messages = [
                {
                    "role": "system",
                    "content": "You're an experienced Python developer explaining errors in one sentence using up to 10 words strictly."
                },
                {
                    "role": "user",
                    "content": f"{param1}: {param2}"
                }
            ]
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                max_tokens=50,
                temperature=0.3,
                top_p=0.1
            )
            
            if self.logger:
                self.logger.debug(f"GPT raw response: {response}")
            
            gpt_response = response.choices[0].message.content + " (gpt)"
            
            # Cache this hint
            self.error_hint_subs.append([param1, param2, gpt_response])
            
            return gpt_response
        except Exception as e:
            if self.logger:
                self.logger.debug(f"GPT hint failed: {e}")
            return None
    
    def teams_post(
        self,
        message: str,
        request: str = "",
        run_name: str = "",
        object_id: str = "T000000"
    ) -> Dict[str, Any]:
        """
        Post a message to Microsoft Teams.
        
        Args:
            message: Message to post
            request: Request description
            run_name: Test run name
            object_id: Test object ID
        
        Returns:
            Response dict
        """
        if not REQUESTS_AVAILABLE:
            return {"error": "requests library not available"}
        
        # Teams webhook URL (can be configured)
        url = os.environ.get(
            'TEAMS_WEBHOOK_URL',
            "https://prod-178.westus.logic.azure.com:443/workflows/bd547a7ba2e34cfdb790b293cf6ab48b/triggers/manual/paths/invoke?api-version=2016-06-01&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=PHGVoHgBdwRxvENue3yS6dj3h2KU4AjX08jsm88JUoo"
        )
        
        headers = {'Content-Type': 'application/json'}
        
        test_desc = f"[{run_name} {object_id}]\n"
        my_message = f"{request}\n\n{message}"
        full_message = f"{test_desc}\n{my_message}"
        
        teams_adaptive_card = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": full_message,
                                "wrap": True
                            }
                        ],
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "version": "1.2"
                    }
                }
            ]
        }
        
        if self.post_results:
            try:
                response = requests.post(url, headers=headers, json=teams_adaptive_card, timeout=10)
                if response.status_code != 202:
                    if self.logger:
                        self.logger.warning(f"Teams error {response.status_code}: {response.text}")
                return {"status": response.status_code, "text": response.text}
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Teams post failed: {e}")
                return {"error": str(e)}
        else:
            return {'teams_message': f"{test_desc}\n{my_message}"}
    
    def datalake_post(
        self,
        test_name: str,
        product: str,
        product_category: str,
        mac_address: str,
        time_savings: float,
        start_time: datetime.datetime,
        console: str,
        run_url: str,
        success: bool,
        type: str = "testrail"
    ) -> bool:
        """
        Post test results to datalake.
        
        Args:
            test_name: Name of the test
            product: Product being tested
            product_category: Product category
            mac_address: Device MAC address
            time_savings: Estimated time saved (minutes)
            start_time: Test start time
            console: Console output/log
            run_url: URL to test run
            success: Whether test passed
            type: Test type identifier
        
        Returns:
            True if successful
        """
        if not REQUESTS_AVAILABLE:
            return False
        
        end_time = datetime.datetime.now().replace(microsecond=0)
        
        total_time = end_time - start_time
        
        datalake = {
            "start_time": str(start_time),
            "product": product,
            "mac_address": mac_address,
            "success": success,
            "end_time": str(end_time),
            "total_time": str(total_time),
            
            "type": type,
            "parameters": {
                "console": console,
                "testrail": run_url
            },
            "test_name": test_name,
            "time_savings": max(total_time.total_seconds() / 60, time_savings),
            "product_category": product_category,
        }
        
        url = 'https://jpdsauto.snapone.com/publish'
        headers = {
            'Content-Type': 'application/json',
            'X-api-key': 'FiORf06Q3g6m6dEigH8YE85BANHKaHnA3FRBxlON',
        }
        
        datalake_json = json.dumps(datalake, ensure_ascii=False, indent=4)
        
        response = ""
        
        if self.post_results:
            response = requests.request("PUT", url=url, headers=headers, data=datalake_json)
            
            if response.status_code != 200:
                response = requests.request("PUT", url=url, headers=headers, data=datalake_json)
                if self.logger:
                    self.logger.exception(f"Datalake's API returns {response.status_code=}: {response.text}")
        
        if self.logger:
            self.logger.debug(f"\nDatalake data: {datalake_json}\n{response}")
        
        return True
    
    def func_starting_log(
        self,
        request: str = "",
        request_display: str = "",
        step_number: int = 0,
        nested: bool = False
    ):
        """
        Log function/step start.
        
        Args:
            request: Request details
            request_display: Display-friendly request
            step_number: Step number
            nested: Whether this is a nested call
        """
        if not request_display:
            request_display = request
        
        level = "DEBUG" if nested else "INFO"
        
        if self.logger:
            self.logger.log(level, f"\n{'-'*25} Step {step_number} {'-'*25}")
            self.logger.log(level, f"<-- {request_display}")
    
    def func_finishing_log(
        self,
        response: Any = None,
        nested: bool = False
    ):
        """
        Log function/step completion.
        
        Args:
            response: Response data
            nested: Whether this is a nested call
        """
        level = "DEBUG" if nested else "INFO"
        
        if self.logger:
            self.logger.log(level, f"--> Response: {response}")
    
    def wrapper(self, func):
        """
        Decorator that displays info about function with parameters.
        
        Args:
            func: Function to wrap
        
        Returns:
            Wrapped function
        """
        def my_inner(*args, **kwargs):
            if self.logger:
                self.logger.debug(f"{func.__name__}({args}, {kwargs}) has started")
            
            request = f"{func.__name__}({args}, {kwargs})"
            request_display = kwargs.get("request_display", request)
            nested = kwargs.get("nested", False)
            
            self.func_starting_log(
                request=request,
                request_display=request_display,
                nested=nested
            )
            
            # Execute function
            response = func(*args, **kwargs)
            
            if self.logger:
                self.logger.debug(f"{func.__name__} response={response}")
            
            self.func_finishing_log(response=response, nested=nested)
            
            return response
        
        return my_inner


# Singleton instance
_logger_instance = None


def get_logger(
    artifact_path: str = "reports/artifacts",
    post_results: bool = True
) -> DatalakeLogger:
    """
    Get or create singleton logger instance.
    
    Args:
        artifact_path: Path to store artifacts
        post_results: Whether to post to Teams/Datalake
    
    Returns:
        DatalakeLogger instance
    """
    global _logger_instance
    
    if _logger_instance is None:
        _logger_instance = DatalakeLogger(
            artifact_path=artifact_path,
            post_results=post_results
        )
    
    return _logger_instance
