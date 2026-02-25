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
from cortex.utils.device import probe_pmu_available


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

    def check_build_status(self) -> SystemCheck:
        """Check if harness, adapter, and kernel plugins are built."""
        harness_path = 'src/engine/harness/cortex'
        adapter_path = 'primitives/adapters/v1/native/cortex_adapter_native'

        has_harness = self.fs.exists(harness_path)
        has_adapter = self.fs.exists(adapter_path)
        kernel_plugins = self.fs.glob('primitives/kernels/v1', '*@*/lib*.*')

        if not has_harness and not has_adapter and not kernel_plugins:
            return SystemCheck(
                'Build Status',
                'fail',
                'Nothing built. Run `make all` to build harness, adapter, and kernels.',
                critical=True,
            )

        parts = []
        if not has_harness:
            parts.append('harness missing')
        if not has_adapter:
            parts.append('adapter missing')
        if not kernel_plugins:
            parts.append('no kernel plugins')

        if parts:
            return SystemCheck(
                'Build Status',
                'warn',
                f'Partial build: {", ".join(parts)}. Run `make all`.',
                critical=False,
            )

        return SystemCheck(
            'Build Status',
            'pass',
            f'Harness, adapter, and {len(kernel_plugins)} kernel plugin(s) built',
        )

    def check_pmu_privilege(self) -> SystemCheck:
        """Check PMU (performance counter) access privilege.

        Probes by running cortex_inscount on the noop kernel. Always non-critical
        since latency benchmarks are valid without PMU data.
        """
        # Pre-probe existence checks for granular messaging
        inscount_path = 'sdk/kernel/tools/cortex_inscount'
        if not self.fs.exists(inscount_path):
            return SystemCheck(
                'PMU Access',
                'warn',
                'cortex_inscount not built (run `make all`). PMU data optional.',
                critical=False,
            )

        noop_dir = 'primitives/kernels/v1/noop@f32'
        noop_built = any(
            self.fs.exists(f'{noop_dir}/libnoop{ext}')
            for ext in ('.dylib', '.so')
        )
        if not noop_built:
            return SystemCheck(
                'PMU Access',
                'warn',
                'Noop kernel not built (run `make all`). PMU probe skipped.',
                critical=False,
            )

        # Delegate actual probe to shared utility
        if probe_pmu_available(self.fs, self.process):
            return SystemCheck(
                'PMU Access',
                'pass',
                'Performance counters available (instruction/cycle counting enabled)',
            )

        # PMU unavailable — platform-specific guidance
        system = self.env.get_system_type()
        if system == 'Darwin':
            msg = ('PMU counters unavailable. Run with `sudo` for instruction/cycle data. '
                   'Latency benchmarks are valid without PMU.')
        elif system == 'Linux':
            msg = ('PMU counters unavailable. One-time fix: '
                   '`sudo setcap cap_perfmon=ep <adapter_path>`. '
                   'Latency benchmarks are valid without PMU.')
        else:
            msg = 'PMU counters unavailable. Latency benchmarks are valid without PMU.'

        return SystemCheck('PMU Access', 'warn', msg, critical=False)

    def check_rt_scheduling(self) -> SystemCheck:
        """Check real-time scheduling capability.

        macOS does not support RT scheduling (expected). Linux checks for
        CAP_SYS_NICE capability. Always non-critical.
        """
        system = self.env.get_system_type()

        if system == 'Darwin':
            return SystemCheck(
                'RT Scheduling',
                'pass',
                'macOS uses best-effort scheduling (RT not available, expected)',
            )

        if system == 'Linux':
            try:
                status_path = '/proc/self/status'
                if self.fs.exists(status_path):
                    content = self.fs.read_file(status_path)
                    for line in content.split('\n'):
                        if line.startswith('CapEff:'):
                            hex_caps = line.split(':')[1].strip()
                            caps = int(hex_caps, 16)
                            # Bit 23 = CAP_SYS_NICE
                            if caps & (1 << 23):
                                return SystemCheck(
                                    'RT Scheduling',
                                    'pass',
                                    'CAP_SYS_NICE available (SCHED_FIFO/SCHED_RR supported)',
                                )
                            else:
                                return SystemCheck(
                                    'RT Scheduling',
                                    'warn',
                                    'CAP_SYS_NICE not set. Run with `sudo` or '
                                    '`sudo setcap cap_sys_nice=ep <binary>` for RT scheduling.',
                                    critical=False,
                                )
            except (ValueError, IndexError) as e:
                self.log.info(f"Could not parse /proc/self/status capabilities: {e}")
            except Exception as e:
                self.log.info(f"RT scheduling check failed: {e}")

            return SystemCheck(
                'RT Scheduling',
                'warn',
                'Unable to determine RT scheduling capability',
                critical=False,
            )

        return SystemCheck(
            'RT Scheduling',
            'warn',
            f'Unsupported platform: {system}',
            critical=False,
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
            self.check_build_status(),
            self.check_pmu_privilege(),
            self.check_rt_scheduling(),
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
