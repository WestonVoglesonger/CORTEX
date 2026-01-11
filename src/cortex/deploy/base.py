"""
Deployer Protocol - Abstract interface for device deployment strategies.

This module defines the core protocol that all deployment strategies must implement.
Supports multiple deployment types: SSH (Jetson, RPi), JTAG (STM32), Docker, etc.
"""

from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass


@dataclass
class DeploymentResult:
    """
    Result of successful deployment.

    Attributes:
        success: Whether deployment succeeded
        transport_uri: Connection string for adapter (e.g., "tcp://192.168.1.123:9000")
        adapter_pid: Remote process ID (None for embedded/always-on adapters)
        metadata: Platform info, build time, validation status, etc.

    Note on adapter_pid=None:
        This is a first-class case for:
        - Embedded devices (STM32 firmware always listening)
        - Persistent adapters (daemon already running)
        - Hardware accelerators (FPGA, no process concept)
    """
    success: bool
    transport_uri: str
    adapter_pid: Optional[int]
    metadata: dict[str, any]


@dataclass
class CleanupResult:
    """
    Result of cleanup operation.

    Attributes:
        success: Whether cleanup succeeded
        errors: List of non-fatal issues encountered during cleanup
    """
    success: bool
    errors: list[str]


@runtime_checkable
class Deployer(Protocol):
    """
    Interface for device deployment strategies.

    All deployers must implement these methods to integrate with
    cortex run/pipeline commands.

    @runtime_checkable decorator enables isinstance() checks:
        deployer = SSHDeployer(...)
        assert isinstance(deployer, Deployer)  # Works at runtime

    Implementations:
        - SSHDeployer: rsync + remote build + daemon (Jetson, RPi, Linux SBCs)
        - JTAGDeployer: cross-compile + flash (STM32, embedded ARM) [future]
        - DockerDeployer: container-based deployment [future]
    """

    def deploy(self, verbose: bool = False, skip_validation: bool = False) -> DeploymentResult:
        """
        Deploy code, build (if needed), start adapter.

        Args:
            verbose: Stream build output to user
            skip_validation: Skip oracle validation (faster, trust correctness)

        Returns:
            DeploymentResult with transport_uri and metadata

        Raises:
            DeploymentError: If deployment fails at any step

        Postconditions:
            - Adapter is running and listening on transport_uri
            - Device has all necessary files to run benchmarks
            - Cleanup must be called after benchmarking

        Example:
            result = deployer.deploy(verbose=True)
            print(f"Adapter ready at {result.transport_uri}")
            # ... run benchmarks ...
            deployer.cleanup()
        """
        ...

    def cleanup(self) -> CleanupResult:
        """
        Stop adapter and remove all deployment artifacts.

        Returns:
            CleanupResult indicating success/failure

        Postconditions:
            - Device no longer responding to protocol messages (if applicable)
            - Resources released (files, processes, ports, etc.)
            - Device in clean state for next deployment

        Note:
            Must not raise exceptions (errors go in CleanupResult.errors)

            What "cleanup" means is deployer-specific:
                - SSH: kill process, rm files
                - Serial: close port, optionally reset device
                - Docker: stop container, remove image (optional)

        Example:
            result = deployer.cleanup()
            if not result.success:
                print(f"Cleanup issues: {result.errors}")
        """
        ...

    def fetch_logs(self, output_dir: str) -> dict[str, any]:
        """
        Fetch deployment logs from device and save to output_dir.

        MUST be called BEFORE cleanup() to retrieve logs before deletion.

        Optional method: Not all deployers have logs to fetch.
        Implementations that don't fetch logs can return empty success result.

        Args:
            output_dir: Directory to save logs (e.g., results/run-*/deployment/)

        Returns:
            Dictionary with fetch results:
            {
                "success": bool,              # True if all fetches succeeded
                "files_fetched": list[str],   # Files successfully written
                "errors": list[str],          # Any errors encountered
                "sizes": dict[str, int]       # File sizes in bytes
            }

        Side effects:
            - Creates output_dir/ if it doesn't exist
            - Writes log files (adapter.log, build.log, etc.)
            - May write metadata.json with deployment info

        Note:
            Must not raise exceptions (errors go in result dict)
            Large files (>10MB) should be truncated with warning

        Example:
            result = deployer.fetch_logs("results/run-001/deployment")
            if not result["success"]:
                print(f"Log fetch issues: {result['errors']}")
        """
        # Default implementation for deployers without logs
        return {
            "success": True,
            "files_fetched": [],
            "errors": [],
            "sizes": {}
        }
