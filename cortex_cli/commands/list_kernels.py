"""List available kernels command"""
import os
import sys
from pathlib import Path
from cortex_cli.core.discovery import discover_kernels as discover_kernels_base

def setup_parser(parser):
    """Setup argument parser for list command"""
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed information'
    )

def discover_kernels():
    """Discover all available kernels with additional metadata for list command"""
    # Use shared discovery function
    base_kernels = discover_kernels_base()

    # Add extra metadata for list command
    kernels = []
    for k in base_kernels:
        kernel_dir = Path(k['spec_uri'])
        kernels.append({
            'name': k['name'],
            'version': k['version'],
            'dtype': k['dtype'],
            'path': str(kernel_dir),
            'built': k['built'],
            'c_impl': (kernel_dir / f"{k['name']}.c").exists(),
            'spec': (kernel_dir / "spec.yaml").exists(),
            'oracle': (kernel_dir / "oracle.py").exists()
        })

    return kernels

def execute(args):
    """Execute list command"""
    kernels = discover_kernels()

    if not kernels:
        print("No kernels found in kernels/ directory")
        return 1

    print(f"\nAvailable Kernels ({len(kernels)} found):")
    print("=" * 80)

    if args.verbose:
        # Detailed view
        for kernel in kernels:
            status = "BUILT" if kernel['built'] else "NOT BUILT"
            print(f"\n{kernel['name']} ({kernel['version']}/{kernel['dtype']}) - {status}")
            print(f"  Path: {kernel['path']}")
            print(f"  Implementation: {'✓' if kernel['c_impl'] else '✗'}")
            print(f"  Spec: {'✓' if kernel['spec'] else '✗'}")
            print(f"  Oracle: {'✓' if kernel['oracle'] else '✗'}")
    else:
        # Table view
        print(f"{'Kernel':<20} {'Version':<10} {'DType':<10} {'Status':<15}")
        print("-" * 80)

        for kernel in kernels:
            status = "✓ Built" if kernel['built'] else "✗ Not built"
            if not kernel['c_impl']:
                status = "⚠ No impl"

            print(f"{kernel['name']:<20} {kernel['version']:<10} {kernel['dtype']:<10} {status:<15}")

    print()

    # Summary
    built_count = sum(1 for k in kernels if k['built'])
    impl_count = sum(1 for k in kernels if k['c_impl'])
    print(f"Summary: {impl_count}/{len(kernels)} implemented, {built_count}/{len(kernels)} built")
    print()

    return 0
