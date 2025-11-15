"""
Host power configuration for CORTEX benchmarks.

TEMPORARY: Fall 2025 implementation for x86 host machines only.
Spring 2026: Will be redesigned when device adapters exist.

REMOVAL/REFACTORING PLAN (Spring 2026):
- Option A: Rename to apply_host_power_config() when device adapters exist
- Option B: Remove entirely if device adapters handle all power management

See: docs/architecture/adr-001-temporary-host-power-config.md

Platform Support:
- Linux x86: Full support (cpufreq governor, turbo control)
- macOS: Warning-only (CPU frequency managed by OS)
- Other: Warning-only

Design:
- Context manager pattern for automatic cleanup
- Preserves original settings and restores on exit
- Isolated utility - no coupling to core engine
"""

import platform
import subprocess
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, Dict, Any
import logging
import glob

logger = logging.getLogger(__name__)


class LinuxPowerConfig:
    """Linux-specific power configuration (cpufreq)"""

    def __init__(self):
        self.original_governors = {}
        self.original_turbo_state = None
        self.turbo_control_path = None

    def _detect_turbo_control(self) -> Optional[Path]:
        """
        Detect which turbo boost control interface is available.

        Returns:
            Path to turbo control file, or None if not available
        """
        # Intel: /sys/devices/system/cpu/intel_pstate/no_turbo
        intel_path = Path('/sys/devices/system/cpu/intel_pstate/no_turbo')
        if intel_path.exists():
            return intel_path

        # AMD: /sys/devices/system/cpu/cpufreq/boost
        amd_path = Path('/sys/devices/system/cpu/cpufreq/boost')
        if amd_path.exists():
            return amd_path

        return None

    def apply_governor(self, governor: str) -> bool:
        """
        Apply CPU frequency governor to all cores.
        Saves original state for restoration.

        Args:
            governor: "performance", "powersave", "ondemand", etc.

        Returns:
            True if successful, False otherwise
        """
        governor_files = glob.glob('/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor')

        if not governor_files:
            logger.warning("No CPU frequency governor control found (not supported or no permission)")
            return False

        try:
            # Save original governors
            for gov_file in governor_files:
                with open(gov_file, 'r') as f:
                    self.original_governors[gov_file] = f.read().strip()

            # Apply new governor to all cores
            for gov_file in governor_files:
                with open(gov_file, 'w') as f:
                    f.write(governor + '\n')

            logger.info(f"Applied CPU governor '{governor}' to {len(governor_files)} cores")
            return True

        except PermissionError:
            logger.error(
                "Permission denied: CPU governor control requires root privileges.\n"
                "Run with sudo: sudo PYTHONPATH=src python3 -m cortex run ..."
            )
            return False
        except Exception as e:
            logger.error(f"Failed to apply CPU governor: {e}")
            return False

    def apply_turbo(self, enabled: bool) -> bool:
        """
        Control Intel Turbo Boost / AMD Turbo Core.
        Saves original state for restoration.

        Args:
            enabled: True to enable, False to disable

        Returns:
            True if successful, False otherwise
        """
        self.turbo_control_path = self._detect_turbo_control()

        if not self.turbo_control_path:
            logger.warning("Turbo boost control not available (not supported or no permission)")
            return False

        try:
            # Save original turbo state
            with open(self.turbo_control_path, 'r') as f:
                self.original_turbo_state = f.read().strip()

            # Apply turbo setting
            # Note: Intel uses no_turbo (1 = disabled, 0 = enabled)
            #       AMD uses boost (1 = enabled, 0 = disabled)
            is_intel = 'intel_pstate' in str(self.turbo_control_path)

            if is_intel:
                # Intel: no_turbo=1 means turbo is OFF
                value = '0' if enabled else '1'
            else:
                # AMD: boost=1 means turbo is ON
                value = '1' if enabled else '0'

            with open(self.turbo_control_path, 'w') as f:
                f.write(value + '\n')

            vendor = "Intel" if is_intel else "AMD"
            state = "enabled" if enabled else "disabled"
            logger.info(f"Turbo boost ({vendor}) {state}")
            return True

        except PermissionError:
            logger.error(
                "Permission denied: Turbo boost control requires root privileges.\n"
                "Run with sudo: sudo PYTHONPATH=src python3 -m cortex run ..."
            )
            return False
        except Exception as e:
            logger.error(f"Failed to control turbo boost: {e}")
            return False

    def restore(self):
        """Restore original power settings"""
        try:
            # Restore governors
            for gov_file, original_value in self.original_governors.items():
                try:
                    with open(gov_file, 'w') as f:
                        f.write(original_value + '\n')
                except Exception as e:
                    logger.warning(f"Failed to restore governor for {gov_file}: {e}")

            if self.original_governors:
                logger.info(f"Restored original CPU governors for {len(self.original_governors)} cores")

            # Restore turbo state
            if self.original_turbo_state and self.turbo_control_path:
                try:
                    with open(self.turbo_control_path, 'w') as f:
                        f.write(self.original_turbo_state + '\n')
                    logger.info("Restored original turbo boost state")
                except Exception as e:
                    logger.warning(f"Failed to restore turbo state: {e}")

        except Exception as e:
            logger.warning(f"Error during power config restoration: {e}")


class DarwinPowerConfig:
    """macOS power configuration (stub - OS-managed)"""

    def apply_governor(self, governor: str) -> bool:
        """
        macOS does not support manual CPU governor control.
        CPU frequency is automatically managed by the OS.

        Args:
            governor: Ignored on macOS

        Returns:
            True (not an error - just OS limitation)
        """
        logger.warning(
            "macOS does not support manual CPU governor control. "
            "CPU frequency is automatically managed by the OS. "
            f"Requested governor '{governor}' will be ignored."
        )
        return True  # Not an error - just OS limitation

    def apply_turbo(self, enabled: bool) -> bool:
        """
        macOS does not support manual Turbo Boost control.
        Turbo Boost is automatically managed by the OS.

        Args:
            enabled: Ignored on macOS

        Returns:
            True (not an error - just OS limitation)
        """
        state = "enable" if enabled else "disable"
        logger.warning(
            "macOS does not support manual Turbo Boost control. "
            "Turbo Boost is automatically managed by the OS. "
            f"Request to {state} turbo boost will be ignored."
        )
        return True  # Not an error - just OS limitation

    def restore(self):
        """No-op on macOS - nothing to restore"""
        pass


@contextmanager
def apply_power_config(power_config: Dict[str, Any]):
    """
    Apply host power configuration as a context manager.
    Automatically restores original settings on exit.

    TEMPORARY: Fall 2025 x86 host only. Spring 2026: redesign for device adapters.

    Usage:
        with apply_power_config(config['power']):
            # Run benchmark
            run_harness(...)

    Args:
        power_config: Power section from CORTEX config YAML

    Yields:
        None

    Example YAML:
        power:
          governor: "performance"
          turbo: false
    """
    system = platform.system()

    if system == 'Linux':
        controller = LinuxPowerConfig()
    elif system == 'Darwin':
        controller = DarwinPowerConfig()
    else:
        logger.warning(f"Power config not supported on {system}")
        yield
        return

    # Apply settings
    try:
        if 'governor' in power_config:
            controller.apply_governor(power_config['governor'])

        if 'turbo' in power_config:
            controller.apply_turbo(power_config['turbo'])

        yield

    finally:
        # Always restore original settings (even on error)
        controller.restore()
