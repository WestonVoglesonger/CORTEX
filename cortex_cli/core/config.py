"""Configuration generation and management"""
import yaml
from pathlib import Path
from typing import Dict, Optional, List

def load_base_config(config_path: str = "configs/cortex.yaml") -> Dict:
    """Load base configuration template"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

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

def generate_config(
    kernel_name: str,
    output_path: str,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    base_config_path: str = "configs/cortex.yaml"
) -> bool:
    """
    Generate a configuration file for a specific kernel

    Args:
        kernel_name: Name of kernel to configure
        output_path: Where to write the config file
        duration: Override benchmark duration (seconds)
        repeats: Override number of repeats
        warmup: Override warmup duration (seconds)
        base_config_path: Path to base config template

    Returns:
        True if successful, False otherwise
    """
    # Find kernel
    kernel = find_kernel(kernel_name)
    if not kernel:
        print(f"Error: Kernel '{kernel_name}' not found")
        return False

    if not kernel['built']:
        print(f"Warning: Kernel '{kernel_name}' is not built")
        print(f"Run 'cortex build' first")
        return False

    # Load base config
    try:
        config = load_base_config(base_config_path)
    except Exception as e:
        print(f"Error loading base config: {e}")
        return False

    # Override benchmark parameters if provided
    if duration is not None:
        config['benchmark']['parameters']['duration_seconds'] = duration
    if repeats is not None:
        config['benchmark']['parameters']['repeats'] = repeats
    if warmup is not None:
        config['benchmark']['parameters']['warmup_seconds'] = warmup

    # Configure single plugin
    config['plugins'] = [
        {
            'name': kernel['display_name'],
            'status': 'ready',
            'spec_uri': kernel['spec_uri'],
            'spec_version': kernel['spec_version']
        }
    ]

    # Write config
    try:
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return True
    except Exception as e:
        print(f"Error writing config: {e}")
        return False

def generate_batch_configs(
    output_dir: str,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None
) -> List[tuple]:
    """
    Generate configs for all available kernels

    Returns:
        List of (kernel_name, config_path) tuples
    """
    kernels = discover_kernels()
    built_kernels = [k for k in kernels if k['built']]

    if not built_kernels:
        print("No built kernels found")
        return []

    configs = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for kernel in built_kernels:
        config_path = Path(output_dir) / f"{kernel['display_name']}.yaml"

        if generate_config(
            kernel['display_name'],
            str(config_path),
            duration=duration,
            repeats=repeats,
            warmup=warmup
        ):
            configs.append((kernel['display_name'], str(config_path)))

    return configs
