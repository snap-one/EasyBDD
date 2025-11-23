"""
Retry logic for test actions with configurable attempts and delays
"""

import time
from typing import Callable, Any, Optional, Type, Tuple, Dict
from functools import wraps
from loguru import logger


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        delay: float = 1.0,
        backoff_multiplier: float = 2.0,
        max_delay: float = 30.0,
        retry_on_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    ):
        """
        Initialize retry configuration

        Args:
            max_attempts: Maximum number of retry attempts
            delay: Initial delay between retries in seconds
            backoff_multiplier: Multiplier for exponential backoff
            max_delay: Maximum delay between retries
            retry_on_exceptions: Tuple of exception types to retry on (None = all)
        """
        self.max_attempts = max_attempts
        self.delay = delay
        self.backoff_multiplier = backoff_multiplier
        self.max_delay = max_delay
        self.retry_on_exceptions = retry_on_exceptions or (Exception,)


def with_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 30.0,
    retry_on_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
) -> Callable:
    """
    Decorator to add retry logic to a function

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_multiplier: Multiplier for exponential backoff
        max_delay: Maximum delay between retries
        retry_on_exceptions: Tuple of exception types to retry on

    Example:
        @with_retry(max_attempts=3, delay=1.0)
        def flaky_action():
            # Code that might fail
            pass
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            config = RetryConfig(
                max_attempts=max_attempts,
                delay=delay,
                backoff_multiplier=backoff_multiplier,
                max_delay=max_delay,
                retry_on_exceptions=retry_on_exceptions,
            )

            last_exception = None
            current_delay = config.delay

            for attempt in range(1, config.max_attempts + 1):
                try:
                    logger.debug(
                        f"Attempting {func.__name__} (attempt {attempt}/{config.max_attempts})"
                    )
                    result = func(*args, **kwargs)
                    if attempt > 1:
                        logger.info(
                            f"✅ {func.__name__} succeeded on attempt {attempt}"
                        )
                    return result

                except config.retry_on_exceptions as e:
                    last_exception = e
                    logger.warning(
                        f"⚠️  {func.__name__} failed on attempt {attempt}/{config.max_attempts}: {str(e)}"
                    )

                    # If this is not the last attempt, wait before retrying
                    if attempt < config.max_attempts:
                        wait_time = min(current_delay, config.max_delay)
                        logger.info(f"Retrying in {wait_time:.1f} seconds...")
                        time.sleep(wait_time)
                        current_delay *= config.backoff_multiplier

            # All attempts failed
            logger.error(
                f"❌ {func.__name__} failed after {config.max_attempts} attempts"
            )
            raise last_exception

        return wrapper

    return decorator


def retry_action(
    action_func: Callable, config: RetryConfig, *args, **kwargs
) -> Any:
    """
    Execute an action with retry logic

    Args:
        action_func: The action function to execute
        config: Retry configuration
        *args: Positional arguments for the action
        **kwargs: Keyword arguments for the action

    Returns:
        Result of the action function

    Raises:
        Exception: If all retry attempts fail
    """
    last_exception = None
    current_delay = config.delay

    for attempt in range(1, config.max_attempts + 1):
        try:
            logger.debug(
                f"Attempting {action_func.__name__} (attempt {attempt}/{config.max_attempts})"
            )
            result = action_func(*args, **kwargs)
            if attempt > 1:
                logger.info(
                    f"✅ {action_func.__name__} succeeded on attempt {attempt}"
                )
            return result

        except config.retry_on_exceptions as e:
            last_exception = e
            logger.warning(
                f"⚠️  {action_func.__name__} failed on attempt {attempt}/{config.max_attempts}: {str(e)}"
            )

            # If this is not the last attempt, wait before retrying
            if attempt < config.max_attempts:
                wait_time = min(current_delay, config.max_delay)
                logger.info(f"Retrying in {wait_time:.1f} seconds...")
                time.sleep(wait_time)
                current_delay *= config.backoff_multiplier

    # All attempts failed
    logger.error(
        f"❌ {action_func.__name__} failed after {config.max_attempts} attempts"
    )
    raise last_exception


class RetryManager:
    """Manages retry behavior for test actions"""

    def __init__(self):
        self.default_config = RetryConfig()
        self.action_configs: Dict[str, RetryConfig] = {}

    def set_default_config(self, config: RetryConfig):
        """Set the default retry configuration"""
        self.default_config = config

    def set_action_config(self, action_name: str, config: RetryConfig):
        """Set retry configuration for a specific action"""
        self.action_configs[action_name] = config

    def get_config(self, action_name: str) -> RetryConfig:
        """Get retry configuration for an action"""
        return self.action_configs.get(action_name, self.default_config)

    def execute_with_retry(
        self, action_name: str, action_func: Callable, *args, **kwargs
    ) -> Any:
        """
        Execute an action with retry logic

        Args:
            action_name: Name of the action
            action_func: The action function to execute
            *args: Positional arguments for the action
            **kwargs: Keyword arguments for the action

        Returns:
            Result of the action function
        """
        config = self.get_config(action_name)
        return retry_action(action_func, config, *args, **kwargs)
