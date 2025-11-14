"""Configuration generation and management"""
import yaml
from pathlib import Path
from typing import Dict, Optional, List
from .discovery import discover_kernels, find_kernel

def load_base_config(config_path: str = "primitives/configs/cortex.yaml") -> Dict:
    """Load base configuration template"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def generate_config(
    kernel_name: str,
    output_path: str,
    output_dir: Optional[str] = None,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    base_config_path: str = "primitives/configs/cortex.yaml"
) -> bool:
    """
    Generate a configuration file for a specific kernel

    Args:
        kernel_name: Name of kernel to configure
        output_path: Where to write the config file
        output_dir: Override output directory for results (kernel-specific)
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

    # Override output directory if provided
    if output_dir is not None:
        config['output']['directory'] = output_dir

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
    warmup: Optional[int] = None,
    base_config_path: str = "primitives/configs/cortex.yaml"
) -> List[tuple]:
    """
    Generate configs for kernels based on base config

    Behavior:
    - If base config has explicit plugins: section -> use those kernels only
    - If no plugins: section (auto-detect mode) -> use all built kernels

    This matches the C harness auto-detection behavior for consistency.

    Returns:
        List of (kernel_name, config_path) tuples
    """
    # Load base config to check for explicit plugins list
    try:
        base_config = load_base_config(base_config_path)
    except Exception as e:
        print(f"Error loading base config: {e}")
        return []

    # Check if plugins key exists in config
    # Three cases:
    # 1. No 'plugins' key → auto-detect all built kernels
    # 2. 'plugins: []' → explicit empty list, run zero kernels
    # 3. 'plugins: [...]' → explicit list, run only those kernels

    if 'plugins' in base_config:
        explicit_plugins = base_config['plugins']

        if not explicit_plugins:
            # Empty list - user explicitly wants zero kernels
            print(f"Empty plugins list in {base_config_path}, running zero kernels")
            return []

        # Explicit mode: use only specified kernels
        kernel_names = [p['name'] for p in explicit_plugins if p.get('status') == 'ready']
        print(f"Using explicit plugins list from {base_config_path}: {kernel_names}")

        # Verify each kernel is built
        all_kernels = discover_kernels()
        kernel_map = {k['display_name']: k for k in all_kernels}

        kernels_to_run = []
        for name in kernel_names:
            if name in kernel_map:
                if kernel_map[name]['built']:
                    kernels_to_run.append(kernel_map[name])
                else:
                    print(f"Warning: Kernel '{name}' in config but not built, skipping")
            else:
                print(f"Warning: Kernel '{name}' in config but not found, skipping")
    else:
        # Auto-detect mode: discover all built kernels
        print(f"No plugins section in {base_config_path}, auto-detecting all built kernels")
        kernels = discover_kernels()
        kernels_to_run = [k for k in kernels if k['built']]

    if not kernels_to_run:
        print("No kernels available to benchmark")
        return []

    configs = []
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for kernel in kernels_to_run:
        config_path = Path(output_dir) / f"{kernel['display_name']}.yaml"

        if generate_config(
            kernel['display_name'],
            str(config_path),
            duration=duration,
            repeats=repeats,
            warmup=warmup,
            base_config_path=base_config_path
        ):
            configs.append((kernel['display_name'], str(config_path)))

    return configs
