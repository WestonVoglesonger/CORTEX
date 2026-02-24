"""Check deadline compliance for a benchmark run."""
from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.utils.paths import get_most_recent_run, get_run_directory
from cortex.core import ConsoleLogger, RealFileSystemService
import json


def setup_parser(parser):
    """Setup argument parser for check-deadline command"""
    parser.add_argument(
        '--run-name',
        help='Name of run to check (default: most recent run)'
    )
    parser.add_argument(
        '--threshold',
        type=float,
        default=1.0,
        help='Maximum acceptable miss rate %% (default: 1.0)'
    )
    parser.add_argument(
        '--format',
        choices=['table', 'json'],
        default='table',
        help='Output format (default: table)'
    )
    parser.add_argument(
        '--telemetry-format', '-t',
        choices=['ndjson', 'csv', 'auto'],
        default='ndjson',
        help='Preferred telemetry format to load (default: ndjson)'
    )


def execute(args):
    """Execute check-deadline command.

    Returns 0 if all kernels pass, 1 if any kernel exceeds the threshold.
    """
    # Determine which run to check
    if args.run_name:
        run_name = args.run_name
    else:
        run_name = get_most_recent_run()
        if not run_name:
            print("Error: No runs found in results/")
            return 1

    run_dir = get_run_directory(run_name)
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        return 1

    # Create analyzer with production dependencies
    filesystem = RealFileSystemService()
    logger = ConsoleLogger()
    analyzer = TelemetryAnalyzer(filesystem=filesystem, logger=logger)

    # Load telemetry
    df = analyzer.load_telemetry(str(run_dir), prefer_format=args.telemetry_format)
    if df is None or df.empty:
        print("Error: No telemetry data found")
        return 1

    # Calculate statistics
    stats = analyzer.calculate_statistics(df)

    if 'miss_rate' not in stats.columns:
        print("Error: No deadline data in telemetry (deadline_missed column missing)")
        return 1

    # Check each kernel against threshold
    threshold = args.threshold
    results = []
    any_failed = False

    for kernel_name in stats.index:
        row = stats.loc[kernel_name]
        miss_rate = row['miss_rate']
        total = int(row['total_samples'])
        misses = int(row['deadline_misses'])
        passed = miss_rate <= threshold

        if not passed:
            any_failed = True

        results.append({
            'kernel': kernel_name,
            'miss_rate': round(miss_rate, 4),
            'total_samples': total,
            'deadline_misses': misses,
            'threshold': threshold,
            'status': 'PASS' if passed else 'FAIL',
        })

    # Output results
    if args.format == 'json':
        output = {
            'run_name': run_name,
            'threshold': threshold,
            'overall': 'FAIL' if any_failed else 'PASS',
            'kernels': results,
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Deadline Check: {run_name} (threshold: {threshold}%)")
        print("-" * 70)
        print(f"{'Kernel':<25} {'Miss Rate %':>12} {'Misses':>8} {'Total':>8} {'Status':>8}")
        print("-" * 70)
        for r in results:
            status_str = r['status']
            print(f"{r['kernel']:<25} {r['miss_rate']:>11.4f}% {r['deadline_misses']:>8} {r['total_samples']:>8} {status_str:>8}")
        print("-" * 70)
        overall = "FAIL" if any_failed else "PASS"
        print(f"Overall: {overall}")

    return 1 if any_failed else 0
