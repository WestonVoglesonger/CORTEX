"""Protocol definitions for dependency injection.

This module defines Protocol-based abstractions for all external dependencies.
Protocols use structural typing (duck typing with type hints) which means any
class implementing these methods satisfies the Protocol without explicit inheritance.

Benefits:
- Easy to mock in tests (just implement the methods)
- No inheritance required (more Pythonic)
- Type-safe with mypy/pyright
- Clear interface contracts
"""

from typing import Protocol, Dict, Any, Optional, List, Union, Iterator
from pathlib import Path
import sys


class Logger(Protocol):
    """Abstraction for logging operations.

    Replaces direct print() statements throughout the codebase.
    Enables structured logging and testability.
    """

    def info(self, message: str) -> None:
        """Log informational message."""
        ...

    def warning(self, message: str) -> None:
        """Log warning message."""
        ...

    def error(self, message: str) -> None:
        """Log error message."""
        ...

    def debug(self, message: str) -> None:
        """Log debug message."""
        ...


class FileSystemService(Protocol):
    """Abstraction for filesystem operations.

    Wraps all Path and file I/O operations to enable testing without
    real filesystem access. Critical for unit test isolation.
    """

    def exists(self, path: Union[str, Path]) -> bool:
        """Check if path exists."""
        ...

    def is_file(self, path: Union[str, Path]) -> bool:
        """Check if path is a file."""
        ...

    def is_dir(self, path: Union[str, Path]) -> bool:
        """Check if path is a directory."""
        ...

    def read_file(self, path: Union[str, Path]) -> str:
        """Read entire file as string."""
        ...

    def write_file(self, path: Union[str, Path], content: str) -> None:
        """Write string content to file."""
        ...

    def mkdir(self, path: Union[str, Path], parents: bool = True, exist_ok: bool = True) -> None:
        """Create directory (with parents if specified)."""
        ...

    def rmtree(self, path: Union[str, Path]) -> None:
        """Recursively remove directory tree."""
        ...

    def glob(self, path: Union[str, Path], pattern: str) -> List[Path]:
        """Find all files matching glob pattern."""
        ...

    def iterdir(self, path: Union[str, Path]) -> Iterator[Path]:
        """Iterate over directory contents."""
        ...

    def open(self, path: Union[str, Path], mode: str = 'r', buffering: int = -1) -> Any:
        """Open file and return file handle."""
        ...


class ProcessHandle(Protocol):
    """Abstraction for subprocess handle.

    Wraps subprocess.Popen object methods.
    """

    def poll(self) -> Optional[int]:
        """Check if process has terminated. Returns exit code or None."""
        ...

    def wait(self) -> int:
        """Wait for process to terminate and return exit code."""
        ...


class ProcessExecutor(Protocol):
    """Abstraction for process execution.

    Wraps subprocess.Popen to enable testing without spawning real processes.
    """

    def popen(
        self,
        cmd: List[str],
        stdout: Optional[Any] = None,
        stderr: Optional[Any] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None
    ) -> ProcessHandle:
        """Execute command and return process handle."""
        ...


class TimeProvider(Protocol):
    """Abstraction for time operations.

    Enables deterministic testing by controlling time.
    Critical for testing time-dependent code like progress tracking.
    """

    def current_time(self) -> float:
        """Get current time in seconds since epoch."""
        ...

    def sleep(self, seconds: float) -> None:
        """Sleep for specified number of seconds."""
        ...


class EnvironmentProvider(Protocol):
    """Abstraction for environment access.

    Wraps os.environ and platform.system() to enable testing
    across different platforms without actually changing the system.
    """

    def get_environ(self) -> Dict[str, str]:
        """Get copy of environment variables."""
        ...

    def get_system_type(self) -> str:
        """Get system type ('Darwin', 'Linux', 'Windows', etc.)."""
        ...


class ToolLocator(Protocol):
    """Abstraction for external tool discovery.

    Wraps shutil.which() to enable testing without requiring
    tools to be installed (caffeinate, systemd-inhibit, stdbuf, etc.).
    """

    def find_tool(self, tool_name: str) -> Optional[str]:
        """Find tool in PATH and return absolute path, or None if not found."""
        ...

    def has_tool(self, tool_name: str) -> bool:
        """Check if tool exists in PATH."""
        ...


class ConfigLoader(Protocol):
    """Abstraction for configuration file loading.

    Wraps YAML loading to enable testing with mock configurations
    without requiring actual config files.
    """

    def load_yaml(self, path: str) -> Dict[str, Any]:
        """Load YAML file and return parsed dictionary."""
        ...
