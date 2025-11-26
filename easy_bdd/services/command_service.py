"""
Command Execution Service
Handles execution of SSH, shell, bash, batch, PowerShell, and Python commands
"""

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import paramiko


class CommandService:
    """Service for executing local and remote commands"""

    def __init__(self, config=None):
        self.config = config
        self.os_type = platform.system().lower()
        self._shell_cache = {}  # Cache for found shell executables

    def execute_ssh_command(
        self,
        host: str,
        command: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        key_file: Optional[str] = None,
        port: int = 22,
        timeout: int = 30,
    ) -> Tuple[str, int]:
        """
        Execute a command on a remote server via SSH

        Returns:
            Tuple of (output, exit_code)
        """
        try:
            # Ensure port and timeout are integers
            port = int(port) if port else 22
            timeout = int(timeout) if timeout else 30

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Connect to SSH server
            if key_file and os.path.exists(key_file):
                ssh.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    key_filename=key_file,
                    timeout=timeout,
                )
            elif password:
                ssh.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=timeout,
                )
            else:
                # Try key-based auth from default location
                ssh.connect(
                    hostname=host,
                    port=port,
                    username=username or os.getenv("USER", "root"),
                    timeout=timeout,
                )

            # Execute command
            stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="ignore")
            error_output = stderr.read().decode("utf-8", errors="ignore")

            ssh.close()

            # Combine stdout and stderr
            full_output = output
            if error_output:
                full_output += f"\n{error_output}"

            return full_output.strip(), exit_code

        except Exception as e:
            error_msg = f"SSH command execution failed: {str(e)}"
            print(f"      ❌ {error_msg}")
            return error_msg, 1

    def execute_shell_command(
        self,
        command: str,
        shell: str = "auto",
        working_directory: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, int]:
        """
        Execute a shell command locally

        Returns:
            Tuple of (output, exit_code)
        """
        try:
            # Ensure timeout is an integer
            timeout = int(timeout) if timeout else 30

            # Ensure command is a string
            if not isinstance(command, str) or not command.strip():
                raise ValueError("Command must be a non-empty string")

            # Determine shell based on OS if auto
            if shell == "auto":
                shell = self._detect_default_shell()

            # Build command based on shell type
            if shell == "cmd" or shell == "batch":
                # Windows CMD / Batch
                cmd = ["cmd", "/c", command]
                use_shell = False
            elif shell == "powershell" or shell == "pwsh":
                # Windows PowerShell or PowerShell Core
                # Try PowerShell Core first (cross-platform), then Windows PowerShell
                shell_path = self._find_shell_executable("pwsh")
                if not shell_path:
                    shell_path = self._find_shell_executable("powershell")
                
                if shell_path:
                    # PowerShell Core uses -Command, Windows PowerShell uses -Command
                    cmd = [shell_path, "-NoProfile", "-NonInteractive", "-Command", command]
                else:
                    # Fallback to powershell (should be in PATH on Windows)
                    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
                use_shell = False
            elif shell in ["bash", "sh", "zsh", "fish", "tcsh", "csh", "dash", "ksh"]:
                # Unix shells - find the shell executable
                shell_path = self._find_shell_executable(shell)
                
                if shell_path:
                    cmd = [shell_path, "-c", command]
                else:
                    # Fallback: use shell directly (should be in PATH)
                    cmd = [shell, "-c", command]
                use_shell = False  # We're providing the shell explicitly
            else:
                # Default to system shell with shell=True
                cmd = command
                use_shell = True

            # Execute command
            result = subprocess.run(
                cmd,
                cwd=working_directory,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=use_shell,
            )

            output = result.stdout
            if result.stderr:
                output += f"\n{result.stderr}"

            return output.strip(), result.returncode

        except subprocess.TimeoutExpired:
            error_msg = f"Command execution timed out after {timeout} seconds"
            print(f"      ❌ {error_msg}")
            return error_msg, 124  # Timeout exit code
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            print(f"      ❌ {error_msg}")
            return error_msg, 1

    def execute_bash_command(
        self,
        command: str,
        working_directory: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, int]:
        """Execute a bash command"""
        timeout = int(timeout) if timeout else 30
        return self.execute_shell_command(
            command, shell="bash", working_directory=working_directory, timeout=timeout
        )

    def execute_powershell_command(
        self,
        command: str,
        working_directory: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, int]:
        """Execute a PowerShell command"""
        timeout = int(timeout) if timeout else 30
        return self.execute_shell_command(
            command,
            shell="powershell",
            working_directory=working_directory,
            timeout=timeout,
        )

    def execute_batch_command(
        self,
        command: str,
        working_directory: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, int]:
        """Execute a Windows batch command"""
        timeout = int(timeout) if timeout else 30
        return self.execute_shell_command(
            command, shell="cmd", working_directory=working_directory, timeout=timeout
        )
    
    def _detect_default_shell(self) -> str:
        """Detect the default shell for the current platform"""
        if self.os_type == "windows":
            # On Windows, prefer PowerShell if available, otherwise CMD
            if self._find_shell_executable("pwsh") or self._find_shell_executable("powershell"):
                return "powershell"
            return "cmd"
        else:
            # On Unix-like systems, check SHELL environment variable
            default_shell = os.environ.get("SHELL", "")
            if default_shell:
                # Extract shell name from path (e.g., /bin/bash -> bash)
                shell_name = os.path.basename(default_shell)
                # Remove leading dot if present (e.g., .zsh -> zsh)
                if shell_name.startswith("."):
                    shell_name = shell_name[1:]
                # Check if it's a supported shell
                if shell_name in ["bash", "sh", "zsh", "fish", "tcsh", "csh", "dash", "ksh"]:
                    return shell_name
            # Fallback to bash (most common on Linux/Mac)
            return "bash"
    
    def _find_shell_executable(self, shell_name: str) -> Optional[str]:
        """Find the path to a shell executable, with caching"""
        # Check cache first
        if shell_name in self._shell_cache:
            return self._shell_cache[shell_name]
        
        shell_path = None
        
        # Try common paths first (platform-specific)
        if self.os_type == "windows":
            if shell_name in ["powershell", "pwsh"]:
                # PowerShell paths
                possible_paths = [
                    "C:\\Program Files\\PowerShell\\7\\pwsh.exe",  # PowerShell Core
                    "C:\\Program Files (x86)\\PowerShell\\7\\pwsh.exe",
                    "C:\\Program Files\\PowerShell\\6\\pwsh.exe",
                    "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",  # Windows PowerShell
                ]
                for path in possible_paths:
                    if os.path.exists(path):
                        shell_path = path
                        break
            elif shell_name in ["cmd", "batch"]:
                # CMD is always available on Windows
                shell_path = "C:\\Windows\\System32\\cmd.exe"
        else:
            # Unix-like systems
            possible_paths = [
                f"/bin/{shell_name}",
                f"/usr/bin/{shell_name}",
                f"/usr/local/bin/{shell_name}",
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    shell_path = path
                    break
        
        # If not found in common paths, try PATH
        if not shell_path:
            shell_path = shutil.which(shell_name)
        
        # Cache the result (even if None, to avoid repeated lookups)
        self._shell_cache[shell_name] = shell_path
        return shell_path

    def execute_python_code(
        self,
        code: str,
        working_directory: Optional[str] = None,
        timeout: int = 30,
    ) -> Tuple[str, Optional[Any], int]:
        """
        Execute Python code

        Returns:
            Tuple of (output, result, exit_code)
        """
        try:
            # Ensure timeout is an integer
            timeout = int(timeout) if timeout else 30

            # Create a temporary Python script
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                # Wrap code to capture output and return value
                # Escape code for safe inclusion in f-string
                escaped_code = code.replace("'''", '"""').replace('"""', '\\"\\"\\"')
                wrapped_code = f"""
import sys
import io
from contextlib import redirect_stdout, redirect_stderr

# Capture stdout and stderr
stdout_capture = io.StringIO()
stderr_capture = io.StringIO()

try:
    with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
        # User code
        exec('''{escaped_code}''')
        result = None
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    result = None
    raise

# Get captured output
output = stdout_capture.getvalue() + stderr_capture.getvalue()
print(output, end='')
if result is not None:
    import json
    try:
        print(f"\\n__PYTHON_RESULT__:{{json.dumps(result)}}")
    except:
        print(f"\\n__PYTHON_RESULT__:{{str(result)}}")
"""
                f.write(wrapped_code)
                temp_file = f.name

            try:
                # Execute the Python script
                python_executable = sys.executable
                result = subprocess.run(
                    [python_executable, temp_file],
                    cwd=working_directory,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                output = result.stdout
                if result.stderr:
                    output += f"\n{result.stderr}"

                # Extract result if present
                python_result = None
                if "__PYTHON_RESULT__:" in output:
                    lines = output.split("\n")
                    output_lines = []
                    for line in lines:
                        if line.startswith("__PYTHON_RESULT__:"):
                            result_str = line.replace("__PYTHON_RESULT__:", "")
                            try:
                                import json

                                python_result = json.loads(result_str)
                            except:
                                python_result = result_str
                        else:
                            output_lines.append(line)
                    output = "\n".join(output_lines)

                exit_code = result.returncode
                return output.strip(), python_result, exit_code

            finally:
                # Clean up temp file
                try:
                    os.unlink(temp_file)
                except:
                    pass

        except subprocess.TimeoutExpired:
            error_msg = f"Python code execution timed out after {timeout} seconds"
            print(f"      ❌ {error_msg}")
            return error_msg, None, 124
        except Exception as e:
            error_msg = f"Python code execution failed: {str(e)}"
            print(f"      ❌ {error_msg}")
            return error_msg, None, 1
