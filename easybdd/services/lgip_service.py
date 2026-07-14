"""
LGIP (LG IP IR Control) service for Easy BDD Framework.

Sends IR keycodes to AV devices that support the LG IP control protocol over TCP.
Maintains persistent connections via ConnectionPool.

YAML actions:
  lgip.connect      — open a connection to the device (optional; auto-opened on send)
  lgip.send_keycode — send an IR keycode to the device
  lgip.disconnect   — close the connection

Example:
  steps:
    - action: lgip.connect
      ip: 192.168.1.50
      port: 9761

    - action: lgip.send_keycode
      ip: 192.168.1.50
      keycode: "20"       # power on
      store_as: ir_result

    - action: lgip.send_keycode
      ip: 192.168.1.50
      keycode: "02"       # volume up

    - action: lgip.disconnect
      ip: 192.168.1.50

Shorthand (no explicit connect needed):
  steps:
    - lgip.send_keycode:
        ip: 192.168.1.50
        keycode: "20"
        store_as: result

Common LG keycodes:
  "20" = Power On      "21" = Power Off     "02" = Volume Up
  "03" = Volume Down   "09" = Mute          "27" = Input HDMI1
  "28" = Input HDMI2   "29" = Input HDMI3   "60" = Input HDMI4
"""

import socket
import time
from typing import Any, Dict, Optional

from ..core.connection_pool import ConnectionPool

_DEFAULT_PORT = 9761
_DEFAULT_TIMEOUT = 5.0


def _pool_key(ip: str, port: int) -> str:
    return f"lgip://{ip}:{port}"


class _LGIPConn:
    """Raw TCP connection for LGIP protocol."""

    def __init__(self, ip: str, port: int, timeout: float = _DEFAULT_TIMEOUT):
        print(f"         🔌 LGIP connecting to {ip}:{port}...")
        self._sock = socket.create_connection((ip, port), timeout=timeout)
        self._sock.settimeout(timeout)
        print(f"         ✅ LGIP connected to {ip}:{port}")

    def send_keycode(self, keycode: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
        """Send an IR keycode packet and return the device's response."""
        # LGIP packet format: "k" + keycode (2-char hex) + " 01 " + value + "\r"
        # For a simple keypress the value field is the keycode itself.
        packet = f"k{keycode} 01 {keycode}\r"
        print(f"         📤 LGIP sending: {packet!r}")
        self._sock.sendall(packet.encode("ascii"))

        # Read response (device echoes the command back with a status byte)
        self._sock.settimeout(timeout)
        try:
            response = self._sock.recv(256).decode("ascii", errors="replace").strip()
            print(f"         📥 LGIP response: {response!r}")
            return response
        except socket.timeout:
            print(f"         ⚠️  LGIP: no response within {timeout}s")
            return ""

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


class LGIPService:
    """Stateful LGIP IR control service backed by a shared ConnectionPool."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    # ------------------------------------------------------------------ #
    # Action dispatch                                                      #
    # ------------------------------------------------------------------ #

    def execute(self, action: str, params: Dict[str, Any], variables: Dict[str, Any]) -> Any:
        action_lower = action.lower()

        if "connect" in action_lower:
            return self._connect(params)
        if "send" in action_lower or "keycode" in action_lower:
            return self._send_keycode(params)
        if "disconnect" in action_lower or "close" in action_lower:
            return self._disconnect(params)

        raise ValueError(f"Unknown lgip action: {action!r}. Use: lgip.connect, lgip.send_keycode, lgip.disconnect")

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect(self, params: Dict[str, Any]) -> bool:
        ip = params.get("ip", "")
        port = int(params.get("port", _DEFAULT_PORT))
        timeout = float(params.get("timeout", _DEFAULT_TIMEOUT))
        if not ip:
            raise ValueError("lgip.connect requires 'ip'")
        key = _pool_key(ip, port)
        if self._pool.has(key):
            print(f"         ♻️  Reusing existing LGIP connection to {ip}:{port}")
            return True
        self._pool.acquire(key, lambda: _LGIPConn(ip, port, timeout))
        return True

    def _send_keycode(self, params: Dict[str, Any]) -> str:
        ip = params.get("ip", "")
        port = int(params.get("port", _DEFAULT_PORT))
        timeout = float(params.get("timeout", _DEFAULT_TIMEOUT))
        keycode = str(params.get("keycode", ""))
        delay_after = float(params.get("delay_after", 0.0))

        if not ip:
            raise ValueError("lgip.send_keycode requires 'ip'")
        if not keycode:
            raise ValueError("lgip.send_keycode requires 'keycode'")

        key = _pool_key(ip, port)
        conn: _LGIPConn = self._pool.acquire(key, lambda: _LGIPConn(ip, port, timeout))

        try:
            result = conn.send_keycode(keycode, timeout)
            if delay_after:
                time.sleep(delay_after)
            return result
        except Exception:
            self._pool.evict(key)
            raise

    def _disconnect(self, params: Dict[str, Any]) -> bool:
        ip = params.get("ip", "")
        port = int(params.get("port", _DEFAULT_PORT))
        if not ip:
            raise ValueError("lgip.disconnect requires 'ip'")
        key = _pool_key(ip, port)
        print(f"         🔌 LGIP disconnecting from {ip}:{port}")
        self._pool.evict(key)
        return True
