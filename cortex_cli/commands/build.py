"""Build command"""
import subprocess
import sys

def setup_parser(parser):
    """Setup argument parser for build command"""
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Clean before building'
    )
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
    parser.add_argument(
        '--jobs', '-j',
        type=int,
        default=None,
        help='Number of parallel jobs (default: auto)'
    )

def execute(args):
    """Execute build command"""
    print("=" * 80)
    print("CORTEX Build")
    print("=" * 80)

    # Clean if requested
    if args.clean:
        print("\n[1/2] Cleaning...")
        result = subprocess.run(['make', 'clean'], capture_output=not args.verbose)
        if result.returncode != 0:
            print("Error: Clean failed")
            return 1
        print("✓ Clean complete")

    # Build
    step_num = 2 if args.clean else 1
    total_steps = 2 if args.clean else 1

    print(f"\n[{step_num}/{total_steps}] Building...")

    if args.kernels_only:
        target = 'plugins'
    else:
        target = 'all'

    # Build make command
    cmd = ['make', target]
    if args.jobs:
        cmd.extend(['-j', str(args.jobs)])

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
