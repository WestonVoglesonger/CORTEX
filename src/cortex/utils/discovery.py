"""Kernel discovery and registry scanning"""
import yaml
from pathlib import Path
from typing import List, Dict, Optional

def discover_kernels() -> List[Dict]:
    """Discover all available kernels with their metadata"""
    kernels = []
    kernels_dir = Path('kernels')

    if not kernels_dir.exists():
        return kernels

    # Scan version directories
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

            # Check if kernel has implementation
            c_impl = (kernel_dir / f"{kernel_name}.c").exists()
            if not c_impl:
                continue  # Skip kernels without implementation

            # Check if built
            lib_name = f"lib{kernel_name}"
            dylib_path = kernel_dir / f"{lib_name}.dylib"
            so_path = kernel_dir / f"{lib_name}.so"
            built = dylib_path.exists() or so_path.exists()

            # Load spec for version info
            spec_path = kernel_dir / "spec.yaml"
            spec_version = "1.0.0"
            if spec_path.exists():
                try:
                    with open(spec_path, 'r') as f:
                        spec = yaml.safe_load(f)
                        if 'kernel' in spec and 'version' in spec['kernel']:
                            spec_version = spec['kernel']['version']
                except:
                    pass

            kernels.append({
                'name': kernel_name,
                'display_name': f"{kernel_name}_v{version[1]}" if version != "v1" else kernel_name,
                'version': version,
                'dtype': dtype,
                'spec_uri': str(kernel_dir),
                'spec_version': spec_version,
                'built': built
            })

    return kernels

def find_kernel(kernel_name: str) -> Optional[Dict]:
    """Find a specific kernel by name (handles v1/v2 variants)"""
    kernels = discover_kernels()

    # Exact match first
    for k in kernels:
        if k['display_name'] == kernel_name or k['name'] == kernel_name:
            return k

    # Try matching just the base name (prefer v1)
    for k in kernels:
        if k['name'] == kernel_name and k['version'] == 'v1':
            return k

    # Any version match
    for k in kernels:
        if k['name'] == kernel_name:
            return k

    return None
