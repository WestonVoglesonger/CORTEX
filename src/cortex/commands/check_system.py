"""System configuration checker for benchmark reproducibility"""
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Tuple


class SystemCheck:
    """Represents a single system configuration check"""
    def __init__(self, name: str, status: str, message: str, critical: bool = False):
        self.name = name
        self.status = status  # 'pass', 'warn', 'fail'
        self.message = message
        self.critical = critical


def check_cpu_governor() -> SystemCheck:
    """Check CPU frequency governor setting"""
    system = platform.system()

    if system == 'Linux':
        try:
            # Check CPU governor on Linux
            gov_path = Path('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')
            if gov_path.exists():
                governor = gov_path.read_text().strip()
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


def check_turbo_boost() -> SystemCheck:
    """Check Intel Turbo Boost / AMD Turbo Core status"""
    system = platform.system()

    if system == 'Linux':
        try:
            # Intel turbo boost
            intel_turbo = Path('/sys/devices/system/cpu/intel_pstate/no_turbo')
            if intel_turbo.exists():
                no_turbo = intel_turbo.read_text().strip()
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
            amd_turbo = Path('/sys/devices/system/cpu/cpufreq/boost')
            if amd_turbo.exists():
                boost = amd_turbo.read_text().strip()
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


def check_thermal_state() -> SystemCheck:
    """Check system thermal condition"""
    system = platform.system()

    if system == 'Darwin':
        try:
            # Use pmset to check thermal state
            result = subprocess.run(
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
            thermal_dir = Path('/sys/class/thermal')
            if thermal_dir.exists():
                max_temp = 0
                for zone in thermal_dir.glob('thermal_zone*'):
                    temp_file = zone / 'temp'
                    if temp_file.exists():
                        temp_millicelsius = int(temp_file.read_text().strip())
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


def check_background_services() -> SystemCheck:
    """Check for resource-intensive background services"""
    system = platform.system()

    # Common resource-heavy processes to check for
    heavy_processes = [
        'docker', 'dockerd', 'containerd',  # Docker
        'VBoxHeadless', 'VirtualBox',       # VirtualBox
        'vmware', 'vmware-vmx',             # VMware
        'node', 'npm',                      # Node.js (build servers)
        'make', 'gcc', 'clang',             # Compilation
        'python',                           # Python (may be data processing)
    ]

    try:
        if system == 'Darwin':
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )
        elif system == 'Linux':
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )
        else:
            return SystemCheck(
                'Background Services',
                'warn',
                f'Unsupported platform: {system}'
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


def check_sleep_prevention() -> SystemCheck:
    """Check if sleep prevention tools are available"""
    system = platform.system()

    if system == 'Darwin':
        if shutil.which('caffeinate'):
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
        if shutil.which('systemd-inhibit'):
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


def run_all_checks() -> Tuple[List[SystemCheck], bool]:
    """
    Run all system configuration checks

    Returns:
        Tuple of (list of checks, all_pass boolean)
    """
    checks = [
        check_cpu_governor(),
        check_turbo_boost(),
        check_thermal_state(),
        check_background_services(),
        check_sleep_prevention(),
    ]

    # Determine if all critical checks passed
    all_pass = all(
        check.status != 'fail' and not (check.critical and check.status == 'warn')
        for check in checks
    )

    return checks, all_pass


def print_results(checks: List[SystemCheck], verbose: bool = False) -> None:
    """Print check results in a formatted table"""
    print("=" * 80)
    print("SYSTEM CONFIGURATION CHECK")
    print("=" * 80)
    print()

    # Status symbols
    symbols = {
        'pass': '✓',
        'warn': '⚠',
        'fail': '✗'
    }

    for check in checks:
        symbol = symbols.get(check.status, '?')
        critical_marker = ' [CRITICAL]' if check.critical else ''

        print(f"{symbol} {check.name}: {check.message}{critical_marker}")

    print()
    print("=" * 80)

    # Summary
    pass_count = sum(1 for c in checks if c.status == 'pass')
    warn_count = sum(1 for c in checks if c.status == 'warn')
    fail_count = sum(1 for c in checks if c.status == 'fail')

    print(f"Summary: {pass_count} passed, {warn_count} warnings, {fail_count} failed")

    # Critical warnings
    critical_issues = [c for c in checks if c.critical and c.status in ['warn', 'fail']]
    if critical_issues:
        print()
        print("Critical Issues:")
        for issue in critical_issues:
            print(f"  - {issue.name}: {issue.message}")
        print()
        print("Recommendation: Address critical issues before running benchmarks")

    print("=" * 80)


def setup_parser(parser):
    """Setup argument parser for check-system command"""
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose output'
    )


def execute(args):
    """Execute system configuration check"""
    checks, all_pass = run_all_checks()
    print_results(checks, verbose=args.verbose)

    # Return exit code
    # 0: All checks passed
    # 1: Critical failures detected
    if all_pass:
        return 0
    else:
        return 1
