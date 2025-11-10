"""Experiment execution"""
import subprocess
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from cortex_cli.core.paths import (
    create_run_structure,
    create_kernel_directory,
    get_kernel_data_dir,
    get_run_directory
)

def run_harness(config_path: str, run_name: str, verbose: bool = False) -> Optional[str]:
    """
    Run the CORTEX harness with a given config

    Args:
        config_path: Path to configuration file
        run_name: Name of the run for organizing results
        verbose: Show harness output

    Returns:
        Run directory path if successful, None otherwise
    """
    harness_binary = Path('src/harness/cortex')

    if not harness_binary.exists():
        print(f"Error: Harness binary not found at {harness_binary}")
        print("Run 'cortex build' first")
        return None

    if not harness_binary.is_file():
        print(f"Error: {harness_binary} exists but is not a file")
        return None

    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Error: Config file not found: {config_path}")
        return None

    if not config_file.is_file():
        print(f"Error: {config_path} exists but is not a file")
        return None

    # Run harness
    cmd = [str(harness_binary), 'run', config_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=not verbose,
            text=True,
            cwd='.'
        )

        if result.returncode != 0:
            print(f"Error: Harness execution failed (exit code {result.returncode})")
            if not verbose and result.stderr:
                print(result.stderr)
            return None

        # Return the run directory path
        run_dir = get_run_directory(run_name)
        if run_dir.exists():
            return str(run_dir)

        return None  # Run directory not created

    except Exception as e:
        print(f"Error running harness: {e}")
        return None

def run_single_kernel(
    kernel_name: str,
    run_name: str,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    verbose: bool = False
) -> Optional[str]:
    """
    Run benchmark for a single kernel

    Args:
        kernel_name: Name of kernel to benchmark
        run_name: Name of the run for organizing results
        duration: Override duration (seconds)
        repeats: Override number of repeats
        warmup: Override warmup duration (seconds)
        verbose: Show verbose output

    Returns:
        Run directory path if successful, None otherwise
    """
    from cortex_cli.core.config import generate_config

    # Create run directory structure
    create_run_structure(run_name)
    kernel_dir = create_kernel_directory(run_name, kernel_name)

    # Generate config
    config_dir = Path('configs/generated')
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"{kernel_name}.yaml"

    print(f"Generating config for {kernel_name}...")

    if not generate_config(
        kernel_name,
        str(config_path),
        output_dir=str(kernel_dir),
        duration=duration,
        repeats=repeats,
        warmup=warmup
    ):
        return None

    print(f"Running benchmark for {kernel_name}...")

    # Run harness
    results_dir = run_harness(str(config_path), run_name, verbose=verbose)

    if results_dir:
        print(f"✓ Benchmark complete: {results_dir}")

    return results_dir

def run_all_kernels(
    run_name: str,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    verbose: bool = False
) -> Optional[str]:
    """
    Run benchmarks for all available kernels

    Args:
        run_name: Name of the run for organizing results
        duration: Override duration (seconds)
        repeats: Override number of repeats
        warmup: Override warmup duration (seconds)
        verbose: Show verbose output

    Returns:
        Run directory path if successful, None otherwise
    """
    from cortex_cli.core.config import generate_batch_configs

    # Create run directory structure
    create_run_structure(run_name)

    # Generate all configs
    config_dir = Path('configs/generated')
    config_dir.mkdir(parents=True, exist_ok=True)

    print("Generating configs for all kernels...")
    configs = generate_batch_configs(
        str(config_dir),
        duration=duration,
        repeats=repeats,
        warmup=warmup
    )

    if not configs:
        print("No kernels available to benchmark")
        return None

    print(f"Found {len(configs)} kernel(s) to benchmark")

    run_dir = get_run_directory(run_name)
    print(f"Results will be saved to: {run_dir}")
    print()

    # Run each kernel
    results = []
    for i, (kernel_name, config_path) in enumerate(configs, 1):
        print("=" * 80)
        print(f"[{i}/{len(configs)}] Running {kernel_name}")
        print("=" * 80)

        # Create kernel directory
        kernel_dir = create_kernel_directory(run_name, kernel_name)

        # Need to regenerate config with specific output directory
        from cortex_cli.core.config import generate_config
        if not generate_config(
            kernel_name,
            config_path,
            output_dir=str(kernel_dir),
            duration=duration,
            repeats=repeats,
            warmup=warmup
        ):
            print(f"✗ {kernel_name} failed (config generation)")
            print()
            continue

        # Run harness
        result = run_harness(config_path, run_name, verbose=verbose)

        if result:
            results.append((kernel_name, result))
            print(f"✓ {kernel_name} complete")
        else:
            print(f"✗ {kernel_name} failed")

        print()

    # Summary
    print("=" * 80)
    print("Benchmark Summary")
    print("=" * 80)
    print(f"Completed: {len(results)}/{len(configs)} kernels")
    print(f"Results directory: {run_dir}")
    print("=" * 80)

    return str(run_dir) if results else None
