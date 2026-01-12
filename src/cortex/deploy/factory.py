"""
DeployerFactory - Parse device strings and route to appropriate deployers.

Format-based routing:
    user@host              → SSHDeployer (auto-deploy)
    user@host:2222         → SSHDeployer with custom SSH port
    tcp://host:port        → Manual connection (return URI string)
    serial:///dev/ttyUSB0  → Manual connection (return URI string)
    stm32:/dev/ttyUSB0     → JTAGDeployer (future, not yet implemented)
"""

from typing import Union


class DeployerFactory:
    """Factory for parsing device strings into deployers or transport URIs."""

    @staticmethod
    def from_device_string(device: str) -> Union['Deployer', str]:
        """
        Parse device string and return deployer (auto-deploy) or transport URI (manual).

        Args:
            device: Device connection string (or None for local default)

        Returns:
            - Deployer instance for auto-deploy formats (user@host, stm32:)
            - Transport URI string for manual formats (tcp://, serial://, etc.)

        Auto-deploy formats (return Deployer):
            user@host              → SSHDeployer(user, host, port=22)
            user@host:2222         → SSHDeployer(user, host, port=2222)
            stm32:serial           → JTAGDeployer(device) [future]

        Manual formats (return transport URI string):
            tcp://host:port   → "tcp://host:port"
            serial:///dev/tty → "serial:///dev/tty?baud=115200"
            local://          → "local://"

        Raises:
            ValueError: If format not recognized

        Example (auto-deploy):
            result = DeployerFactory.from_device_string("nvidia@192.168.1.123")
            if isinstance(result, Deployer):
                deploy_result = result.deploy()
                transport_uri = deploy_result.transport_uri
                # ... run benchmark with transport_uri ...
                result.cleanup()

        Example (manual):
            result = DeployerFactory.from_device_string("tcp://192.168.1.123:9000")
            if isinstance(result, str):
                transport_uri = result  # Adapter already running
                # ... run benchmark with transport_uri ...
                # No cleanup needed (adapter is persistent)
        """
        # Lazy import to avoid circular dependencies
        from .ssh_deployer import SSHDeployer

        if not device:
            return "local://"  # Default to local adapter

        if '@' in device:
            # Parse SSH format: user@host[:port]
            user, host_part = device.split('@', 1)

            # Parse port if specified
            if ':' in host_part:
                host, port_str = host_part.rsplit(':', 1)
                try:
                    port = int(port_str)
                    if not (1 <= port <= 65535):
                        raise ValueError(f"Port must be 1-65535, got {port}")
                except ValueError as e:
                    raise ValueError(f"Invalid SSH port in device string '{device}': {e}")
            else:
                host = host_part
                port = 22

            return SSHDeployer(user, host, ssh_port=port)

        if device.startswith('stm32:'):
            raise NotImplementedError("JTAGDeployer not yet implemented (Spring 2026)")

        # Manual transport formats - return URI as-is
        if device.startswith(('tcp://', 'serial://', 'local://')):
            return device

        raise ValueError(
            f"Unknown device format: {device}\n"
            f"Expected: user@host | tcp://host:port | serial:///dev/device | "
            f"local:// | stm32:device"
        )
