"""System configuration checker for benchmark reproducibility

CRIT-004 PR #3: Refactored to use dependency injection for full testability.
"""
from pathlib import Path
from typing import Dict, List, Tuple

from cortex.core import (
    FileSystemService,
    ProcessExecutor,
    EnvironmentProvider,
    ToolLocator,
    Logger
)


class SystemCheck:
    """Represents a single system configuration check"""
    def __init__(self, name: str, status: str, message: str, critical: bool = False):
        self.name = name
        self.status = status  # 'pass', 'warn', 'fail'
        self.message = message
        self.critical = critical


class SystemChecker:
    """System configuration checker with dependency injection.

    Checks system configuration for benchmark reproducibility across
    Linux, macOS, and Windows platforms. All external dependencies
    are injected for testability.
    """

    def __init__(
        self,
        filesystem: FileSystemService,
        process_executor: ProcessExecutor,
        env_provider: EnvironmentProvider,
        tool_locator: ToolLocator,
        logger: Logger
    ):
        """Initialize with injected dependencies.

        Args:
            filesystem: Filesystem operations abstraction
            process_executor: Subprocess execution abstraction
            env_provider: Platform/environment detection
            tool_locator: External tool discovery
            logger: Logging abstraction
        """
        self.fs = filesystem
        self.process = process_executor
        self.env = env_provider
        self.tools = tool_locator
        self.log = logger

    def check_cpu_governor(self) -> SystemCheck:
        """Check CPU frequency governor setting"""
        system = self.env.get_system_type()

        if system == 'Linux':
            try:
                # Check CPU governor on Linux
                gov_path = '/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'
                if self.fs.exists(gov_path):
                    governor = self.fs.read_file(gov_path).strip()
                    if governor == 'performance':
                        return SystemCheck(
                            'CPU Governor',
                            'pass',
                            f'Set to performance mode ({governor})'
                        )
                    else:
                        return SystemCheck(
                            'CPU Governor',
                            'warn',
                            f'Set to {governor} (recommend performance)',
                            critical=False
                        )
                else:
                    return SystemCheck(
                        'CPU Governor',
                        'warn',
                        'Unable to detect governor (cpufreq not available)'
                    )
            except Exception as e:
                return SystemCheck(
                    'CPU Governor',
                    'warn',
                    f'Unable to check: {e}'
                )

        elif system == 'Darwin':
            # macOS doesn't expose governor interface
            return SystemCheck(
                'CPU Governor',
                'pass',
                'macOS manages CPU frequency automatically'
            )

        else:
            return SystemCheck(
                'CPU Governor',
                'warn',
                f'Unsupported platform: {system}'
            )

    def check_turbo_boost(self) -> SystemCheck:
        """Check Intel Turbo Boost / AMD Turbo Core status"""
        system = self.env.get_system_type()

        if system == 'Linux':
            try:
                # Intel turbo boost
                intel_turbo = '/sys/devices/system/cpu/intel_pstate/no_turbo'
                if self.fs.exists(intel_turbo):
                    no_turbo = self.fs.read_file(intel_turbo).strip()
                    if no_turbo == '1':
                        return SystemCheck(
                            'Turbo Boost',
                            'pass',
                            'Disabled (Intel Turbo Boost off for consistency)'
                        )
                    else:
                        return SystemCheck(
                            'Turbo Boost',
                            'warn',
                            'Enabled (may cause frequency variance)',
                            critical=False
                        )

                # AMD turbo core
                amd_turbo = '/sys/devices/system/cpu/cpufreq/boost'
                if self.fs.exists(amd_turbo):
                    boost = self.fs.read_file(amd_turbo).strip()
                    if boost == '0':
                        return SystemCheck(
                            'Turbo Boost',
                            'pass',
                            'Disabled (AMD Turbo Core off for consistency)'
                        )
                    else:
                        return SystemCheck(
                            'Turbo Boost',
                            'warn',
                            'Enabled (may cause frequency variance)',
                            critical=False
                        )

                return SystemCheck(
                    'Turbo Boost',
                    'warn',
                    'Unable to detect turbo state (neither Intel nor AMD interface found)'
                )

            except Exception as e:
                return SystemCheck(
                    'Turbo Boost',
                    'warn',
                    f'Unable to check: {e}'
                )

        elif system == 'Darwin':
            # macOS doesn't expose turbo boost control
            return SystemCheck(
                'Turbo Boost',
                'pass',
                'macOS manages turbo boost automatically'
            )

        else:
            return SystemCheck(
                'Turbo Boost',
                'warn',
                f'Unsupported platform: {system}'
            )

    def check_thermal_state(self) -> SystemCheck:
        """Check system thermal condition"""
        system = self.env.get_system_type()

        if system == 'Darwin':
            try:
                # Use pmset to check thermal state
                result = self.process.run(
                    ['pmset', '-g', 'therm'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.returncode == 0:
                    output = result.stdout.lower()
                    if 'cpu_speed_limit' in output:
                        # Parse CPU speed limit
                        for line in output.split('\n'):
                            if 'cpu_speed_limit' in line:
                                if '100' in line:
                                    return SystemCheck(
                                        'Thermal State',
                                        'pass',
                                        'No thermal throttling detected'
                                    )
                                else:
                                    return SystemCheck(
                                        'Thermal State',
                                        'warn',
                                        'Thermal throttling detected (let system cool down)',
                                        critical=True
                                    )

                    return SystemCheck(
                        'Thermal State',
                        'pass',
                        'No thermal issues detected'
                    )
                else:
                    return SystemCheck(
                        'Thermal State',
                        'warn',
                        'Unable to check thermal state'
                    )

            except Exception as e:
                return SystemCheck(
                    'Thermal State',
                    'warn',
                    f'Unable to check: {e}'
                )

        elif system == 'Linux':
            try:
                # Check thermal zones
                thermal_dir = '/sys/class/thermal'
                if self.fs.exists(thermal_dir):
                    max_temp = 0
                    for zone_path in self.fs.glob(thermal_dir, 'thermal_zone*'):
                        temp_file = str(Path(zone_path) / 'temp')
                        if self.fs.exists(temp_file):
                            temp_millicelsius = int(self.fs.read_file(temp_file).strip())
                            temp_celsius = temp_millicelsius / 1000
                            max_temp = max(max_temp, temp_celsius)

                    if max_temp > 80:
                        return SystemCheck(
                            'Thermal State',
                            'warn',
                            f'High temperature detected ({max_temp:.1f}°C - let system cool down)',
                            critical=True
                        )
                    elif max_temp > 0:
                        return SystemCheck(
                            'Thermal State',
                            'pass',
                            f'Temperature normal ({max_temp:.1f}°C)'
                        )

                return SystemCheck(
                    'Thermal State',
                    'warn',
                    'Unable to detect thermal sensors'
                )

            except Exception as e:
                return SystemCheck(
                    'Thermal State',
                    'warn',
                    f'Unable to check: {e}'
                )

        else:
            return SystemCheck(
                'Thermal State',
                'warn',
                f'Unsupported platform: {system}'
            )

    def check_background_services(self) -> SystemCheck:
        """Check for resource-intensive background services"""
        system = self.env.get_system_type()

        # Common resource-heavy processes to check for
        heavy_processes = [
            'docker', 'dockerd', 'containerd',  # Docker
            'VBoxHeadless', 'VirtualBox',       # VirtualBox
            'vmware', 'vmware-vmx',             # VMware
            'node', 'npm',                      # Node.js (build servers)
            'make', 'gcc', 'clang',             # Compilation
            # Note: 'python' removed - too broad, would flag CORTEX itself
        ]

        try:
            if system not in ['Darwin', 'Linux']:
                return SystemCheck(
                    'Background Services',
                    'warn',
                    f'Unsupported platform: {system}'
                )

            result = self.process.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                running_heavy = []
                for process in heavy_processes:
                    if process in result.stdout:
                        # Count occurrences (rough estimate)
                        count = result.stdout.count(process)
                        if count > 2:  # More than a couple instances
                            running_heavy.append(f'{process} ({count})')

                if running_heavy:
                    return SystemCheck(
                        'Background Services',
                        'warn',
                        f'Heavy processes detected: {", ".join(running_heavy)}',
                        critical=False
                    )
                else:
                    return SystemCheck(
                        'Background Services',
                        'pass',
                        'No heavy background processes detected'
                    )

            return SystemCheck(
                'Background Services',
                'warn',
                'Unable to check running processes'
            )

        except Exception as e:
            return SystemCheck(
                'Background Services',
                'warn',
                f'Unable to check: {e}'
            )

    def check_sleep_prevention(self) -> SystemCheck:
        """Check if sleep prevention tools are available"""
        system = self.env.get_system_type()

        if system == 'Darwin':
            if self.tools.has_tool('caffeinate'):
                return SystemCheck(
                    'Sleep Prevention',
                    'pass',
                    'caffeinate available (automatic during runs)'
                )
            else:
                return SystemCheck(
                    'Sleep Prevention',
                    'fail',
                    'caffeinate not found (required on macOS)',
                    critical=True
                )

        elif system == 'Linux':
            if self.tools.has_tool('systemd-inhibit'):
                return SystemCheck(
                    'Sleep Prevention',
                    'pass',
                    'systemd-inhibit available (automatic during runs)'
                )
            else:
                return SystemCheck(
                    'Sleep Prevention',
                    'warn',
                    'systemd-inhibit not found (ensure system won\'t sleep)',
                    critical=False
                )

        else:
            return SystemCheck(
                'Sleep Prevention',
                'warn',
                f'Unsupported platform: {system}'
            )

    def run_all_checks(self) -> Tuple[List[SystemCheck], bool]:
        """Run all system configuration checks.

        Returns:
            Tuple of (list of checks, all_pass boolean)
        """
        checks = [
            self.check_cpu_governor(),
            self.check_turbo_boost(),
            self.check_thermal_state(),
            self.check_background_services(),
            self.check_sleep_prevention(),
        ]

        # Determine if all critical checks passed
        all_pass = all(
            check.status != 'fail' and not (check.critical and check.status == 'warn')
            for check in checks
        )

        return checks, all_pass

    def print_results(self, checks: List[SystemCheck], verbose: bool = False) -> None:
        """Print check results in a formatted table using logger.

        Args:
            checks: List of SystemCheck results
            verbose: Show verbose output (currently unused, for future enhancement)
        """
        self.log.info("=" * 80)
        self.log.info("SYSTEM CONFIGURATION CHECK")
        self.log.info("=" * 80)
        self.log.info("")

        # Status symbols
        symbols = {
            'pass': '✓',
            'warn': '⚠',
            'fail': '✗'
        }

        for check in checks:
            symbol = symbols.get(check.status, '?')
            critical_marker = ' [CRITICAL]' if check.critical else ''
            self.log.info(f"{symbol} {check.name}: {check.message}{critical_marker}")

        self.log.info("")
        self.log.info("=" * 80)

        # Summary
        pass_count = sum(1 for c in checks if c.status == 'pass')
        warn_count = sum(1 for c in checks if c.status == 'warn')
        fail_count = sum(1 for c in checks if c.status == 'fail')

        self.log.info(f"Summary: {pass_count} passed, {warn_count} warnings, {fail_count} failed")

        # Critical warnings
        critical_issues = [c for c in checks if c.critical and c.status in ['warn', 'fail']]
        if critical_issues:
            self.log.info("")
            self.log.info("Critical Issues:")
            for issue in critical_issues:
                self.log.info(f"  - {issue.name}: {issue.message}")
            self.log.info("")
            self.log.info("Recommendation: Address critical issues before running benchmarks")

        self.log.info("=" * 80)


def setup_parser(parser):
    """Setup argument parser for check-system command"""
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose output'
    )


def execute(args):
    """Execute system configuration check.

    This is a facade function for backward compatibility. Creates a SystemChecker
    instance with production dependencies and runs the checks.

    Returns:
        Exit code: 0 if all checks passed, 1 if critical failures detected
    """
    from cortex.core import (
        RealFileSystemService,
        SubprocessExecutor,
        SystemEnvironmentProvider,
        SystemToolLocator,
        ConsoleLogger
    )

    # Create checker with production dependencies
    checker = SystemChecker(
        filesystem=RealFileSystemService(),
        process_executor=SubprocessExecutor(),
        env_provider=SystemEnvironmentProvider(),
        tool_locator=SystemToolLocator(),
        logger=ConsoleLogger()
    )

    # Run checks
    checks, all_pass = checker.run_all_checks()
    checker.print_results(checks, verbose=args.verbose)

    # Return exit code
    # 0: All checks passed
    # 1: Critical failures detected
    if all_pass:
        return 0
    else:
        return 1
