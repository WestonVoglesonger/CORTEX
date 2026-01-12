"""
CORTEX synthetic dataset generator integration.

Provides complete workflow for detecting, executing, and integrating
generator-based datasets into the CLI execution pipeline.
"""

import os
import sys
import yaml
import tempfile
import hashlib
import importlib.util
from datetime import datetime
from typing import Optional, Tuple, Dict, List, Any
from pathlib import Path
import numpy as np


def is_generator_dataset(dataset_path: str) -> bool:
    """
    Check if dataset is generator-based.

    Detection logic:
    1. Primary: Read spec.yaml, check dataset.type == "generator"
    2. Fallback: Check if generator.py exists (convenience)

    Args:
        dataset_path: Path to dataset primitive directory

    Returns:
        True if dataset is generator-based, False otherwise
    """
    if not os.path.isdir(dataset_path):
        return False

    # Primary: Explicit type declaration in spec.yaml
    spec_path = os.path.join(dataset_path, "spec.yaml")
    if os.path.exists(spec_path):
        try:
            with open(spec_path) as f:
                spec = yaml.safe_load(f)

            # Handle dataset: null or empty spec by using or {} to coalesce None
            dataset_section = spec.get('dataset') if spec else None
            dataset_type = dataset_section.get('type') if dataset_section else None

            if dataset_type == 'generator':
                # Verify generator.py exists if type claims generator
                gen_script = os.path.join(dataset_path, "generator.py")
                if not os.path.exists(gen_script):
                    raise ValueError(
                        f"Dataset claims type='generator' but {gen_script} missing"
                    )
                return True
            elif dataset_type is not None:
                # Explicit type but not generator (e.g., type='static')
                return False
        except (FileNotFoundError, yaml.YAMLError, KeyError, TypeError, AttributeError) as e:
            # Catch file/parsing errors including AttributeError from malformed YAML
            print(f"[cortex] Warning: Failed to parse {spec_path}: {e}")

    # Fallback: Check for generator.py existence
    return os.path.exists(os.path.join(dataset_path, "generator.py"))


def execute_generator(generator_path: str,
                      channels: int,
                      sample_rate_hz: int,
                      params: Dict[str, Any]) -> Tuple[str, Dict]:
    """
    Execute generator and return temp file path + manifest.

    Args:
        generator_path: Path to generator primitive directory
                       (e.g., "primitives/datasets/v1/synthetic")
        channels: Number of channels (from dataset.channels)
        sample_rate_hz: Sampling rate (from dataset.sample_rate_hz)
        params: Generation parameters (from dataset.params)

    Returns:
        (temp_file_path, generation_manifest)

    Raises:
        ValueError: If params contains 'channels' (conflict with dataset.channels)
        FileNotFoundError: If generator.py not found
        Exception: If generation fails
    """
    # Coalesce None params to empty dict (handles params: null in YAML)
    if params is None:
        params = {}

    # Validation: Ensure params doesn't override channels
    if 'channels' in params:
        raise ValueError(
            "Configuration error: 'channels' must be specified in "
            "dataset.channels, not dataset.params.channels. "
            "Remove 'channels' from dataset.params."
        )

    # Load generator.py as module
    gen_script = os.path.join(generator_path, "generator.py")
    if not os.path.exists(gen_script):
        raise FileNotFoundError(
            f"Generator script not found: {gen_script}. "
            f"Expected generator.py in {generator_path}"
        )

    print(f"[cortex] Loading generator: {gen_script}")

    spec = importlib.util.spec_from_file_location("generator", gen_script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Instantiate generator
    gen = module.SyntheticGenerator()

    # Validate required parameters
    if 'signal_type' not in params:
        raise ValueError("Missing required parameter: 'signal_type'")
    if 'duration_s' not in params:
        raise ValueError("Missing required parameter: 'duration_s'")

    print(f"[cortex] Generating {params['signal_type']} signal...")
    print(f"[cortex] Parameters: channels={channels}, "
          f"sample_rate={sample_rate_hz}Hz, "
          f"duration={params['duration_s']}s")

    # Execute generator
    result = gen.generate(
        signal_type=params['signal_type'],
        channels=channels,
        sample_rate_hz=sample_rate_hz,
        duration_s=params['duration_s'],
        params=params
    )

    # Handle both return types (ndarray or file path)
    if isinstance(result, str):
        # High-channel mode: Generator returned file path
        temp_file_path = result
        print(f"[cortex] Generated file: {temp_file_path}")
        file_size = os.path.getsize(temp_file_path)
        total_samples = int(params['duration_s'] * sample_rate_hz)
    else:
        # Low-channel mode: Generator returned ndarray
        print(f"[cortex] Generated ndarray: shape={result.shape}, "
              f"dtype={result.dtype}")

        # Write to temp file
        param_hash = hashlib.md5(
            str(sorted(params.items())).encode()
        ).hexdigest()[:8]

        temp_file = tempfile.NamedTemporaryFile(
            prefix=f"cortex_gen_{param_hash}_",
            suffix=".float32",
            delete=False
        )

        try:
            result.tofile(temp_file)
            temp_file.close()
            temp_file_path = temp_file.name
            file_size = os.path.getsize(temp_file_path)
            total_samples = result.shape[0]
            print(f"[cortex] Wrote to temp file: {temp_file_path}")
        except Exception:
            # Best-effort cleanup on write failure
            try:
                temp_file.close()
                os.unlink(temp_file.name)
            except OSError:
                pass  # Ignore errors during cleanup
            raise  # Re-raise original exception

    print(f"[cortex] File size: {file_size / 1e6:.1f} MB")

    # Create generation manifest
    manifest = {
        'generator_primitive': os.path.abspath(generator_path),
        'generator_version': 1,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'parameters': params,
        'output': {
            'channels': channels,
            'sample_rate_hz': sample_rate_hz,
            'total_samples': total_samples,
            'duration_s': total_samples / sample_rate_hz,
            'file_size_bytes': file_size,
            'temp_path': temp_file_path
        },
        'reproducibility_note': (
            "To regenerate this exact dataset, run the generator with "
            "the parameters listed above. Same platform guarantees bitwise "
            "identity; cross-platform guarantees statistical equivalence "
            "(FFT library variations <1e-6)."
        )
    }

    return temp_file_path, manifest


def process_config_with_generators(config_path: str,
                                   output_dir: str) -> Tuple[str, Optional[Dict], List[str]]:
    """
    Process config file, detecting and executing generators if needed.

    This is the main integration point for CLI commands. Call this before
    spawning the harness to handle synthetic dataset generation.

    Args:
        config_path: Path to YAML config file
        output_dir: Output directory for results (for manifest)

    Returns:
        Tuple of:
        - Modified config path (temp file if generator was used)
        - Generation manifest dict (or None if no generator)
        - List of temp files to cleanup

    Raises:
        Exception: If generator execution fails
    """
    temp_files = []

    # Load config
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Check if dataset is generator-based
    # Handle config: null or dataset: null by coalescing to empty dict
    dataset_section = config.get('dataset') if config else None
    dataset_path = dataset_section.get('path') if dataset_section else None

    if not dataset_path:
        # No dataset path - return original config unchanged
        return config_path, None, temp_files

    if not is_generator_dataset(dataset_path):
        # Static dataset - return original config unchanged
        return config_path, None, temp_files

    # Generator detected - execute it
    print(f"[cortex] Detected synthetic dataset generator: {dataset_path}")

    channels = dataset_section.get('channels')
    sample_rate_hz = dataset_section.get('sample_rate_hz')
    # Coalesce params: null to empty dict
    params = dataset_section.get('params') or {}

    if not channels:
        raise ValueError("Missing required field: dataset.channels")
    if not sample_rate_hz:
        raise ValueError("Missing required field: dataset.sample_rate_hz")

    # Execute generator
    generated_file_path, manifest = execute_generator(
        generator_path=dataset_path,
        channels=channels,
        sample_rate_hz=sample_rate_hz,
        params=params
    )

    temp_files.append(generated_file_path)

    # Create modified config pointing to generated file
    config['dataset']['path'] = generated_file_path
    # Keep format explicit
    if 'format' not in config['dataset']:
        config['dataset']['format'] = 'float32'

    # Write modified config to temp file
    temp_config = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.yaml',
        delete=False,
        prefix='cortex_config_'
    )
    yaml.dump(config, temp_config)
    temp_config.close()

    temp_files.append(temp_config.name)

    print(f"[cortex] Modified config written: {temp_config.name}")

    return temp_config.name, manifest, temp_files


def save_generation_manifest(manifest: Dict, output_dir: str) -> None:
    """
    Save generation manifest to results directory.

    Args:
        manifest: Generation manifest dict from execute_generator()
        output_dir: Results directory (e.g., results/run-<timestamp>)
    """
    manifest_path = Path(output_dir) / 'dataset' / 'generation_manifest.yaml'
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with open(manifest_path, 'w') as f:
        yaml.dump(manifest, f)

    print(f"[cortex] Generation manifest saved: {manifest_path}")


def cleanup_temp_files(temp_files: List[str]) -> None:
    """
    Clean up temporary files created during generation.

    Args:
        temp_files: List of file paths to remove
    """
    for path in temp_files:
        try:
            if os.path.exists(path):
                os.unlink(path)
                print(f"[cortex] Cleaned up: {path}")
        except Exception as e:
            print(f"[cortex] Warning: Could not remove temp file {path}: {e}")
