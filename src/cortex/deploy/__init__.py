"""
Device deployment subsystem.

Provides protocol-based deployment strategies for remote devices:
    - SSHDeployer: rsync + remote build + daemon (Jetson, RPi, Linux SBCs)
    - JTAGDeployer: cross-compile + flash (STM32) [future, Spring 2026]

Public API:
    - Deployer: Protocol interface
    - DeployerFactory: Parse device strings
    - DeploymentResult, CleanupResult: Result types
    - DeploymentError, CleanupError: Exceptions
    - SSHDeployer: SSH deployment implementation
"""

from .base import Deployer, DeploymentResult, CleanupResult
from .factory import DeployerFactory
from .exceptions import DeploymentError, CleanupError
from .ssh_deployer import SSHDeployer

__all__ = [
    # Protocol and types
    "Deployer",
    "DeploymentResult",
    "CleanupResult",

    # Factory
    "DeployerFactory",

    # Exceptions
    "DeploymentError",
    "CleanupError",

    # Implementations
    "SSHDeployer",
]
