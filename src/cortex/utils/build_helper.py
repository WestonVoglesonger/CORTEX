"""Build helper utilities for incremental builds"""
import subprocess
from pathlib import Path
from typing import List, Dict, Optional
import os


def needs_rebuild(kernel_spec_uri: str) -> bool:
    """
    Check if a kernel needs rebuilding based on source/binary timestamps.

    Args:
        kernel_spec_uri: Kernel spec URI (e.g., "primitives/kernels/v1/goertzel@f32")

    Returns:
        True if kernel needs rebuilding, False if up-to-date
    """
    kernel_dir = Path(kernel_spec_uri)

    if not kernel_dir.exists():
        return False  # Kernel doesn't exist, can't build

    # Extract kernel name from directory (e.g., "goertzel@f32" -> "goertzel")
    dir_name = kernel_dir.name
    kernel_name = dir_name.split('@')[0]

    # Check for source file
    source_file = kernel_dir / f"{kernel_name}.c"
    if not source_file.exists():
        return False  # No source, can't build

    # Check for shared library (.dylib on macOS, .so on Linux)
    lib_dylib = kernel_dir / f"lib{kernel_name}.dylib"
    lib_so = kernel_dir / f"lib{kernel_name}.so"

    # Find which library exists
    lib_file = None
    if lib_dylib.exists():
        lib_file = lib_dylib
    elif lib_so.exists():
        lib_file = lib_so

    # If no binary exists, need to rebuild
    if lib_file is None:
        return True

    # Compare timestamps: rebuild if source is newer than binary
    source_mtime = source_file.stat().st_mtime
    lib_mtime = lib_file.stat().st_mtime

    return source_mtime > lib_mtime


def check_harness_needs_rebuild() -> bool:
    """
    Check if harness binary needs rebuilding.

    Returns:
        True if harness needs rebuilding, False if up-to-date
    """
    harness_binary = Path("src/engine/harness/cortex")
    harness_src_dir = Path("src/engine/harness")

    # If binary doesn't exist, need to build
    if not harness_binary.exists():
        return True

    # Get binary timestamp
    binary_mtime = harness_binary.stat().st_mtime

    # Check if any source files are newer
    for src_file in harness_src_dir.rglob("*.c"):
        if src_file.stat().st_mtime > binary_mtime:
            return True

    for header_file in harness_src_dir.rglob("*.h"):
        if header_file.stat().st_mtime > binary_mtime:
            return True

    # Binary is up-to-date
    return False


def check_adapter_needs_rebuild(adapter_path: str = "primitives/adapters/v1/native") -> bool:
    """
    Check if adapter binary needs rebuilding.

    Args:
        adapter_path: Path to adapter directory

    Returns:
        True if adapter needs rebuilding, False if up-to-date
    """
    adapter_dir = Path(adapter_path)
    adapter_binary = adapter_dir / "cortex_adapter_native"

    # If binary doesn't exist, need to build
    if not adapter_binary.exists():
        return True

    # Get binary timestamp
    binary_mtime = adapter_binary.stat().st_mtime

    # Check adapter source files
    for src_file in adapter_dir.rglob("*.c"):
        if src_file.stat().st_mtime > binary_mtime:
            return True

    # Check SDK adapter library sources (adapter depends on these)
    sdk_adapter_dir = Path("sdk/adapter/lib")
    if sdk_adapter_dir.exists():
        for src_file in sdk_adapter_dir.rglob("*.c"):
            if src_file.stat().st_mtime > binary_mtime:
                return True

        for header_file in sdk_adapter_dir.rglob("*.h"):
            if header_file.stat().st_mtime > binary_mtime:
                return True

    # Binary is up-to-date
    return False


def build_specific_kernels(kernel_spec_uris: List[str], verbose: bool = False) -> bool:
    """
    Build only specific kernels.

    Args:
        kernel_spec_uris: List of kernel spec URIs to build
        verbose: Show build output

    Returns:
        True if all builds succeeded, False otherwise
    """
    if not kernel_spec_uris:
        return True  # Nothing to build

    print(f"Building {len(kernel_spec_uris)} kernel(s)...")

    for spec_uri in kernel_spec_uris:
        kernel_dir = Path(spec_uri)
        kernel_name = kernel_dir.name

        if not kernel_dir.exists():
            print(f"  ✗ {kernel_name}: directory not found")
            return False

        if not (kernel_dir / "Makefile").exists():
            print(f"  ✗ {kernel_name}: no Makefile")
            return False

        print(f"  Building {kernel_name}...")

        result = subprocess.run(
            ['make'],
            cwd=str(kernel_dir),
            capture_output=not verbose,
            text=True
        )

        if result.returncode != 0:
            print(f"  ✗ {kernel_name}: build failed")
            if not verbose and result.stderr:
                print(f"     {result.stderr}")
            return False

        print(f"  ✓ {kernel_name}")

    return True


def smart_build(
    kernel_spec_uris: List[str],
    force_rebuild: bool = False,
    verbose: bool = False
) -> Dict[str, any]:
    """
    Smart incremental build: only rebuild what's necessary.

    Args:
        kernel_spec_uris: List of kernel spec URIs to check/build
        force_rebuild: Force rebuild even if up-to-date
        verbose: Show verbose output

    Returns:
        Dict with build results:
        {
            'success': bool,
            'harness_rebuilt': bool,
            'adapter_rebuilt': bool,
            'kernels_rebuilt': List[str],
            'kernels_skipped': List[str],
            'errors': List[str]
        }
    """
    results = {
        'success': True,
        'harness_rebuilt': False,
        'adapter_rebuilt': False,
        'kernels_rebuilt': [],
        'kernels_skipped': [],
        'errors': []
    }

    # Check harness
    if force_rebuild or check_harness_needs_rebuild():
        print("Harness needs rebuilding...")
        result = subprocess.run(
            ['make', 'harness'],
            capture_output=not verbose,
            text=True
        )

        if result.returncode != 0:
            results['success'] = False
            results['errors'].append('harness build failed')
            return results

        results['harness_rebuilt'] = True
        print("✓ Harness rebuilt")
    else:
        print("✓ Harness up-to-date")

    # Check adapter
    if force_rebuild or check_adapter_needs_rebuild():
        print("Adapter needs rebuilding...")
        adapter_dir = Path("primitives/adapters/v1/native")

        # First build SDK adapter libraries
        result = subprocess.run(
            ['make'],
            cwd='sdk/adapter/lib',
            capture_output=not verbose,
            text=True
        )

        if result.returncode != 0:
            results['success'] = False
            results['errors'].append('SDK adapter library build failed')
            return results

        # Then build adapter binary
        result = subprocess.run(
            ['make'],
            cwd=str(adapter_dir),
            capture_output=not verbose,
            text=True
        )

        if result.returncode != 0:
            results['success'] = False
            results['errors'].append('adapter build failed')
            return results

        results['adapter_rebuilt'] = True
        print("✓ Adapter rebuilt")
    else:
        print("✓ Adapter up-to-date")

    # Check each kernel
    kernels_to_build = []

    for spec_uri in kernel_spec_uris:
        kernel_name = Path(spec_uri).name

        if force_rebuild or needs_rebuild(spec_uri):
            kernels_to_build.append(spec_uri)
        else:
            results['kernels_skipped'].append(kernel_name)
            if verbose:
                print(f"  ✓ {kernel_name} up-to-date")

    # Build needed kernels
    if kernels_to_build:
        if not build_specific_kernels(kernels_to_build, verbose):
            results['success'] = False
            results['errors'].append('kernel build failed')
            return results

        results['kernels_rebuilt'] = [Path(uri).name for uri in kernels_to_build]
    else:
        print("✓ All kernels up-to-date")

    return results
