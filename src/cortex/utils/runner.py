"""Experiment execution"""
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from cortex.utils.paths import (
    create_run_structure,
    create_kernel_directory,
    get_kernel_data_dir,
    get_run_directory
)
import shutil
import yaml


def _cleanup_partial_run(run_dir: Path) -> None:
    """
    Clean up a partial run directory on failure.
    
    Args:
        run_dir: Path to the run directory to clean up
    """
    try:
        if run_dir.exists():
            # Check if directory is empty or only contains empty subdirectories
            # Only remove if it's truly empty or contains no meaningful data
            has_data = False
            if (run_dir / "kernel-data").exists():
                kernel_data = run_dir / "kernel-data"
                for kernel_dir in kernel_data.iterdir():
                    if kernel_dir.is_dir():
                        # Check if kernel directory has any files
                        if any(kernel_dir.iterdir()):
                            has_data = True
                            break
            
            # Only remove if no data was written
            if not has_data:
                shutil.rmtree(run_dir)
                print(f"Cleaned up partial run directory: {run_dir}")
    except Exception as e:
        # Don't fail if cleanup fails - just log it
        print(f"Warning: Could not clean up partial run directory {run_dir}: {e}")

def run_harness(config_path: str, run_name: str, verbose: bool = False) -> Optional[str]:
    """
    Run the CORTEX harness with a given config

    Args:
        config_path: Path to configuration file
        run_name: Name of the run for organizing results
        verbose: Show all output including stress-ng and telemetry

    Returns:
        Run directory path if successful, None otherwise
    """
    harness_binary = Path('src/engine/harness/cortex')

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

    # Read config to get benchmark parameters for progress tracking
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        duration = config_data.get('benchmark', {}).get('parameters', {}).get('duration_seconds', 5)
        repeats = config_data.get('benchmark', {}).get('parameters', {}).get('repeats', 3)
        warmup = config_data.get('benchmark', {}).get('parameters', {}).get('warmup_seconds', 5)
        total_time = warmup + (repeats * duration)
    except:
        total_time = None  # Fall back to no progress calculation

    # Run harness with sleep prevention wrapper
    cmd = [str(harness_binary), 'run', config_path]

    # Add platform-specific sleep prevention wrapper
    import platform
    import shutil

    system = platform.system()
    sleep_prevention_tool = None

    if system == 'Darwin':
        # macOS: use caffeinate
        if shutil.which('caffeinate'):
            cmd = ['caffeinate', '-dims'] + cmd
            sleep_prevention_tool = 'caffeinate'
    elif system == 'Linux':
        # Linux: use systemd-inhibit if available
        if shutil.which('systemd-inhibit'):
            cmd = ['systemd-inhibit', '--what=sleep:idle'] + cmd
            sleep_prevention_tool = 'systemd-inhibit'

    # Force unbuffered output for real-time progress updates
    # Use stdbuf if available (Linux/macOS with coreutils)
    if shutil.which('stdbuf'):
        cmd = ['stdbuf', '-o0', '-e0'] + cmd
    # Fallback: set environment variable for unbuffered output
    env = dict(os.environ)
    env['PYTHONUNBUFFERED'] = '1'

    # Notify user of sleep prevention status
    if sleep_prevention_tool:
        print(f"[cortex] Sleep prevention active ({sleep_prevention_tool}) for benchmark consistency")
        print(f"[cortex] Display will stay on during benchmark")
    elif system in ['Darwin', 'Linux']:
        print(f"[cortex] Warning: Sleep prevention tool not found")
        print(f"[cortex] Ensure system won't sleep during benchmarks")

    try:
        # Launch subprocess and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd='.',
            env=env
        )

        # Record start time for progress tracking
        start_time = time.time()

        # Time-based progress loop - updates every 0.5s
        spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

        while process.poll() is None:
            elapsed = time.time() - start_time

            if total_time and total_time > 0:
                if elapsed >= total_time:
                    # Benchmark done, now in post-processing (report generation)
                    spinner_idx = int(elapsed * 2) % len(spinner_chars)
                    print(f"\r[Processing results {spinner_chars[spinner_idx]}]    ", end='', flush=True)
                else:
                    # Normal benchmark progress
                    progress_pct = (elapsed / total_time) * 100
                    remaining = total_time - elapsed
                    progress_bar = _make_progress_bar(progress_pct, 30)
                    print(f"\r{progress_bar} | {remaining:3.0f}s remaining    ", end='', flush=True)
            else:
                # No timing info - just show elapsed time
                print(f"\rRunning... {elapsed:.0f}s elapsed", end='', flush=True)

            # Update every 0.5 seconds
            time.sleep(0.5)

        # Process finished - clear progress line
        print(f"\r{' ' * 60}\r", end='')

        # Wait for process and get return code
        returncode = process.wait()

        # Capture any output for error reporting
        stdout, stderr = process.communicate()

        if returncode != 0:
            print(f"\nError: Harness execution failed (exit code {returncode})")
            if stderr:
                print("Error output:")
                print(stderr)
            return None

        # Return the run directory path
        run_dir = get_run_directory(run_name)
        if run_dir.exists():
            return str(run_dir)

        return None  # Run directory not created

    except Exception as e:
        print(f"Error running harness: {e}")
        # Note: Cleanup is handled by the calling function (run_single_kernel or run_all_kernels)
        return None

def _make_progress_bar(percent: float, width: int = 30) -> str:
    """Create a simple text progress bar"""
    filled = int(width * percent / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}]"

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
    from cortex.utils.config import generate_config

    # Create run directory structure
    run_structure = create_run_structure(run_name)
    kernel_dir = create_kernel_directory(run_name, kernel_name)

    # Generate config
    config_dir = Path('primitives/configs/generated')
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
        # Cleanup: remove partial run directory on config generation failure
        _cleanup_partial_run(run_structure['run'])
        return None

    print(f"Running benchmark for {kernel_name}...")

    # Run harness
    results_dir = run_harness(str(config_path), run_name, verbose=verbose)

    if results_dir:
        print(f"✓ Benchmark complete: {results_dir}")
    else:
        # Cleanup: remove partial run directory on harness failure
        _cleanup_partial_run(run_structure['run'])

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
    from cortex.utils.config import generate_batch_configs

    # Create run directory structure
    create_run_structure(run_name)

    # Generate all configs
    config_dir = Path('primitives/configs/generated')
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
        from cortex.utils.config import generate_config
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
