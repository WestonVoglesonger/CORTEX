"""Experiment execution"""
import subprocess
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime

def run_harness(config_path: str, verbose: bool = False) -> Optional[str]:
    """
    Run the CORTEX harness with a given config

    Args:
        config_path: Path to configuration file
        verbose: Show harness output

    Returns:
        Results directory path if successful, None otherwise
    """
    harness_binary = Path('src/harness/cortex')

    if not harness_binary.exists():
        print(f"Error: Harness binary not found at {harness_binary}")
        print("Run 'cortex build' first")
        return None

    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}")
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

        # Try to find the most recent results directory
        # The harness creates results/<run_id>/ directories
        results_dir = Path('results')
        if results_dir.exists():
            # Find most recent non-batch, non-analysis directory
            subdirs = [d for d in results_dir.iterdir()
                      if d.is_dir()
                      and not d.name.startswith('batch_')
                      and d.name != 'analysis']

            if subdirs:
                latest = max(subdirs, key=lambda d: d.stat().st_mtime)
                return str(latest)

        return "results"  # Fallback

    except Exception as e:
        print(f"Error running harness: {e}")
        return None

def run_single_kernel(
    kernel_name: str,
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    verbose: bool = False
) -> Optional[str]:
    """
    Run benchmark for a single kernel

    Args:
        kernel_name: Name of kernel to benchmark
        duration: Override duration (seconds)
        repeats: Override number of repeats
        warmup: Override warmup duration (seconds)
        verbose: Show verbose output

    Returns:
        Results directory path if successful, None otherwise
    """
    from cortex_cli.core.config import generate_config

    # Generate config
    config_dir = Path('configs/generated')
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"{kernel_name}.yaml"

    print(f"Generating config for {kernel_name}...")

    if not generate_config(
        kernel_name,
        str(config_path),
        duration=duration,
        repeats=repeats,
        warmup=warmup
    ):
        return None

    print(f"Running benchmark for {kernel_name}...")

    # Run harness
    results_dir = run_harness(str(config_path), verbose=verbose)

    if results_dir:
        print(f"✓ Benchmark complete: {results_dir}")

    return results_dir

def run_all_kernels(
    duration: Optional[int] = None,
    repeats: Optional[int] = None,
    warmup: Optional[int] = None,
    verbose: bool = False
) -> Optional[str]:
    """
    Run benchmarks for all available kernels

    Args:
        duration: Override duration (seconds)
        repeats: Override number of repeats
        warmup: Override warmup duration (seconds)
        verbose: Show verbose output

    Returns:
        Batch results directory path if successful, None otherwise
    """
    from cortex_cli.core.config import generate_batch_configs

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

    # Create batch results directory
    timestamp = int(time.time())
    batch_dir = Path(f'results/batch_{timestamp}')
    batch_dir.mkdir(parents=True, exist_ok=True)

    print(f"Batch results will be saved to: {batch_dir}")
    print()

    # Run each kernel
    results = []
    for i, (kernel_name, config_path) in enumerate(configs, 1):
        print("=" * 80)
        print(f"[{i}/{len(configs)}] Running {kernel_name}")
        print("=" * 80)

        results_dir = run_harness(config_path, verbose=verbose)

        if results_dir:
            # Collect results into batch directory
            import shutil
            results_path = Path('results')

            # Find telemetry files matching this kernel
            # Pattern: <timestamp>_<kernel>_telemetry.* (CSV or NDJSON)
            csv_pattern = f"*_{kernel_name}_telemetry.csv"
            ndjson_pattern = f"*_{kernel_name}_telemetry.ndjson"

            csv_files = list(results_path.glob(csv_pattern))
            ndjson_files = list(results_path.glob(ndjson_pattern))

            if csv_files or ndjson_files:
                # Get most recent files (by modification time)
                all_files = csv_files + ndjson_files
                if all_files:
                    latest_file = max(all_files, key=lambda f: f.stat().st_mtime)

                    # Extract run_id from filename
                    # e.g., "1762315905289_goertzel_telemetry.csv" -> "1762315905289"
                    run_id = latest_file.stem.split('_')[0]

                    # Create kernel subdirectory in batch
                    kernel_batch_dir = batch_dir / f"{kernel_name}_run"
                    kernel_batch_dir.mkdir(parents=True, exist_ok=True)

                    # Copy all telemetry files with this run_id and kernel_name
                    for pattern in [csv_pattern, ndjson_pattern]:
                        for file in results_path.glob(pattern):
                            if file.stem.startswith(run_id):
                                shutil.copy2(file, kernel_batch_dir / file.name)

                    # Copy HTML report directory if exists (skip duplicate telemetry files)
                    run_dir = results_path / run_id
                    if run_dir.exists() and run_dir.is_dir():
                        for item in run_dir.iterdir():
                            # Skip telemetry files to avoid duplicates (already collected above)
                            if '_telemetry.' in item.name:
                                continue

                            dest = kernel_batch_dir / item.name
                            if item.is_file():
                                shutil.copy2(item, dest)
                            elif item.is_dir():
                                shutil.copytree(item, dest, dirs_exist_ok=True)

            results.append((kernel_name, results_dir))
            print(f"✓ {kernel_name} complete")
        else:
            print(f"✗ {kernel_name} failed")

        print()

    # Summary
    print("=" * 80)
    print("Batch Benchmark Summary")
    print("=" * 80)
    print(f"Completed: {len(results)}/{len(configs)} kernels")
    print(f"Results directory: {batch_dir}")
    print("=" * 80)

    return str(batch_dir) if results else None
