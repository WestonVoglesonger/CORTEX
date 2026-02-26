"""Configuration management with temp YAML generation"""
import glob as globmod
import tempfile
from typing import Dict, List, Optional, Union
from pathlib import Path

import yaml

def load_base_config(config_path: str = "primitives/configs/cortex.yaml") -> Dict:
    """Load base configuration template"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def _discover_kernel(name: str) -> str:
    """Find a kernel's spec_uri (dtype directory) on disk.

    Layout: primitives/kernels/v{N}/{kernel_name}/{dtype}/
    If *name* already contains '/' (e.g. 'notch_iir/f32') it is treated as
    fully qualified.  Otherwise we discover the first available dtype variant.

    Returns:
        Path to the dtype directory (e.g. 'primitives/kernels/v1/notch_iir/f32')

    Raises:
        ValueError: If the kernel cannot be found.
    """
    if '/' in name:
        # Fully qualified — match exact directory
        candidates = globmod.glob(f'primitives/kernels/v*/{name}')
    else:
        # Short name — discover any dtype variant
        candidates = globmod.glob(f'primitives/kernels/v*/{name}/*')
        # Filter to only directories that contain a .c file (actual dtype dirs)
        candidates = [c for c in candidates
                      if Path(c).is_dir() and
                      any(Path(c).glob('*.c'))]

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
    if not isinstance(config, dict):
        raise ValueError(f"Config file {base_config_path!r} is empty or not a YAML mapping")

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
        # Normalize to list so both single-kernel and pipeline paths share logic
        kernel_names = kernel_filter if isinstance(kernel_filter, list) else [kernel_filter]
        base_plugins = config.get('plugins', [])

        plugins = []
        for kname in kernel_names:
            existing = [p for p in base_plugins if p.get('name') == kname]
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

    # Strip keys the C harness doesn't understand (e.g. pipeline-mode config)
    config.pop('pipelines', None)

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
