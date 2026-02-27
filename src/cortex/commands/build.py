"""Build command"""
import os
import subprocess
import sys

def setup_parser(parser):
    """Setup argument parser for build command"""
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose build output'
    )
    parser.add_argument(
        '--kernels-only',
        action='store_true',
        help='Only build kernel plugins'
    )


def execute(args):
    """Execute build command"""
    print("=" * 80)
    print("CORTEX Build")
    print("=" * 80)

    print("\nBuilding...")

    if args.kernels_only:
        target = 'plugins'
    else:
        target = 'all'

    # Build make command — always parallelize
    cmd = ['make', target, f'-j{os.cpu_count() or 1}']

    # Execute build
    result = subprocess.run(
        cmd,
        capture_output=not args.verbose,
        text=True
    )

    if result.returncode != 0:
        print("\n✗ Build failed")
        if not args.verbose and result.stderr:
            print("\nError output:")
            print(result.stderr)
            print("\nRun with --verbose to see full output")
        return 1

    print("✓ Build complete")

    # Show summary
    print("\n" + "=" * 80)
    print("Build Summary")
    print("=" * 80)

    if not args.kernels_only:
        print("  ✓ Harness built")
        print("  ✓ Kernel plugins built")
        print("  ✓ Tests built")
    else:
        print("  ✓ Kernel plugins built")

    print("\nRun 'cortex list' to see available kernels")
    print("=" * 80)

    return 0
