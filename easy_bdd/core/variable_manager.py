"""
Centralized Variable and Configuration Management System
Handles variables, secrets, environment configs, and API authentication centrally
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re


@dataclass
class VariableScope:
    """Represents different variable scopes"""

    name: str
    priority: int  # Higher number = higher priority
    variables: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get variable value"""
        return self.variables.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set variable value"""
        self.variables[key] = value

    def update(self, variables: Dict[str, Any]) -> None:
        """Update multiple variables"""
        self.variables.update(variables)


@dataclass
class SecretConfig:
    """Configuration for secret handling"""

    provider: str = "env"  # env, file, vault, etc.
    path: Optional[str] = None
    prefix: Optional[str] = None
    encryption: bool = False


class VariableManager:
    """Central variable management system with scope hierarchy"""

    def __init__(self):
        self.scopes: List[VariableScope] = []
        self.secret_config = SecretConfig()
        self._setup_default_scopes()

    def _setup_default_scopes(self):
        """Setup default variable scopes in priority order"""
        # Lower priority (evaluated first, can be overridden)
        self.add_scope("framework_defaults", 1)
        self.add_scope("config_file", 2)
        self.add_scope("environment_vars", 3)
        self.add_scope("test_variables", 4)
        self.add_scope("runtime_data", 5)  # API responses, calculated values
        # Higher priority (evaluated last, overrides others)
        self.add_scope("session_overrides", 10)

    def add_scope(self, name: str, priority: int) -> VariableScope:
        """Add a new variable scope"""
        scope = VariableScope(name, priority)
        self.scopes.append(scope)
        self.scopes.sort(key=lambda s: s.priority)
        return scope

    def get_scope(self, name: str) -> Optional[VariableScope]:
        """Get scope by name"""
        return next((s for s in self.scopes if s.name == name), None)

    def set_variable(self, key: str, value: Any, scope: str = "runtime_data") -> None:
        """Set variable in specific scope"""
        target_scope = self.get_scope(scope)
        if target_scope:
            target_scope.set(key, value)

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get variable value using scope hierarchy (highest priority wins)"""
        # Check scopes in reverse priority order (highest first)
        for scope in reversed(self.scopes):
            if key in scope.variables:
                return scope.variables[key]
        return default

    def get_all_variables(self) -> Dict[str, Any]:
        """Get all variables merged across scopes (highest priority wins)"""
        merged = {}
        # Apply scopes in priority order (lowest to highest)
        for scope in self.scopes:
            merged.update(scope.variables)
        return merged

    def substitute_variables(
        self, text: str, additional_vars: Optional[Dict] = None
    ) -> str:
        """Substitute ${variable} patterns in text"""
        if not isinstance(text, str):
            return text

        # Get all variables and add any additional ones
        variables = self.get_all_variables()
        if additional_vars:
            variables.update(additional_vars)

        # Enhanced variable substitution with nested support
        def replace_var(match):
            var_name = match.group(1)

            # Support dot notation for nested access
            value = variables
            for part in var_name.split("."):
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # Variable not found, return original placeholder
                    return match.group(0)

            return str(value)

        # Replace ${variable} and ${object.property} patterns
        pattern = r"\$\{([^}]+)\}"
        result = re.sub(pattern, replace_var, text)
        return result

    def substitute_recursive(
        self, data: Any, additional_vars: Optional[Dict] = None
    ) -> Any:
        """Recursively substitute variables in data structures"""
        if isinstance(data, str):
            return self.substitute_variables(data, additional_vars)
        elif isinstance(data, dict):
            return {
                k: self.substitute_recursive(v, additional_vars)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self.substitute_recursive(item, additional_vars) for item in data]
        else:
            return data

    def load_environment_variables(self, prefix: Optional[str] = None):
        """Load environment variables into environment_vars scope"""
        env_scope = self.get_scope("environment_vars")
        env_vars = {}

        for key, value in os.environ.items():
            if prefix and not key.startswith(prefix):
                continue

            # Remove prefix if specified
            clean_key = key[len(prefix) :] if prefix else key

            # Try to parse as JSON for complex values
            try:
                parsed_value = json.loads(value)
                env_vars[clean_key] = parsed_value
            except (json.JSONDecodeError, ValueError):
                env_vars[clean_key] = value

        env_scope.update(env_vars)

    def load_config_file(self, config_path: Union[str, Path]):
        """Load variables from config file"""
        config_path = Path(config_path)
        if not config_path.exists():
            return

        with open(config_path, "r") as f:
            if config_path.suffix.lower() in [".yaml", ".yml"]:
                data = yaml.safe_load(f) or {}
            else:
                data = json.load(f)

        # Load framework config
        config_scope = self.get_scope("config_file")
        config_scope.update(data.get("variables", {}))

        # Also load environment-specific variables
        environments = data.get("environments", {})
        current_env = self.get_variable("ENVIRONMENT", "default")
        if current_env in environments:
            config_scope.update(environments[current_env])

    def save_session_state(self, file_path: Union[str, Path]):
        """Save current session state to file"""
        state = {
            "timestamp": datetime.now().isoformat(),
            "variables": self.get_all_variables(),
            "scopes": {
                scope.name: scope.variables for scope in self.scopes if scope.variables
            },
        }

        with open(file_path, "w") as f:
            json.dump(state, f, indent=2, default=str)

    def load_session_state(self, file_path: Union[str, Path]):
        """Load session state from file"""
        file_path = Path(file_path)
        if not file_path.exists():
            return

        with open(file_path, "r") as f:
            state = json.load(f)

        # Restore scope variables
        for scope_name, variables in state.get("scopes", {}).items():
            scope = self.get_scope(scope_name)
            if scope:
                scope.update(variables)


class APIConfigManager:
    """Centralized API configuration management"""

    def __init__(self, variable_manager: VariableManager):
        self.variable_manager = variable_manager
        self.auth_configs: Dict[str, Dict[str, Any]] = {}
        self.base_configs: Dict[str, Dict[str, Any]] = {}
        self.active_tokens: Dict[str, Dict[str, Any]] = {}

    def load_api_config(self, config_data: Dict[str, Any]):
        """Load API configuration from config data"""
        api_config = config_data.get("api", {})

        # Load base API configs
        self.base_configs.update(api_config)

        # Load authentication configs with variable substitution
        auth_configs = api_config.get("auth_configs", {})
        for device_id, config in auth_configs.items():
            # Substitute variables in auth config
            substituted_config = self.variable_manager.substitute_recursive(config)
            self.auth_configs[device_id] = substituted_config

    def get_auth_config(self, device_id: str) -> Dict[str, Any]:
        """Get authentication config for device with variable substitution"""
        if device_id in self.auth_configs:
            # Re-substitute in case variables have changed
            config = self.auth_configs[device_id]
            return self.variable_manager.substitute_recursive(config)

        # Try default config
        default_config = self.auth_configs.get("default", {})
        return self.variable_manager.substitute_recursive(default_config)

    def get_base_config(self, key: str, default: Any = None) -> Any:
        """Get base API configuration value"""
        value = self.base_configs.get(key, default)
        if isinstance(value, str):
            return self.variable_manager.substitute_variables(value)
        return value

    def store_token(self, device_id: str, token_data: Dict[str, Any]):
        """Store authentication token for device"""
        self.active_tokens[device_id] = {**token_data, "stored_at": datetime.now()}

        # Also store in runtime variables for access in tests
        self.variable_manager.set_variable(
            f"auth_token_{device_id}", token_data.get("token")
        )
        self.variable_manager.set_variable(
            f"auth_expires_{device_id}", token_data.get("expires_at")
        )

    def get_token(self, device_id: str) -> Optional[Dict[str, Any]]:
        """Get stored token for device"""
        return self.active_tokens.get(device_id)

    def clear_token(self, device_id: str):
        """Clear stored token for device"""
        if device_id in self.active_tokens:
            del self.active_tokens[device_id]

        # Clear from runtime variables
        self.variable_manager.set_variable(f"auth_token_{device_id}", None)
        self.variable_manager.set_variable(f"auth_expires_{device_id}", None)


class GlobalConfigManager:
    """Central configuration and variable management"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/framework.yaml")
        self.variable_manager = VariableManager()
        self.api_config_manager = APIConfigManager(self.variable_manager)
        self._raw_config: Dict[str, Any] = {}

        # Set up framework defaults
        self._setup_framework_defaults()

        # Load configuration
        self.load_configuration()

    def _setup_framework_defaults(self):
        """Setup framework default variables"""
        defaults = self.variable_manager.get_scope("framework_defaults")
        defaults.update(
            {
                "ENVIRONMENT": "default",
                "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": datetime.now().strftime("%H:%M:%S"),
                "random_id": f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "workspace_dir": str(Path.cwd()),
                "config_dir": str(Path.cwd() / "config"),
                "tests_dir": str(Path.cwd() / "tests"),
                "reports_dir": str(Path.cwd() / "reports"),
            }
        )

    def load_configuration(self):
        """Load main configuration file"""
        if not self.config_path.exists():
            self._create_default_config()

        with open(self.config_path, "r") as f:
            self._raw_config = yaml.safe_load(f) or {}

        # Load variables into appropriate scopes
        self.variable_manager.load_config_file(self.config_path)

        # Load environment variables
        self.variable_manager.load_environment_variables("EASYBDD_")

        # Load API configuration
        self.api_config_manager.load_api_config(self._raw_config)

    def _create_default_config(self):
        """Create default configuration file"""
        default_config = {
            "variables": {
                "base_url": "https://example.com",
                "api_url": "https://api.example.com",
                "test_user_email": "test@example.com",
                "default_timeout": 30,
            },
            "config": {
                "browser": {
                    "default": "chrome",
                    "headless": False,
                    "timeout": 30,
                },
                "api": {
                    "timeout": 30,
                    "verify_ssl": True,
                    "base_urls": {
                        "development": "https://dev-api.example.com",
                        "staging": "https://staging-api.example.com",
                        "production": "https://api.example.com",
                    },
                    "auth_configs": {
                        "default": {"type": "none"},
                    },
                },
            },
            "environments": {
                "development": {
                    "base_url": "https://dev.example.com",
                    "debug": True,
                },
                "staging": {
                    "base_url": "https://staging.example.com",
                    "debug": False,
                },
                "production": {
                    "base_url": "https://example.com",
                    "debug": False,
                },
            },
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(default_config, f, default_flow_style=False)

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get variable value"""
        return self.variable_manager.get_variable(key, default)

    def set_variable(self, key: str, value: Any, scope: str = "runtime_data") -> None:
        """Set variable value"""
        self.variable_manager.set_variable(key, value, scope)

    def substitute_variables(
        self, text: str, additional_vars: Optional[Dict] = None
    ) -> str:
        """Substitute variables in text"""
        return self.variable_manager.substitute_variables(text, additional_vars)

    def substitute_recursive(
        self, data: Any, additional_vars: Optional[Dict] = None
    ) -> Any:
        """Recursively substitute variables in data"""
        return self.variable_manager.substitute_recursive(data, additional_vars)

    def get_api_config(self) -> APIConfigManager:
        """Get API configuration manager"""
        return self.api_config_manager

    def get_raw_config(self) -> Dict[str, Any]:
        """Get raw configuration data"""
        return self._raw_config

    def load_device_config(self, device_file: Union[str, Path]):
        """Load device-specific configuration from file"""
        device_path = Path(device_file)

        # If just a filename, look in config/devices/
        if not device_path.is_absolute():
            device_path = Path("config/devices") / device_file
            if not device_path.suffix:
                device_path = device_path.with_suffix(".yaml")

        if not device_path.exists():
            print(f"Warning: Device config file not found: {device_path}")
            return

        with open(device_path, "r") as f:
            device_data = yaml.safe_load(f) or {}

        # Load device variables into a device-specific scope
        device_name = device_path.stem
        device_scope_name = f"device_{device_name}"

        # Create device scope if it doesn't exist
        if not self.variable_manager.get_scope(device_scope_name):
            device_scope = self.variable_manager.add_scope(device_scope_name, 6)
        else:
            device_scope = self.variable_manager.get_scope(device_scope_name)

        # Flatten device config for easy access
        flattened_vars = self._flatten_device_config(device_data, device_name)
        device_scope.update(flattened_vars)

        # Also load into API config if authentication is present
        if "authentication" in device_data:
            self._load_device_auth_config(device_name, device_data)

        return device_data

    def _flatten_device_config(
        self, device_data: Dict[str, Any], device_name: str
    ) -> Dict[str, Any]:
        """Flatten device configuration for easy variable access"""
        flattened = {}

        # Device info
        if "device_info" in device_data:
            for key, value in device_data["device_info"].items():
                flattened[f"device_{key}"] = value

        # Network config
        if "network" in device_data:
            for key, value in device_data["network"].items():
                flattened[f"device_{key}"] = value

        # API endpoints
        if "api_endpoints" in device_data:
            for key, value in device_data["api_endpoints"].items():
                flattened[f"endpoint_{key}"] = value

        # Test data
        if "test_data" in device_data:
            for key, value in device_data["test_data"].items():
                flattened[f"test_{key}"] = value

        # Test settings
        if "test_settings" in device_data:
            for key, value in device_data["test_settings"].items():
                flattened[f"setting_{key}"] = value

        # Environment-specific data
        current_env = self.variable_manager.get_variable("ENVIRONMENT", "default")
        env_data = device_data.get("environments", {}).get(current_env, {})
        for key, value in env_data.items():
            flattened[f"device_{key}"] = value  # Override base values

        # Set device name for reference
        flattened["current_device"] = device_name
        flattened["device_config_file"] = device_name

        return flattened

    def _load_device_auth_config(self, device_name: str, device_data: Dict[str, Any]):
        """Load device authentication configuration into API config manager"""
        auth_data = device_data.get("authentication", {})
        network_data = device_data.get("network", {})

        # Build auth config compatible with existing system
        auth_config = {
            "type": auth_data.get("type", "bearer_token"),
            "endpoint": f"{network_data.get('base_url', '')}{auth_data.get('auth_endpoint', '/auth')}",
            "username": auth_data.get("username"),
            "password": auth_data.get("password"),
            "username_field": auth_data.get("username_field", "username"),
            "password_field": auth_data.get("password_field", "password"),
            "token_field": auth_data.get("token_field", "access_token"),
            "token_expires_field": auth_data.get("token_expires_field", "expires_in"),
            "default_expiry": auth_data.get("default_expiry", 3600),
            "verify_ssl": auth_data.get("verify_ssl", True),
            "timeout": auth_data.get("timeout", 30),
            "headers": auth_data.get("headers", {}),
            "auth_method": auth_data.get("auth_method", "POST"),
        }

        # Add to API auth configs
        self.api_config_manager.auth_configs[device_name] = auth_config

    def export_variables(self, file_path: Union[str, Path], format: str = "json"):
        """Export current variables to file"""
        variables = self.variable_manager.get_all_variables()

        file_path = Path(file_path)
        if format.lower() == "yaml":
            with open(file_path, "w") as f:
                yaml.dump(variables, f, default_flow_style=False)
        else:
            with open(file_path, "w") as f:
                json.dump(variables, f, indent=2, default=str)

    def debug_variables(self) -> Dict[str, Any]:
        """Get debug information about all variables and scopes"""
        debug_info = {
            "all_variables": self.variable_manager.get_all_variables(),
            "scopes": {},
        }

        for scope in self.variable_manager.scopes:
            if scope.variables:
                debug_info["scopes"][scope.name] = {
                    "priority": scope.priority,
                    "variables": scope.variables,
                }

        return debug_info


# Global instance for easy access
_global_config_manager: Optional[GlobalConfigManager] = None


def get_global_config() -> GlobalConfigManager:
    """Get or create global configuration manager"""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = GlobalConfigManager()
    return _global_config_manager


def set_global_config(config_manager: GlobalConfigManager):
    """Set global configuration manager"""
    global _global_config_manager
    _global_config_manager = config_manager
