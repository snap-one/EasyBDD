"""
Soft Assertion Manager for Easy BDD Framework

Allows tests to continue execution even when assertions fail,
collecting all failures to report at the end of the test.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SoftAssertionFailure:
    """Represents a single soft assertion failure."""

    step_number: int
    action: str
    message: str
    expected: Optional[Any] = None
    actual: Optional[Any] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    details: Optional[Dict[str, Any]] = None

    def __str__(self) -> str:
        """Format failure as readable string."""
        parts = [f"Step {self.step_number} ({self.action}): {self.message}"]

        if self.expected is not None:
            parts.append(f"  Expected: {self.expected}")

        if self.actual is not None:
            parts.append(f"  Actual: {self.actual}")

        if self.details:
            for key, value in self.details.items():
                parts.append(f"  {key}: {value}")

        return "\n".join(parts)


class SoftAssertionManager:
    """Manages soft assertions during test execution."""

    def __init__(self):
        """Initialize the soft assertion manager."""
        self._failures: List[SoftAssertionFailure] = []
        self._enabled = True

    def add_failure(
        self,
        step_number: int,
        action: str,
        message: str,
        expected: Optional[Any] = None,
        actual: Optional[Any] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a soft assertion failure.

        Args:
            step_number: The step number where failure occurred
            action: The action that failed
            message: Description of the failure
            expected: Expected value (optional)
            actual: Actual value (optional)
            details: Additional context (optional)
        """
        failure = SoftAssertionFailure(
            step_number=step_number,
            action=action,
            message=message,
            expected=expected,
            actual=actual,
            details=details,
        )
        self._failures.append(failure)
        print(f"⚠️  Soft Assertion Failed: {message}")

    def has_failures(self) -> bool:
        """Check if any soft assertions have failed."""
        return len(self._failures) > 0

    def get_failures(self) -> List[SoftAssertionFailure]:
        """Get all recorded failures."""
        return self._failures.copy()

    def get_failure_count(self) -> int:
        """Get the count of failures."""
        return len(self._failures)

    def clear(self) -> None:
        """Clear all recorded failures."""
        self._failures.clear()

    def get_summary(self) -> str:
        """Get a summary of all failures."""
        if not self._failures:
            return "No soft assertion failures."

        lines = [f"\n{'='*60}"]
        lines.append(f"SOFT ASSERTION FAILURES: {len(self._failures)} total")
        lines.append("=" * 60)

        for idx, failure in enumerate(self._failures, 1):
            lines.append(f"\n{idx}. {failure}")

        lines.append("=" * 60)
        return "\n".join(lines)

    def raise_if_failures(self) -> None:
        """
        Raise an exception if there are any recorded failures.
        This should be called at the end of the test or when checking soft assertions.
        """
        if self._failures:
            summary = self.get_summary()
            raise AssertionError(
                f"{len(self._failures)} soft assertion(s) failed:\n{summary}"
            )

    def enable(self) -> None:
        """Enable soft assertion recording."""
        self._enabled = True

    def disable(self) -> None:
        """Disable soft assertion recording."""
        self._enabled = False

    def is_enabled(self) -> bool:
        """Check if soft assertion recording is enabled."""
        return self._enabled

    def to_dict(self) -> Dict[str, Any]:
        """Convert failures to dictionary format for reporting."""
        return {
            "count": len(self._failures),
            "failures": [
                {
                    "step_number": f.step_number,
                    "action": f.action,
                    "message": f.message,
                    "expected": str(f.expected) if f.expected is not None else None,
                    "actual": str(f.actual) if f.actual is not None else None,
                    "timestamp": f.timestamp,
                    "details": f.details or {},
                }
                for f in self._failures
            ],
        }
