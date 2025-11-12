"""
Path management for CORTEX results directory structure.

New structure:
results/
├── run-2025-11-10-001/          # Auto-named or user-named
│   ├── kernel-data/
│   │   ├── bandpass_fir/
│   │   │   ├── telemetry.csv
│   │   │   ├── telemetry.ndjson
│   │   │   └── report.html
│   │   └── car/
│   │       └── ...
│   └── analysis/
│       ├── SUMMARY.md
│       └── *.png
"""

from pathlib import Path
from datetime import datetime
from typing import Optional
import re
import os

# fcntl is Unix-only, handle import gracefully
try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False


def generate_run_name(custom_name: Optional[str] = None, base_dir: str = "results") -> str:
    """
    Generate a run name for the results directory.

    Args:
        custom_name: User-provided custom name, or None for auto-generation
        base_dir: Base results directory (default: "results")

    Returns:
        Run name string (e.g., "run-2025-11-10-001" or custom name)

    Raises:
        ValueError: If custom name is invalid
    """
    if custom_name:
        # Validate custom name (alphanumeric, hyphens, underscores only)
        # Explicitly check for path separators and directory traversal attempts
        if not re.match(r'^[a-zA-Z0-9_-]+$', custom_name):
            raise ValueError(
                f"Invalid run name '{custom_name}'. "
                "Only alphanumeric characters, hyphens, and underscores allowed."
            )
        
        # Additional security: reject any path separators
        if '/' in custom_name or '\\' in custom_name or '..' in custom_name:
            raise ValueError(
                f"Invalid run name '{custom_name}'. "
                "Path separators and directory traversal sequences are not allowed."
            )

        # Canonicalize base directory path to prevent directory traversal
        results_path = Path(base_dir).resolve()
        if results_path.exists() and (results_path / custom_name).exists():
            raise ValueError(
                f"Run name '{custom_name}' already exists in {base_dir}/. "
                "Please choose a different name."
            )

        return custom_name

    # Auto-generate: run-YYYY-MM-DD-NNN
    today = datetime.now().strftime("%Y-%m-%d")
    prefix = f"run-{today}-"

    # Canonicalize base directory path
    results_path = Path(base_dir).resolve()
    if not results_path.exists():
        return f"{prefix}001"

    # Use file locking to prevent race conditions in parallel execution (Unix only)
    # On Windows or systems without fcntl, we'll use a fallback approach
    if HAS_FCNTL:
        lock_file = results_path / ".run_name_lock"
        
        try:
            # Create lock file if it doesn't exist
            lock_file.touch(exist_ok=True)
            
            # Acquire exclusive lock for sequence number generation
            with open(lock_file, 'r+') as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    # Find highest sequence number for today
                    max_seq = 0
                    for entry in results_path.iterdir():
                        if entry.is_dir() and entry.name.startswith(prefix):
                            # Extract sequence number
                            match = re.match(rf'^{re.escape(prefix)}(\d{{3}})$', entry.name)
                            if match:
                                seq = int(match.group(1))
                                max_seq = max(max_seq, seq)

                    # Return next sequence number
                    next_seq = max_seq + 1
                    return f"{prefix}{next_seq:03d}"
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        except (OSError, IOError) as e:
            # Fallback if file locking fails (e.g., on NFS)
            import warnings
            warnings.warn(f"Could not acquire lock for run name generation: {e}. "
                         "Race condition possible in parallel execution.")
            # Fall through to non-locked path
    
    # Fallback: find sequence without locking (race condition possible on Windows/parallel execution)
    import warnings
    if not HAS_FCNTL:
        warnings.warn("File locking not available on this platform. "
                     "Race condition possible in parallel execution.")
    
    # Find highest sequence number for today (without lock)
    max_seq = 0
    for entry in results_path.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix):
            match = re.match(rf'^{re.escape(prefix)}(\d{{3}})$', entry.name)
            if match:
                seq = int(match.group(1))
                max_seq = max(max_seq, seq)

    next_seq = max_seq + 1
    return f"{prefix}{next_seq:03d}"


def get_run_directory(run_name: str, base_dir: str = "results") -> Path:
    """
    Get the full path to a run directory.

    Args:
        run_name: Name of the run
        base_dir: Base results directory (default: "results")

    Returns:
        Path object for the run directory (canonicalized)
    """
    # Canonicalize paths to prevent directory traversal
    base_path = Path(base_dir).resolve()
    run_path = (base_path / run_name).resolve()
    
    # Ensure the resolved path is still within the base directory
    try:
        run_path.relative_to(base_path)
    except ValueError:
        raise ValueError(f"Invalid run name '{run_name}': resolves outside base directory")
    
    return run_path


def get_kernel_data_dir(run_name: str, kernel: Optional[str] = None, base_dir: str = "results") -> Path:
    """
    Get the path to kernel-data directory or a specific kernel's directory.

    Args:
        run_name: Name of the run
        kernel: Specific kernel name, or None for kernel-data root
        base_dir: Base results directory (default: "results")

    Returns:
        Path to kernel-data/ or kernel-data/{kernel}/
    """
    kernel_data = get_run_directory(run_name, base_dir) / "kernel-data"
    if kernel:
        return kernel_data / kernel
    return kernel_data


def get_analysis_dir(run_name: str, base_dir: str = "results") -> Path:
    """
    Get the path to the analysis directory for a run.

    Args:
        run_name: Name of the run
        base_dir: Base results directory (default: "results")

    Returns:
        Path to analysis/ directory
    """
    return get_run_directory(run_name, base_dir) / "analysis"


def get_most_recent_run(base_dir: str = "results") -> Optional[str]:
    """
    Find the most recently modified run directory.

    Args:
        base_dir: Base results directory (default: "results")

    Returns:
        Name of most recent run, or None if no runs exist
    """
    results_path = Path(base_dir)
    if not results_path.exists():
        return None

    # Find all run directories (must contain kernel-data/ subdirectory)
    run_dirs = []
    for entry in results_path.iterdir():
        if entry.is_dir() and (entry / "kernel-data").exists():
            run_dirs.append(entry)

    if not run_dirs:
        return None

    # Sort by modification time, most recent first
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return run_dirs[0].name


def get_all_runs(base_dir: str = "results") -> list[str]:
    """
    Get all run directory names, sorted by modification time (most recent first).

    Args:
        base_dir: Base results directory (default: "results")

    Returns:
        List of run names
    """
    results_path = Path(base_dir)
    if not results_path.exists():
        return []

    # Find all run directories (must contain kernel-data/ subdirectory)
    run_dirs = []
    for entry in results_path.iterdir():
        if entry.is_dir() and (entry / "kernel-data").exists():
            run_dirs.append(entry)

    # Sort by modification time, most recent first
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [d.name for d in run_dirs]


def create_run_structure(run_name: str, base_dir: str = "results") -> dict[str, Path]:
    """
    Create the directory structure for a new run.

    Args:
        run_name: Name of the run
        base_dir: Base results directory (default: "results")

    Returns:
        Dictionary with paths:
            - 'run': Path to run directory
            - 'kernel_data': Path to kernel-data directory
            - 'analysis': Path to analysis directory
    """
    run_dir = get_run_directory(run_name, base_dir)
    kernel_data = get_kernel_data_dir(run_name, base_dir=base_dir)
    analysis = get_analysis_dir(run_name, base_dir)

    # Create directories
    run_dir.mkdir(parents=True, exist_ok=True)
    kernel_data.mkdir(exist_ok=True)
    analysis.mkdir(exist_ok=True)

    return {
        'run': run_dir,
        'kernel_data': kernel_data,
        'analysis': analysis
    }


def create_kernel_directory(run_name: str, kernel: str, base_dir: str = "results") -> Path:
    """
    Create a directory for a specific kernel's data.

    Args:
        run_name: Name of the run
        kernel: Kernel name
        base_dir: Base results directory (default: "results")

    Returns:
        Path to the kernel's directory
    """
    kernel_dir = get_kernel_data_dir(run_name, kernel, base_dir)
    kernel_dir.mkdir(parents=True, exist_ok=True)
    return kernel_dir
