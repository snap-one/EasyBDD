"""
Telnet service for Easy BDD Framework.

Maintains persistent connections via ConnectionPool so a session opened in one
step stays alive for subsequent steps.

YAML actions:
  telnet.connect  — open a Telnet connection (also auto-opened on first send)
  telnet.send     — send a command and wait for a prompt string
  telnet.receive  — read output up to a prompt or timeout
  telnet.close    — close and evict the connection

Example:
  steps:
    - action: telnet.connect
      host: 192.168.1.1
      port: 23
      timeout: 10.0

    - action: telnet.send
      host: 192.168.1.1
      command: "show version\\n"
      prompt: "#"
      timeout: 10.0
      store_as: version_output

    - action: telnet.close
      host: 192.168.1.1
"""

import socket
import time
from typing import Any, Dict, Optional

from ..core.connection_pool import ConnectionPool


def _pool_key(host: str, port: int) -> str:
    return f"telnet://{host}:{port}"


class _TelnetConn:
    """Minimal Telnet connection over raw socket (avoids deprecated telnetlib)."""

    WILL = b"\xff\xfb"
    WONT = b"\xff\xfc"
    DO = b"\xff\xfd"
    DONT = b"\xff\xfe"
    IAC = b"\xff"

    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._buf = b""
        # Absorb initial negotiation bytes
        self._negotiate()

    def _negotiate(self):
        """Read and discard initial Telnet negotiation bytes."""
        try:
            self._sock.settimeout(2.0)
            data = self._sock.recv(256)
            # Send WONT/DONT responses to any WILL/DO negotiations
            response = b""
            i = 0
            while i < len(data):
                if data[i:i+1] == self.IAC and i + 2 < len(data):
                    cmd = data[i+1:i+2]
                    if cmd == self.WILL:
                        response += self.IAC + self.DONT + data[i+2:i+3]
                    elif cmd == self.DO:
                        response += self.IAC + self.WONT + data[i+2:i+3]
                    i += 3
                else:
                    self._buf += data[i:i+1]
                    i += 1
            if response:
                self._sock.sendall(response)
        except (socket.timeout, OSError):
            pass

    def send(self, data: str, encoding: str = "utf-8") -> None:
        raw = data.encode(encoding) if isinstance(data, str) else data
        self._sock.sendall(raw)

    def read_until(self, prompt: str, timeout: float = 10.0, encoding: str = "utf-8") -> str:
        prompt_bytes = prompt.encode(encoding)
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = deadline - time.time()
            self._sock.settimeout(min(remaining, 0.5))
            try:
                chunk = self._sock.recv(4096)
                if chunk:
                    self._buf += chunk
                    if prompt_bytes in self._buf:
                        result = self._buf.decode(encoding, errors="replace")
                        self._buf = b""
                        return result
            except socket.timeout:
                continue
            except OSError:
                break
        result = self._buf.decode(encoding, errors="replace")
        self._buf = b""
        return result

    def read_available(self, timeout: float = 1.0, encoding: str = "utf-8") -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._sock.settimeout(min(deadline - time.time(), 0.2))
            try:
                chunk = self._sock.recv(4096)
                if chunk:
                    self._buf += chunk
                else:
                    break
            except socket.timeout:
                break
            except OSError:
                break
        result = self._buf.decode(encoding, errors="replace")
        self._buf = b""
        return result

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


class TelnetService:
    """Stateful Telnet service backed by a shared ConnectionPool."""

    def __init__(self, pool: ConnectionPool):
        self._pool = pool

    # ------------------------------------------------------------------ #
    # Action dispatch                                                      #
    # ------------------------------------------------------------------ #

    def execute(self, action: str, params: Dict[str, Any], variables: Dict[str, Any]) -> Any:
        action_lower = action.lower()

        if "connect" in action_lower:
            return self._connect(params)
        if "send" in action_lower:
            return self._send(params)
        if "receive" in action_lower or "read" in action_lower:
            return self._receive(params)
        if "close" in action_lower:
            return self._close(params)

        raise ValueError(f"Unknown telnet action: {action}")

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect(self, params: Dict[str, Any]) -> bool:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        timeout = float(params.get("timeout", 10.0))
        if not host:
            raise ValueError("telnet.connect requires 'host'")
        key = _pool_key(host, port)
        self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))
        return True

    def _send(self, params: Dict[str, Any]) -> str:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        command = params.get("command", "")
        prompt = params.get("prompt", "#")
        timeout = float(params.get("timeout", 10.0))
        encoding = params.get("encoding", "utf-8")
        if not host:
            raise ValueError("telnet.send requires 'host'")
        key = _pool_key(host, port)
        conn: _TelnetConn = self._pool.acquire(
            key, lambda: _TelnetConn(host, port, timeout)
        )
        try:
            data = command if command.endswith("\n") else command + "\n"
            conn.send(data, encoding)
            return conn.read_until(prompt, timeout, encoding)
        except Exception:
            self._pool.evict(key)
            raise

    def _receive(self, params: Dict[str, Any]) -> str:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        prompt = params.get("prompt", "")
        timeout = float(params.get("timeout", 5.0))
        encoding = params.get("encoding", "utf-8")
        if not host:
            raise ValueError("telnet.receive requires 'host'")
        key = _pool_key(host, port)
        conn: _TelnetConn = self._pool.acquire(
            key, lambda: _TelnetConn(host, port, timeout)
        )
        try:
            if prompt:
                return conn.read_until(prompt, timeout, encoding)
            return conn.read_available(timeout, encoding)
        except Exception:
            self._pool.evict(key)
            raise

    def _close(self, params: Dict[str, Any]) -> bool:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        self._pool.evict(_pool_key(host, port))
        return True
