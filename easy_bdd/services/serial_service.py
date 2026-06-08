"""
Serial port service for Easy BDD Framework.

Maintains persistent connections via ConnectionPool so a port opened in one
step stays open for subsequent steps in the same test run.

YAML actions:
  serial.send    — write data to port, optionally read response
  serial.receive — read data from port (up to timeout)
  serial.flush   — discard buffered input
  serial.close   — close and evict the port connection

Example:
  steps:
    - action: serial.send
      port: COM3
      baudrate: 115200
      data: "version\\r\\n"
      store_as: version_response
      timeout: 2.0

    - action: serial.receive
      port: COM3
      timeout: 5.0
      store_as: extra_output
"""

from typing import Any, Dict, Optional

from ..core.connection_pool import ConnectionPool


def _pool_key(port: str, baudrate: int) -> str:
    return f"serial://{port}:{baudrate}"


class SerialService:
    """Stateful serial port service backed by a shared ConnectionPool."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    # ------------------------------------------------------------------ #
    # Action dispatch                                                      #
    # ------------------------------------------------------------------ #

    def execute(self, action: str, params: Dict[str, Any], variables: Dict[str, Any]) -> Any:
        action_lower = action.lower()

        if "send" in action_lower:
            return self._send(params)
        if "receive" in action_lower or "read" in action_lower:
            return self._receive(params)
        if "flush" in action_lower:
            return self._flush(params)
        if "close" in action_lower:
            return self._close(params)

        raise ValueError(f"Unknown serial action: {action}")

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _send(self, params: Dict[str, Any]) -> str:
        """Write data to the serial port. Returns any immediate response."""
        try:
            import serial as pyserial
        except ImportError:
            raise RuntimeError(
                "pyserial is not installed. Run: pip install pyserial"
            )

        port = params.get("port", "")
        baudrate = int(params.get("baudrate", 115200))
        data = params.get("data", "")
        timeout = float(params.get("timeout", 1.0))
        encoding = params.get("encoding", "utf-8")
        read_response = params.get("read_response", True)

        if not port:
            raise ValueError("serial.send requires 'port'")

        key = _pool_key(port, baudrate)
        conn = self._pool.acquire(
            key,
            lambda: pyserial.Serial(port, baudrate, timeout=timeout),
        )

        try:
            raw = data.encode(encoding) if isinstance(data, str) else data
            conn.write(raw)
            conn.flush()

            if read_response:
                response_bytes = conn.read_all() or conn.read(conn.in_waiting or 1)
                return response_bytes.decode(encoding, errors="replace")
            return ""
        except Exception:
            self._pool.evict(key)
            raise

    def _receive(self, params: Dict[str, Any]) -> str:
        """Read available data from the serial port."""
        try:
            import serial as pyserial
        except ImportError:
            raise RuntimeError("pyserial is not installed. Run: pip install pyserial")

        port = params.get("port", "")
        baudrate = int(params.get("baudrate", 115200))
        timeout = float(params.get("timeout", 2.0))
        encoding = params.get("encoding", "utf-8")
        until = params.get("until", "")  # Read until this string appears

        if not port:
            raise ValueError("serial.receive requires 'port'")

        key = _pool_key(port, baudrate)
        conn = self._pool.acquire(
            key,
            lambda: pyserial.Serial(port, baudrate, timeout=timeout),
        )
        conn.timeout = timeout

        try:
            if until:
                buffer = b""
                until_bytes = until.encode(encoding)
                import time
                deadline = time.time() + timeout
                while time.time() < deadline:
                    chunk = conn.read(1)
                    if chunk:
                        buffer += chunk
                        if until_bytes in buffer:
                            break
                return buffer.decode(encoding, errors="replace")
            else:
                import time
                time.sleep(min(timeout, 0.5))
                waiting = conn.in_waiting
                raw = conn.read(waiting) if waiting else b""
                return raw.decode(encoding, errors="replace")
        except Exception:
            self._pool.evict(key)
            raise

    def _flush(self, params: Dict[str, Any]) -> bool:
        port = params.get("port", "")
        baudrate = int(params.get("baudrate", 115200))
        key = _pool_key(port, baudrate)
        conn = self._pool._pool.get(key)
        if conn:
            try:
                conn.reset_input_buffer()
            except Exception:
                pass
        return True

    def _close(self, params: Dict[str, Any]) -> bool:
        port = params.get("port", "")
        baudrate = int(params.get("baudrate", 115200))
        self._pool.evict(_pool_key(port, baudrate))
        return True
