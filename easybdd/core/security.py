"""
Sensitive data masking utilities for Easy BDD Framework

Helps prevent accidental exposure of sensitive information in logs and reports.
"""

import re
from typing import Any, Dict, List, Union


class SensitiveDataMasker:
    """Mask sensitive data in logs, reports, and output."""

    # Patterns for sensitive data
    SENSITIVE_PATTERNS = {
        "password": r'(?i)(password|passwd|pwd)[\s:=]+["\']?([^"\'\s]+)',
        "token": r'(?i)(token|bearer|jwt|api[_-]?key)[\s:=]+["\']?([A-Za-z0-9\-_.]+)',
        "secret": r'(?i)(secret|key)[\s:=]+["\']?([^"\'\s]+)',
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "aws_key": r"(?i)(?:AKIA|ASIA)[A-Z0-9]{16}",
    }

    # Keys to mask in dictionaries
    SENSITIVE_KEYS = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "api_key",
        "apikey",
        "access_key",
        "private_key",
        "credential",
        "auth",
        "authorization",
        "bearer",
        "secret_access_key",
        "aws_secret_access_key",
        "client_secret",
        "oauth_secret",
    }

    def __init__(self, mask_char: str = "*", show_last: int = 4):
        """
        Initialize masker.

        Args:
            mask_char: Character to use for masking
            show_last: Number of characters to show at end (0 to hide all)
        """
        self.mask_char = mask_char
        self.show_last = show_last

    def mask_string(self, text: str, preserve_length: bool = False) -> str:
        """
        Mask sensitive data in a string.

        Args:
            text: Input string
            preserve_length: If True, preserve original length with masks

        Returns:
            Masked string
        """
        if not text or not isinstance(text, str):
            return text

        masked = text

        # Apply pattern matching
        for name, pattern in self.SENSITIVE_PATTERNS.items():
            masked = re.sub(
                pattern,
                lambda m: f"{m.group(1)}={self._mask_value(m.group(2), preserve_length)}",
                masked,
            )

        return masked

    def mask_dict(self, data: Dict[str, Any], deep: bool = True) -> Dict[str, Any]:
        """
        Mask sensitive keys in a dictionary.

        Args:
            data: Dictionary to mask
            deep: If True, recursively mask nested dicts

        Returns:
            Dictionary with masked values
        """
        if not isinstance(data, dict):
            return data

        masked = {}

        for key, value in data.items():
            key_lower = key.lower()

            # Check if key is sensitive
            if any(sensitive in key_lower for sensitive in self.SENSITIVE_KEYS):
                masked[key] = self._mask_value(value, preserve_length=True)
            elif deep and isinstance(value, dict):
                masked[key] = self.mask_dict(value, deep=True)
            elif deep and isinstance(value, list):
                masked[key] = [
                    self.mask_dict(item, deep=True) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                masked[key] = value

        return masked

    def mask_list(self, items: List[Any]) -> List[Any]:
        """
        Mask sensitive data in a list.

        Args:
            items: List to process

        Returns:
            List with masked sensitive items
        """
        return [
            (
                self.mask_dict(item)
                if isinstance(item, dict)
                else self.mask_string(item) if isinstance(item, str) else item
            )
            for item in items
        ]

    def _mask_value(self, value: Any, preserve_length: bool = False) -> str:
        """
        Mask a single value.

        Args:
            value: Value to mask
            preserve_length: Preserve original length

        Returns:
            Masked value
        """
        if value is None:
            return None

        value_str = str(value)
        length = len(value_str)

        if length == 0:
            return value_str

        if preserve_length:
            if self.show_last > 0 and length > self.show_last:
                # Show last N characters
                mask_count = length - self.show_last
                return self.mask_char * mask_count + value_str[-self.show_last :]
            else:
                return self.mask_char * length
        else:
            # Fixed mask length
            if self.show_last > 0 and length > self.show_last:
                return f"{self.mask_char * 4}{value_str[-self.show_last:]}"
            else:
                return self.mask_char * 8

    def safe_log_message(self, message: str) -> str:
        """
        Create a safe version of a log message.

        Args:
            message: Log message

        Returns:
            Message with masked sensitive data
        """
        return self.mask_string(message, preserve_length=False)

    def safe_log_dict(self, data: Dict[str, Any]) -> str:
        """
        Create a safe string representation of a dictionary for logging.

        Args:
            data: Dictionary to log

        Returns:
            String representation with masked sensitive data
        """
        masked = self.mask_dict(data)
        return str(masked)


# Global instance for convenience
_default_masker = SensitiveDataMasker()


def mask_sensitive_data(data: Union[str, Dict, List]) -> Union[str, Dict, List]:
    """
    Convenience function to mask sensitive data.

    Args:
        data: String, dict, or list containing potential sensitive data

    Returns:
        Data with sensitive information masked

    Example:
        >>> mask_sensitive_data({"password": "secret123", "user": "john"})
        {"password": "****et123", "user": "john"}
    """
    if isinstance(data, str):
        return _default_masker.mask_string(data)
    elif isinstance(data, dict):
        return _default_masker.mask_dict(data)
    elif isinstance(data, list):
        return _default_masker.mask_list(data)
    return data


def safe_print(message: str):
    """
    Print with sensitive data automatically masked.

    Args:
        message: Message to print
    """
    print(_default_masker.safe_log_message(message))
