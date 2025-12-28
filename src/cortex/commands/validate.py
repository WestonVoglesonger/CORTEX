"""Validate kernels against oracles command"""
import subprocess
import sys
from pathlib import Path

def setup_parser(parser):
    """Setup argument parser for validate command"""
    parser.add_argument(
        '--kernel',
        help='Validate specific kernel only'
    )
    parser.add_argument(
        '--calibration-state',
        help='Path to calibration state file (for trainable kernels)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose test output'
    )

def execute(args):
    """Execute validate command"""
    print("=" * 80)
    print("CORTEX Kernel Validation")
    print("=" * 80)

    # Check if test binary exists
    test_binary = Path('tests/test_kernel_accuracy')
    if not test_binary.exists():
        print("\n✗ Test binary not found")
        print("  Run 'cortex build' first")
        return 1

    if args.kernel:
        print(f"\nValidating kernel: {args.kernel}")
        cmd = [str(test_binary), '--kernel', args.kernel, '--windows', '10']
        if args.calibration_state:
            cmd.extend(['--state', args.calibration_state])
        if args.verbose:
            cmd.append('--verbose')
    else:
        print("\nValidating all kernels...")
        cmd = [str(test_binary)]

    # Run validation
    result = subprocess.run(cmd, capture_output=not args.verbose, text=True)

    if result.returncode != 0:
        print("\n✗ Validation failed")
        if not args.verbose and result.stderr:
            print("\nError output:")
            print(result.stderr)
        return 1

    print("\n✓ Validation passed")
    print("=" * 80)

    return 0
