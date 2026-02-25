"""Configuration management with temp YAML generation"""
import yaml
import tempfile
from typing import Dict, List, Optional, Union
from pathlib import Path

def load_base_config(config_path: str = "primitives/configs/cortex.yaml") -> Dict:
    """Load base configuration template"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def _discover_kernel(name: str) -> str:
    """Find a kernel's spec_uri on disk.

    If *name* already contains '@' (e.g. 'notch_iir@f32') it is treated as
    fully qualified and matched exactly.  Otherwise we glob with '@*' to
    discover the first available format variant.

    Returns:
        Path to the kernel directory (e.g. 'primitives/kernels/v1/notch_iir@f32')

    Raises:
        ValueError: If the kernel cannot be found.
    """
    import glob as globmod

    if '@' in name:
        # Fully qualified — match exact directory
        candidates = globmod.glob(f'primitives/kernels/v*/{name}')
    else:
        # Short name — discover any format variant
        candidates = globmod.glob(f'primitives/kernels/v*/{name}@*')

    if not candidates:
        raise ValueError(f"Kernel '{name}' not found in primitives/kernels/")
    return candidates[0]


def generate_temp_config(
    base_config_path: str = "primitives/configs/cortex.yaml",
    kernel_filter: Optional[Union[str, List[str]]] = None,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    calibration_state: Optional[str] = None
) -> str:
    """Generate temporary YAML config with runtime overrides.

    Args:
        base_config_path: Path to base config file
        kernel_filter: Filter to specific kernel(s). A string selects one kernel;
            a list of strings builds a plugins section with all listed kernels
            (used for pipeline mode).
        duration: Override benchmark duration (seconds)
        repeats: Override number of repeats
        warmup: Override warmup duration (seconds)
        calibration_state: Path to .cortex_state file for trainable kernels

    Returns:
        Path to generated temp config file (caller must clean up)
    """
    # Load base config
    config = load_base_config(base_config_path)

    # Apply benchmark parameter overrides
    if duration is not None:
        if 'benchmark' not in config:
            config['benchmark'] = {'parameters': {}}
        if 'parameters' not in config['benchmark']:
            config['benchmark']['parameters'] = {}
        config['benchmark']['parameters']['duration_seconds'] = duration

    if repeats is not None:
        if 'benchmark' not in config:
            config['benchmark'] = {'parameters': {}}
        if 'parameters' not in config['benchmark']:
            config['benchmark']['parameters'] = {}
        config['benchmark']['parameters']['repeats'] = repeats

    if warmup is not None:
        if 'benchmark' not in config:
            config['benchmark'] = {'parameters': {}}
        if 'parameters' not in config['benchmark']:
            config['benchmark']['parameters'] = {}
        config['benchmark']['parameters']['warmup_seconds'] = warmup

    # Apply kernel filter (single kernel or list of kernels for pipeline)
    if kernel_filter is not None:
        if isinstance(kernel_filter, list):
            # Pipeline mode: build plugins list with all listed kernels (order preserved)
            plugins = []
            for kname in kernel_filter:
                # Check base config first
                existing = [p for p in config.get('plugins', []) if p.get('name') == kname]
                if existing:
                    plugins.append(existing[0])
                else:
                    kernel_path = _discover_kernel(kname)
                    plugins.append({
                        'name': kname,
                        'status': 'ready',
                        'spec_uri': kernel_path,
                    })
            config['plugins'] = plugins
        else:
            # Single kernel mode (existing behavior)
            if 'plugins' not in config or not config['plugins']:
                config['plugins'] = []

            # Filter to specified kernel only
            filtered_plugins = [p for p in config['plugins'] if p.get('name') == kernel_filter]

            if filtered_plugins:
                # Kernel exists in config - use it
                config['plugins'] = filtered_plugins
            else:
                kernel_path = _discover_kernel(kernel_filter)
                config['plugins'] = [{
                    'name': kernel_filter,
                    'status': 'ready',
                    'spec_uri': kernel_path
                }]

    # Apply calibration state (must be done AFTER kernel filtering)
    if calibration_state is not None:
        # Resolve to absolute path for harness
        state_path = str(Path(calibration_state).resolve())

        # Apply to all plugins in explicit list
        if 'plugins' in config:
            for plugin in config.get('plugins', []):
                plugin['calibration_state'] = state_path

        # NOTE: For auto-detect mode (empty plugins list), calibration_state cannot be
        # applied globally. User must specify --kernel to use trainable kernels with state.
        # This is by design: auto-detect runs ALL kernels, but only specific kernels
        # should use specific calibration states.

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.yaml',
        prefix='cortex_run_',
        delete=False
    ) as f:
        yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        temp_path = f.name

    return temp_path
