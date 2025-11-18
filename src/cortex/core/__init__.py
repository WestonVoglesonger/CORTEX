"""Core dependency injection infrastructure for CORTEX.

This module provides Protocol-based abstractions that enable dependency injection
and testability throughout the codebase. All external dependencies (filesystem,
subprocess, time, etc.) are abstracted via Protocols with production implementations.

CRIT-004: Implement Dependency Injection - Core Modules

Design:
- Protocol-based abstractions (typing.Protocol) for structural typing
- Production implementations for real-world use
- Easy mocking for unit tests
- Clean separation of concerns
"""

from cortex.core.protocols import (
    Logger,
    FileSystemService,
    ProcessExecutor,
    ProcessHandle,
    ProcessResult,
    TimeProvider,
    EnvironmentProvider,
    ToolLocator,
    ConfigLoader,
)

from cortex.core.implementations import (
    ConsoleLogger,
    RealFileSystemService,
    SubprocessExecutor,
    SystemTimeProvider,
    SystemEnvironmentProvider,
    SystemToolLocator,
    YamlConfigLoader,
)

__all__ = [
    # Protocols
    "Logger",
    "FileSystemService",
    "ProcessExecutor",
    "ProcessHandle",
    "ProcessResult",
    "TimeProvider",
    "EnvironmentProvider",
    "ToolLocator",
    "ConfigLoader",
    # Implementations
    "ConsoleLogger",
    "RealFileSystemService",
    "SubprocessExecutor",
    "SystemTimeProvider",
    "SystemEnvironmentProvider",
    "SystemToolLocator",
    "YamlConfigLoader",
]
