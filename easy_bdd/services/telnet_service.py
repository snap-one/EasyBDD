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
      username: admin
      password: secret
      username_prompt: "Username:"
      password_prompt: "Password:"
      timeout: 10.0

    - action: telnet.send
      host: 192.168.1.1
      command: "show version\\n"
      prompt: "#"
      timeout: 10.0
      store_as: version_output

    - action: telnet.close
      host: 192.168.1.1

Login shortcut (no explicit telnet.connect required):
  steps:
    - telnet.send:
        host: 192.168.1.1
        port: 23
        username: admin
        password: secret
        command: ?Firmware
        prompt: ">"
        store_as: fw_response
"""

import socket
import sys
import time
from typing import Any, Dict, Optional

from ..core.connection_pool import ConnectionPool

_LOGIN_FAILURE_MARKERS = (
    "invalid login",
    "login failed",
    "login incorrect",
    "authentication failed",
    "access denied",
    "bad password",
    "permission denied",
)


class LoginError(Exception):
    """Raised when the device explicitly rejects login credentials."""


def _pool_key(host: str, port: int) -> str:
    return f"telnet://{host}:{port}"


class _TelnetConn:
    """Minimal Telnet connection over raw socket (avoids deprecated telnetlib)."""

    WILL = b"\xff\xfb"
    WONT = b"\xff\xfc"
    DO = b"\xff\xfd"
    DONT = b"\xff\xfe"
    IAC = b"\xff"

    def __init__(self, host: str, port: int, timeout: float = 55.0):
        print(f"         🔌 Connecting to {host}:{port} (timeout={timeout}s)...")
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._buf = b""
        # Credentials stored here so they survive across TelnetService instances
        # (the runner creates a new TelnetService per step, but the conn lives in
        # the shared ConnectionPool and persists across steps).
        self.creds: Optional[Dict[str, Any]] = None
        print(f"         ✅ TCP connected to {host}:{port}")
        self._negotiate()

    def _negotiate(self):
        """Read and discard initial Telnet negotiation bytes."""
        print(f"         🤝 Telnet negotiation...")
        try:
            self._sock.settimeout(2.0)
            data = self._sock.recv(256)
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
                print(f"         🤝 Sent {len(response) // 3} negotiation response(s)")
            else:
                print(f"         🤝 No negotiation required")
        except (socket.timeout, OSError):
            print(f"         🤝 No negotiation data from device")

    def _login(
        self,
        username: str,
        password: str,
        username_prompt: str = "Username:",
        password_prompt: str = "Password:",
        timeout: float = 10.0,
        encoding: str = "utf-8",
    ) -> str:
        output = ""
        print(f"         🔑 Waiting for username prompt {username_prompt!r}...")
        chunk = self.read_until(username_prompt, timeout, encoding)
        output += chunk
        print(f"         🔑 Sending username: {username!r}")
        self.send(username + "\n", encoding)
        print(f"         🔑 Waiting for password prompt {password_prompt!r}...")
        chunk = self.read_until(password_prompt, timeout, encoding)
        output += chunk
        print(f"         🔑 Sending password")
        self.send(password + "\n", encoding)
        print(f"         🔑 Draining welcome banner (up to 2s)...")
        try:
            chunk = self.read_available(timeout=2.0, encoding=encoding)
            output += chunk
            if chunk.strip():
                print(f"         🔑 Banner: {chunk.strip()!r}")
        except Exception:
            pass
        if any(marker in output.lower() for marker in _LOGIN_FAILURE_MARKERS):
            print(f"         ❌ Login rejected — device response: {output!r}")
            raise LoginError(f"Login rejected by device: {output!r}")
        print(f"         ✅ Login successful")
        return output

    def send(self, data: str, encoding: str = "utf-8") -> None:
        raw = data.encode(encoding) if isinstance(data, str) else data
        self._sock.sendall(raw)

    def read_until(
        self,
        prompt: str,
        timeout: float = 45.0,
        encoding: str = "utf-8",
        idle_timeout: float = 1.0,
        stream: bool = False,
    ) -> str:
        prompt_bytes = prompt.encode(encoding)
        if prompt_bytes in self._buf:
            result = self._buf.decode(encoding, errors="replace")
            self._buf = b""
            return result
        deadline = time.time() + timeout
        last_recv: float = 0.0
        received_any = False
        conn_error: Optional[Exception] = None
        while time.time() < deadline:
            remaining = deadline - time.time()
            self._sock.settimeout(min(remaining, 0.5))
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    conn_error = OSError("Connection closed by remote host")
                    print(f"         ⚠️  EOF — remote closed the connection")
                    break
                received_any = True
                last_recv = time.time()
                if stream:
                    text = chunk.decode(encoding, errors="replace")
                    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
                        if line.strip():
                            print(f"             {line}")
                    sys.stdout.flush()
                self._buf += chunk
                if prompt_bytes in self._buf:
                    result = self._buf.decode(encoding, errors="replace")
                    self._buf = b""
                    return result
            except socket.timeout:
                if received_any and (time.time() - last_recv) >= idle_timeout:
                    break
                continue
            except OSError as exc:
                conn_error = exc
                print(f"         ⚠️  Socket error: {exc}")
                break
        if not received_any:
            self._buf = b""
            if conn_error:
                raise conn_error
            raise TimeoutError(
                f"Telnet: no response within {timeout}s (prompt {prompt!r} not received)"
            )
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
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _reconnect(self, key: str, dead_conn: Optional["_TelnetConn"]) -> Optional["_TelnetConn"]:
        """Re-establish a dead connection using credentials stored on the old conn."""
        creds = dead_conn.creds if dead_conn is not None else None
        if not creds:
            print(f"         ⚠️  No stored credentials for {key} — cannot auto-reconnect")
            return None
        print(f"         🔄 Reconnecting to {creds['host']}:{creds['port']} with stored credentials...")
        return self._login_with_retry(
            key,
            creds["host"], creds["port"], creds["timeout"],
            creds["username"], creds["password"],
            creds["username_prompt"], creds["password_prompt"],
            creds["encoding"], creds["max_retries"],
        )

    def _login_with_retry(
        self,
        key: str,
        host: str,
        port: int,
        timeout: float,
        username: str,
        password: str,
        username_prompt: str,
        password_prompt: str,
        encoding: str,
        max_retries: int,
    ) -> "_TelnetConn":
        """Acquire a connection and log in, reconnecting and retrying on failure."""
        last_exc: Exception = RuntimeError("Login failed")
        for attempt in range(max_retries + 1):
            if attempt > 0:
                print(f"         🔄 Login attempt {attempt + 1}/{max_retries + 1}...")
                self._pool.evict(key)
            conn: _TelnetConn = self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))
            try:
                conn._login(
                    username, password,
                    username_prompt=username_prompt,
                    password_prompt=password_prompt,
                    timeout=timeout,
                    encoding=encoding,
                )
                # Store credentials on the conn so they survive TelnetService re-instantiation
                conn.creds = dict(
                    host=host, port=port, timeout=timeout,
                    username=username, password=password,
                    username_prompt=username_prompt, password_prompt=password_prompt,
                    encoding=encoding, max_retries=max_retries,
                )
                return conn
            except Exception as exc:
                last_exc = exc
                print(f"         ❌ Login attempt {attempt + 1} failed: {exc}")
        self._pool.evict(key)
        raise last_exc

    # ------------------------------------------------------------------ #
    # Actions                                                              #
    # ------------------------------------------------------------------ #

    def _connect(self, params: Dict[str, Any]) -> bool:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        timeout = float(params.get("timeout", 15.0))
        username = params.get("username", "")
        password = params.get("password", "")
        username_prompt = params.get("username_prompt", "Username:")
        password_prompt = params.get("password_prompt", "Password:")
        encoding = params.get("encoding", "utf-8")
        max_retries = int(params.get("max_retries", 2))
        if not host:
            raise ValueError("telnet.connect requires 'host'")
        key = _pool_key(host, port)
        if self._pool.has(key):
            print(f"         ♻️  Reusing existing connection to {host}:{port}")
            return True
        if username:
            self._login_with_retry(
                key, host, port, timeout,
                username, password,
                username_prompt, password_prompt,
                encoding, max_retries,
            )
        else:
            self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))
        return True

    def _send(self, params: Dict[str, Any]) -> str:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        command = params.get("command", "")
        prompt = params.get("prompt", "#")
        timeout = float(params.get("timeout", 55.0))
        encoding = params.get("encoding", "utf-8")
        username = params.get("username", "")
        password = params.get("password", "")
        username_prompt = params.get("username_prompt", "Username:")
        password_prompt = params.get("password_prompt", "Password:")
        max_retries = int(params.get("max_retries", 2))
        if not host:
            raise ValueError("telnet.send requires 'host'")
        key = _pool_key(host, port)
        is_new = not self._pool.has(key)
        if is_new:
            if username:
                conn = self._login_with_retry(
                    key, host, port, timeout,
                    username, password,
                    username_prompt, password_prompt,
                    encoding, max_retries,
                )
            else:
                print(f"         🔌 Opening unauthenticated connection to {host}:{port}")
                conn = self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))
        else:
            print(f"         ♻️  Reusing existing connection to {host}:{port}")
            conn = self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))

        data = command if command.endswith("\n") else command + "\n"
        print(f"         📤 Sending: {command!r}")
        try:
            conn.send(data, encoding)
            result = conn.read_until(prompt, timeout, encoding, stream=True)
            print(f"         📥 Done ({len(result)} chars)")
            return result
        except OSError as exc:
            print(f"         ⚠️  Connection lost: {exc}")
            self._pool.evict(key)
            new_conn = self._reconnect(key, conn)
            if new_conn is None:
                raise
            try:
                print(f"         📤 Resending: {command!r}")
                new_conn.send(data, encoding)
                result = new_conn.read_until(prompt, timeout, encoding, stream=True)
                print(f"         📥 Done ({len(result)} chars)")
                return result
            except Exception:
                self._pool.evict(key)
                raise
        except Exception:
            self._pool.evict(key)
            raise

    def _receive(self, params: Dict[str, Any]) -> str:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        prompt = params.get("prompt", "")
        timeout = float(params.get("timeout", 45.0))
        encoding = params.get("encoding", "utf-8")
        if not host:
            raise ValueError("telnet.receive requires 'host'")
        key = _pool_key(host, port)
        print(f"         📥 Receiving from {host}:{port}" + (f" until {prompt!r}" if prompt else " (available data)"))
        conn: _TelnetConn = self._pool.acquire(
            key, lambda: _TelnetConn(host, port, timeout)
        )
        try:
            if prompt:
                result = conn.read_until(prompt, timeout, encoding)
            else:
                result = conn.read_available(timeout, encoding)
            preview = result.strip()[:120].replace("\n", "\\n").replace("\r", "")
            print(f"         📥 Received {len(result)} chars: {preview!r}")
            return result
        except Exception:
            self._pool.evict(key)
            raise

    def _close(self, params: Dict[str, Any]) -> bool:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        key = _pool_key(host, port)
        print(f"         🔌 Closing connection to {host}:{port}")
        self._pool.evict(key)
        return True
