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
    "incorrect login",   # e.g. "% Incorrect Login/Password" (Araknis switches)
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

    def __init__(self, host: str, port: int, timeout: float = 15.0):
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

    # Single-byte IAC command codes (used for comparisons inside recv'd data)
    _WILL = b"\xfb"
    _WONT = b"\xfc"
    _DO   = b"\xfd"
    _DONT = b"\xfe"
    _SB   = b"\xfa"  # sub-negotiation begin
    _SE   = b"\xf0"  # sub-negotiation end

    def _strip_iac(self, data: bytes) -> bytes:
        """Remove IAC control sequences from raw recv'd data; send DONT/WONT responses.

        The class WILL/WONT/DO/DONT constants are 2-byte (include the leading 0xFF),
        so we compare against the single-byte cmd codes (_WILL etc.) here instead.
        Response sequences use the 2-byte constants (e.g. self.DONT = b'\\xff\\xfe').
        """
        result = b""
        response = b""
        i = 0
        while i < len(data):
            b = data[i:i+1]
            if b != self.IAC:
                result += b
                i += 1
                continue
            # IAC byte — need at least one more byte
            if i + 1 >= len(data):
                break  # incomplete at end of buffer; discard
            cmd = data[i + 1:i + 2]
            if cmd == self.IAC:
                # Escaped 0xFF literal
                result += b"\xff"
                i += 2
            elif cmd == self._SB:
                # Sub-negotiation: skip everything until IAC SE
                end = data.find(self.IAC + self._SE, i + 2)
                i = end + 2 if end != -1 else len(data)
            elif cmd in (self._WILL, self._WONT, self._DO, self._DONT):
                if i + 2 >= len(data):
                    break  # incomplete option byte
                option = data[i + 2:i + 3]
                if cmd == self._WILL:
                    response += self.DONT + option   # b"\xff\xfe" + option
                elif cmd == self._DO:
                    response += self.WONT + option   # b"\xff\xfc" + option
                elif cmd == self._WONT:
                    response += self.DONT + option   # acknowledge
                elif cmd == self._DONT:
                    response += self.WONT + option   # acknowledge
                i += 3
            else:
                i += 2  # other 2-byte commands (AYT, IP, DM, …)
        if response:
            try:
                self._sock.sendall(response)
            except OSError:
                pass
        return result

    def _negotiate(self):
        """Read and respond to initial Telnet IAC negotiation (loops until idle)."""
        print(f"         🤝 Telnet negotiation...")
        iac_count = 0
        try:
            deadline = time.time() + 3.0
            self._sock.settimeout(1.0)
            while time.time() < deadline:
                try:
                    data = self._sock.recv(256)
                except socket.timeout:
                    break
                if not data:
                    break
                had_iac = self.IAC in data
                clean = self._strip_iac(data)
                if had_iac:
                    iac_count += 1
                self._buf += clean
                if clean and not had_iac:
                    # Pure text arrived (no IAC) — device is already past negotiation
                    break
        except OSError as exc:
            print(f"         🤝 Negotiation socket error: {exc}")
        if iac_count:
            print(f"         🤝 Telnet negotiation complete ({iac_count} IAC burst(s))")
        else:
            print(f"         🤝 No IAC negotiation")

    def _login(
        self,
        username: str,
        password: str,
        username_prompt: str = "Username:",
        password_prompt: str = "Password:",
        shell_prompt: str = "",
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

        if shell_prompt:
            # Wait for the actual shell prompt so the socket buffer is fully drained
            # before we hand control back to _send.  This prevents stale prompt bytes
            # from being returned as the response to the first command.
            print(f"         🔑 Waiting for shell prompt {shell_prompt!r}...")
            try:
                chunk = self.read_until(shell_prompt, timeout=15.0, encoding=encoding)
                output += chunk
                if chunk.strip():
                    print(f"         🔑 Banner: {chunk.strip()!r}")
            except Exception as exc:
                print(f"         ⚠️  Shell prompt not seen: {exc}")
        else:
            print(f"         🔑 Draining welcome banner (up to 3s)...")
            try:
                chunk = self.read_available(timeout=3.0, encoding=encoding)
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

    _MORE_PROMPT = b"--More--"

    def _prompt_found(self, prompt_bytes: bytes) -> bool:
        """Return True only when the prompt appears as a real device prompt.

        A single-character prompt like '#' also appears inside the echo line
        (e.g. 'AN-220-SW-R-16-POE# show version') so we must distinguish the
        real prompt from mid-line occurrences.  The rule: the prompt is "real"
        when it is followed by optional whitespace and then a line-ending or
        end-of-buffer — NOT by non-whitespace text on the same line.

        Examples:
          'AN-220-SW-R-16-POE# show version\\r\\n'  → False  (echo line)
          'AN-220-SW-R-16-POE# \\r\\n'              → True   (real prompt)
          'AN-220-SW-R-16-POE# '  (end of buffer)  → True   (real prompt, partial)
        """
        import re as _re
        try:
            text = self._buf.decode("utf-8", errors="replace")
            prompt_str = prompt_bytes.decode("utf-8", errors="replace")
        except Exception:
            return prompt_bytes in self._buf  # fallback
        # Match prompt followed by optional spaces/tabs then line-end or end-of-string
        pattern = _re.escape(prompt_str) + r"[ \t]*(?:\r\n|\r|\n|$)"
        return bool(_re.search(pattern, text))

    def _handle_more_pagination(self, encoding: str) -> None:
        """Send a space to page through --More-- prompts and strip the marker."""
        import re as _re
        text = self._buf.decode(encoding, errors="replace")
        # Strip --More-- with surrounding whitespace/CR from the accumulated buffer
        cleaned = _re.sub(r"\s*--More--\s*", "\n", text)
        self._buf = cleaned.encode(encoding)
        self._sock.sendall(b" ")

    def read_until(
        self,
        prompt: str,
        timeout: float = 45.0,
        encoding: str = "utf-8",
        idle_timeout: float = 5.0,
        stream: bool = False,
    ) -> str:
        prompt_bytes = prompt.encode(encoding)
        if self._prompt_found(prompt_bytes):
            result = self._buf.decode(encoding, errors="replace")
            self._buf = b""
            return result
        deadline = time.time() + timeout
        last_recv: float = 0.0
        received_any = False
        conn_error: Optional[Exception] = None
        _stream_line_buf = ""  # accumulates partial lines for stream output
        while time.time() < deadline:
            remaining = deadline - time.time()
            self._sock.settimeout(min(remaining, 0.5))
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    conn_error = OSError("Connection closed by remote host")
                    print(f"         ⚠️  EOF — remote closed the connection")
                    break
                # Filter out any mid-session IAC option negotiations.
                # received_any is set even for IAC-only chunks so the
                # idle_timeout clock resets (connection is still alive).
                received_any = True
                last_recv = time.time()
                chunk = self._strip_iac(chunk)
                if not chunk:
                    continue  # was all IAC control bytes — nothing to buffer
                if stream:
                    text = chunk.decode(encoding, errors="replace")
                    # Normalize: \r\n → \n, then drop orphaned \r (avoids blank lines)
                    _stream_line_buf += text.replace("\r\n", "\n").replace("\r", "")
                    while "\n" in _stream_line_buf:
                        line, _stream_line_buf = _stream_line_buf.split("\n", 1)
                        stripped = line.strip()
                        if stripped and stripped != "--More--" and "�" not in stripped:
                            print(f"             {line}")
                    sys.stdout.flush()
                self._buf += chunk
                # Auto-page through --More-- prompts
                if self._MORE_PROMPT in self._buf:
                    self._handle_more_pagination(encoding)
                    continue
                if self._prompt_found(prompt_bytes):
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
            creds["shell_prompt"], creds["encoding"], creds["max_retries"],
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
        shell_prompt: str,
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
                    shell_prompt=shell_prompt,
                    timeout=timeout,
                    encoding=encoding,
                )
                # Store credentials on the conn so they survive TelnetService re-instantiation
                conn.creds = dict(
                    host=host, port=port, timeout=timeout,
                    username=username, password=password,
                    username_prompt=username_prompt, password_prompt=password_prompt,
                    shell_prompt=shell_prompt,
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
        shell_prompt = params.get("prompt", params.get("shell_prompt", ""))
        if username:
            self._login_with_retry(
                key, host, port, timeout,
                username, password,
                username_prompt, password_prompt,
                shell_prompt, encoding, max_retries,
            )
        else:
            self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))
        return True

    def _send(self, params: Dict[str, Any]) -> str:
        host = params.get("host", "")
        port = int(params.get("port", 23))
        command = params.get("command", "")
        commands = params.get("commands") or []
        # If 'command' was given a YAML list value, promote it to 'commands'
        if isinstance(command, list):
            commands = command
            command = ""
        prompt = params.get("prompt", "#")
        timeout = float(params.get("timeout", 15.0))
        encoding = params.get("encoding", "utf-8")
        username = params.get("username", "")
        password = params.get("password", "")
        username_prompt = params.get("username_prompt", "Username:")
        password_prompt = params.get("password_prompt", "Password:")
        max_retries = int(params.get("max_retries", 2))
        if not host:
            raise ValueError("telnet.send requires 'host'")

        # Normalise: a 'commands' list takes precedence; a single 'command' is
        # wrapped into a one-item list so the rest of the logic is uniform.
        if isinstance(commands, str):
            import ast as _ast
            _s = commands.strip()
            # YAML may deliver a Python list literal e.g. "['a', 'b', 'c']"
            if _s.startswith("["):
                try:
                    commands = [str(c) for c in _ast.literal_eval(_s)]
                except Exception:
                    commands = [c.strip() for c in _s.strip("[]").split(",") if c.strip()]
            else:
                commands = [c.strip() for c in _s.splitlines() if c.strip()]
        if not commands and command:
            commands = [command]
        if not commands:
            raise ValueError("telnet.send requires 'command' or 'commands'")

        key = _pool_key(host, port)
        is_new = not self._pool.has(key)
        if is_new:
            if username:
                conn = self._login_with_retry(
                    key, host, port, timeout,
                    username, password,
                    username_prompt, password_prompt,
                    prompt, encoding, max_retries,
                )
            else:
                print(f"         🔌 Opening unauthenticated connection to {host}:{port}")
                conn = self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))
                # Drain the initial device prompt so it is not mistaken for the
                # response to the first command.  telnetlib did this implicitly;
                # our raw-socket implementation must do it explicitly.
                print(f"         🔌 Draining initial prompt {prompt!r}...")
                try:
                    conn.read_until(prompt, timeout=5.0, encoding=encoding)
                except Exception as exc:
                    print(f"         ⚠️  Initial prompt drain timed out: {exc} — continuing anyway")
        else:
            print(f"         ♻️  Reusing existing connection to {host}:{port}")
            conn = self._pool.acquire(key, lambda: _TelnetConn(host, port, timeout))

        result = ""
        try:
            for cmd in commands:
                if not isinstance(cmd, str):
                    print(f"         ⚠️  Skipping non-string command item: {cmd!r} (likely a YAML formatting error)")
                    continue
                # Strip any trailing whitespace/newlines so we control the line ending.
                # Use \r\n — the telnet standard — so devices that require CR+LF execute correctly.
                data = cmd.rstrip("\r\n") + "\r\n"
                print(f"         📤 Sending: {cmd!r}")
                conn.send(data, encoding)
                result = conn.read_until(prompt, timeout, encoding, stream=True)

                # Normalize line endings: \r\n → \n, then drop orphaned \r.
                # Devices often send \r\n\r (CR LF CR) per line; without this the
                # extra \r decodes as a second newline and every field double-spaces.
                result = result.replace("\r\n", "\n").replace("\r", "")

                # Strip remote echo: the first line is the echoed command, sometimes
                # with telnet control bytes interleaved (decoded as � replacement
                # chars). Strip it if it contains the command text OR garbled chars.
                _cmd_clean = cmd.rstrip("\r\n").strip()
                _lines = result.lstrip("\n").split("\n")
                if _lines:
                    _first = _lines[0].strip()
                    # Remove replacement chars to get the printable chars for comparison
                    _first_printable = _first.replace("�", "").strip()
                    if (
                        _first_printable == _cmd_clean
                        or _first_printable.endswith(_cmd_clean)
                        or "�" in _first  # garbled echo line — always drop
                    ):
                        result = "\n".join(_lines[1:]).lstrip("\n")

                print(f"         📥 Done ({len(result)} chars)")
            return result
        except OSError as exc:
            print(f"         ⚠️  Connection lost: {exc}")
            self._pool.evict(key)
            new_conn = self._reconnect(key, conn)
            if new_conn is None:
                raise
            try:
                # Re-send only the last command on reconnect — earlier commands
                # in the sequence cannot be safely replayed automatically.
                last_cmd = commands[-1]
                data = last_cmd.rstrip("\r\n") + "\r\n"
                print(f"         📤 Resending: {last_cmd!r}")
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
