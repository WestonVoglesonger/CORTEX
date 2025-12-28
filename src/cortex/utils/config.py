"""Configuration management with temp YAML generation"""
import yaml
import tempfile
from typing import Dict, Optional
from pathlib import Path

def load_base_config(config_path: str = "primitives/configs/cortex.yaml") -> Dict:
    """Load base configuration template"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def generate_temp_config(
    base_config_path: str = "primitives/configs/cortex.yaml",
    kernel_filter: Optional[str] = None,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    calibration_state: Optional[str] = None
) -> str:
    """Generate temporary YAML config with runtime overrides.

    Args:
        base_config_path: Path to base config file
        kernel_filter: Filter to specific kernel (e.g., "ica", "goertzel")
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

    # Apply kernel filter (for single-kernel mode)
    if kernel_filter is not None:
        # Replace plugins section with single kernel entry
        if 'plugins' not in config or not config['plugins']:
            config['plugins'] = []

        # Filter to specified kernel only
        filtered_plugins = [p for p in config['plugins'] if p.get('name') == kernel_filter]

        if filtered_plugins:
            # Kernel exists in config - use it
            config['plugins'] = filtered_plugins
        else:
            # Kernel not in config - discover it from filesystem
            # Try common locations (v1 is most common)
            import glob
            kernel_candidates = glob.glob(f'primitives/kernels/v*/{kernel_filter}@*')

            if not kernel_candidates:
                raise ValueError(f"Kernel '{kernel_filter}' not found in primitives/kernels/")

            # Use first match (typically v1)
            kernel_path = kernel_candidates[0]

            config['plugins'] = [{
                'name': kernel_filter,
                'status': 'ready',
                'spec_uri': kernel_path
            }]

    # Apply calibration state (must be done AFTER kernel filtering)
    if calibration_state is not None:
        # Resolve to absolute path for harness
        state_path = str(Path(calibration_state).resolve())

        # Apply to all plugins (usually just one in single-kernel mode)
        if 'plugins' in config and config['plugins']:
            for plugin in config['plugins']:
                plugin['calibration_state'] = state_path

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
