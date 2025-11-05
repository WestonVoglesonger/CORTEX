"""List available kernels command"""
import os
import sys
from pathlib import Path

def setup_parser(parser):
    """Setup argument parser for list command"""
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show detailed information'
    )

def discover_kernels():
    """Discover all available kernels in kernels/ directory"""
    kernels = []
    kernels_dir = Path('kernels')

    if not kernels_dir.exists():
        return kernels

    # Scan v1, v2, etc directories
    for version_dir in sorted(kernels_dir.iterdir()):
        if not version_dir.is_dir() or not version_dir.name.startswith('v'):
            continue

        version = version_dir.name

        # Scan kernel@dtype directories
        for kernel_dir in sorted(version_dir.iterdir()):
            if not kernel_dir.is_dir() or '@' not in kernel_dir.name:
                continue

            name_dtype = kernel_dir.name.split('@')
            if len(name_dtype) != 2:
                continue

            kernel_name, dtype = name_dtype

            # Check if kernel is built (look for .dylib or .so)
            lib_name = f"lib{kernel_name}"
            dylib_path = kernel_dir / f"{lib_name}.dylib"
            so_path = kernel_dir / f"{lib_name}.so"
            built = dylib_path.exists() or so_path.exists()

            # Check if C implementation exists
            c_impl = (kernel_dir / f"{kernel_name}.c").exists()

            # Check if spec exists
            spec = (kernel_dir / "spec.yaml").exists()

            # Check if oracle exists
            oracle = (kernel_dir / "oracle.py").exists()

            kernels.append({
                'name': kernel_name,
                'version': version,
                'dtype': dtype,
                'path': str(kernel_dir),
                'built': built,
                'c_impl': c_impl,
                'spec': spec,
                'oracle': oracle
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
