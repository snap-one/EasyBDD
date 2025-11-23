"""
Configuration management for the Easy BDD Framework
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, asdict


@dataclass
class BrowserConfig:
    default: str = "chrome"
    headless: bool = False
    window_size: tuple = (1920, 1080)
    timeout: int = 30
    implicit_wait: int = 10


@dataclass
class APIConfig:
    timeout: int = 30
    verify_ssl: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0


@dataclass
class AndroidConfig:
    default_device: str = "emulator-5554"
    app_package: Optional[str] = None
    timeout: int = 30
    implicit_wait: int = 10


@dataclass
class AWSConfig:
    region: str = "us-east-1"
    profile: Optional[str] = None
    timeout: int = 30


@dataclass
class SerialConfig:
    default_port: str = "/dev/ttyUSB0"
    default_baudrate: int = 9600
    timeout: int = 5


@dataclass
class WebSocketConfig:
    timeout: int = 30
    ping_interval: int = 20
    ping_timeout: int = 10


@dataclass
class ReportingConfig:
    output_dir: str = "reports"
    screenshots: bool = True
    video: bool = False
    html_report: bool = True
    allure_report: bool = False


@dataclass
class ParallelConfig:
    workers: int = 2
    distribute_by: str = "file"  # file, scenario


@dataclass
class FrameworkConfig:
    browser: BrowserConfig
    api: APIConfig
    android: AndroidConfig
    aws: AWSConfig
    serial: SerialConfig
    websocket: WebSocketConfig
    reporting: ReportingConfig
    parallel: ParallelConfig


class ConfigManager:
    """Manages framework configuration"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/framework.yaml")
        self._config = self._create_default_config()
        self._environments: Dict[str, Dict[str, Any]] = {}
        self._raw_config: Dict[str, Any] = {}  # Store raw config data
        
        # Load configuration if file exists
        if self.config_path.exists():
            self.load()
    
    def _create_default_config(self) -> FrameworkConfig:
        """Create default configuration"""
        return FrameworkConfig(
            browser=BrowserConfig(),
            api=APIConfig(),
            android=AndroidConfig(),
            aws=AWSConfig(),
            serial=SerialConfig(),
            websocket=WebSocketConfig(),
            reporting=ReportingConfig(),
            parallel=ParallelConfig()
        )
    
    def load(self, config_path: Optional[Path] = None) -> None:
        """Load configuration from file"""
        path = config_path or self.config_path
        
        if not path.exists():
            return
        
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        
        # Store raw config data for custom settings
        self._raw_config = data.get('config', {})
        
        # Load main configuration
        config_data = data.get('config', {})
        self._update_config_from_dict(config_data)
        
        # Load environments
        self._environments = data.get('environments', {})
    
    def save(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to file"""
        path = config_path or self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'config': asdict(self._config),
            'environments': self._environments
        }
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def create_default_config(self, config_path: Path) -> None:
        """Create a default configuration file"""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        default_data = {
            'config': asdict(self._create_default_config()),
            'environments': {
                'default': {},
                'staging': {
                    'base_url': 'https://staging.example.com',
                    'api_url': 'https://api-staging.example.com'
                },
                'production': {
                    'base_url': 'https://example.com',
                    'api_url': 'https://api.example.com'
                }
            }
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(default_data, f, default_flow_style=False, sort_keys=False)
    
    @property
    def browser(self) -> BrowserConfig:
        """Access browser configuration"""
        return self._config.browser
    
    @property
    def api(self) -> APIConfig:
        """Access API configuration"""
        return self._config.api
    
    @property
    def reporting(self) -> ReportingConfig:
        """Access reporting configuration"""
        return self._config.reporting
    
    @property
    def parallel(self) -> ParallelConfig:
        """Access parallel configuration"""
        return self._config.parallel
    
    def load_environment(self, env_name: str) -> None:
        """Load environment-specific configuration"""
        if env_name in self._environments:
            env_config = self._environments[env_name]
            self._update_config_from_dict(env_config)
    
    def _update_config_from_dict(self, data: Dict[str, Any]) -> None:
        """Update configuration from dictionary"""
        if 'browser' in data:
            self._update_dataclass(self._config.browser, data['browser'])
        if 'api' in data:
            self._update_dataclass(self._config.api, data['api'])
        if 'android' in data:
            self._update_dataclass(self._config.android, data['android'])
        if 'aws' in data:
            self._update_dataclass(self._config.aws, data['aws'])
        if 'serial' in data:
            self._update_dataclass(self._config.serial, data['serial'])
        if 'websocket' in data:
            self._update_dataclass(self._config.websocket, data['websocket'])
        if 'reporting' in data:
            self._update_dataclass(self._config.reporting, data['reporting'])
        if 'parallel' in data:
            self._update_dataclass(self._config.parallel, data['parallel'])
    
    def _update_dataclass(self, obj: Any, data: Dict[str, Any]) -> None:
        """Update dataclass instance with dictionary data"""
        for key, value in data.items():
            if hasattr(obj, key):
                setattr(obj, key, value)
    
    def get(self, path: str, default: Any = None) -> Any:
        """Get configuration value by dot notation path"""
        parts = path.split('.')
        current = self._config
        
        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            else:
                return default
        
        return current
    
    def set(self, path: str, value: Any) -> None:
        """Set configuration value by dot notation path"""
        parts = path.split('.')
        current = self._config
        
        for part in parts[:-1]:
            if hasattr(current, part):
                current = getattr(current, part)
            else:
                return
        
        if hasattr(current, parts[-1]):
            setattr(current, parts[-1], value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self._config)
    
    def to_yaml(self) -> str:
        """Convert configuration to YAML string"""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)
    
    @property
    def config(self) -> FrameworkConfig:
        """Get the configuration object"""
        return self._config