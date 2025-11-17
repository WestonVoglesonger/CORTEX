"""Production implementations of dependency injection protocols.

This module provides real implementations that wrap actual external dependencies
(filesystem, subprocess, time, etc.). These are used in production code.

For testing, use mocks or test doubles instead of these implementations.
"""

import os
import platform
import shutil
import subprocess
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Iterator


class ConsoleLogger:
    """Production logger that prints to console (stdout/stderr)."""

    def info(self, message: str) -> None:
        """Print info message to stdout."""
        print(message)

    def warning(self, message: str) -> None:
        """Print warning message to stdout."""
        print(f"Warning: {message}")

    def error(self, message: str) -> None:
        """Print error message to stderr."""
        print(f"Error: {message}", file=sys.stderr)

    def debug(self, message: str) -> None:
        """Print debug message to stdout."""
        print(f"Debug: {message}")


class RealFileSystemService:
    """Production filesystem service using real pathlib and shutil operations."""

    def exists(self, path: Union[str, Path]) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    def is_file(self, path: Union[str, Path]) -> bool:
        """Check if path is a file."""
        return Path(path).is_file()

    def is_dir(self, path: Union[str, Path]) -> bool:
        """Check if path is a directory."""
        return Path(path).is_dir()

    def read_file(self, path: Union[str, Path]) -> str:
        """Read entire file as string."""
        with open(path, 'r') as f:
            return f.read()

    def write_file(self, path: Union[str, Path], content: str) -> None:
        """Write string content to file."""
        with open(path, 'w') as f:
            f.write(content)

    def mkdir(self, path: Union[str, Path], parents: bool = True, exist_ok: bool = True) -> None:
        """Create directory."""
        Path(path).mkdir(parents=parents, exist_ok=exist_ok)

    def rmtree(self, path: Union[str, Path]) -> None:
        """Recursively remove directory tree."""
        shutil.rmtree(path)

    def glob(self, path: Union[str, Path], pattern: str) -> List[Path]:
        """Find all files matching glob pattern."""
        return list(Path(path).glob(pattern))

    def iterdir(self, path: Union[str, Path]) -> Iterator[Path]:
        """Iterate over directory contents."""
        return Path(path).iterdir()

    def open(self, path: Union[str, Path], mode: str = 'r', buffering: int = -1) -> Any:
        """Open file and return file handle."""
        return open(path, mode, buffering=buffering)


class SubprocessHandle:
    """Wrapper around subprocess.Popen handle."""

    def __init__(self, popen_handle):
        """Initialize with actual subprocess.Popen object."""
        self._handle = popen_handle

    def poll(self) -> Optional[int]:
        """Check if process has terminated."""
        return self._handle.poll()

    def wait(self) -> int:
        """Wait for process to terminate."""
        return self._handle.wait()


class SubprocessExecutor:
    """Production process executor using real subprocess.Popen."""

    def popen(
        self,
        cmd: List[str],
        stdout: Optional[Any] = None,
        stderr: Optional[Any] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> SubprocessHandle:
        """Execute command and return process handle."""
        handle = subprocess.Popen(
            cmd,
            stdout=stdout,
            stderr=stderr,
            cwd=cwd,
            env=env
        )
        return SubprocessHandle(handle)


class SystemTimeProvider:
    """Production time provider using real time module."""

    def current_time(self) -> float:
        """Get current time in seconds since epoch."""
        return time.time()

    def sleep(self, seconds: float) -> None:
        """Sleep for specified seconds."""
        time.sleep(seconds)


class SystemEnvironmentProvider:
    """Production environment provider using real os and platform modules."""

    def get_environ(self) -> Dict[str, str]:
        """Get copy of environment variables."""
        return dict(os.environ)

    def get_system_type(self) -> str:
        """Get system type ('Darwin', 'Linux', etc.)."""
        return platform.system()


class SystemToolLocator:
    """Production tool locator using real shutil.which."""

    def find_tool(self, tool_name: str) -> Optional[str]:
        """Find tool in PATH."""
        return shutil.which(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """Check if tool exists in PATH."""
        return self.find_tool(tool_name) is not None


class YamlConfigLoader:
    """Production config loader using real YAML parser."""

    def __init__(self, filesystem: 'RealFileSystemService'):
        """Initialize with filesystem service for reading files."""
        self.fs = filesystem

    def load_yaml(self, path: str) -> Dict[str, Any]:
        """Load YAML file and return parsed dictionary."""
        content = self.fs.read_file(path)
        return yaml.safe_load(content)
