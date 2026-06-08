"""
Generic connection pool for stateful protocol services (Serial, Telnet, etc.).

Connections are keyed by a string (e.g. "COM3:115200", "192.168.1.1:23") and
created lazily on first acquire via a factory callable. On error, call evict()
to close and remove the bad connection so the next acquire rebuilds it.
"""

from typing import Any, Callable, Dict


class ConnectionPool:
    """Thread-unsafe connection pool keyed by string identifier.

    Designed for single-threaded test execution. If parallel test workers are
    needed, wrap acquire/evict with a threading.Lock.
    """

    def __init__(self):
        self._pool: Dict[str, Any] = {}

    def acquire(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return cached connection for key, or call factory() to create one."""
        if key not in self._pool:
            self._pool[key] = factory()
        return self._pool[key]

    def evict(self, key: str) -> None:
        """Close and remove a connection from the pool."""
        conn = self._pool.pop(key, None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def close_all(self) -> None:
        """Close every pooled connection and clear the pool."""
        for key in list(self._pool.keys()):
            self.evict(key)
