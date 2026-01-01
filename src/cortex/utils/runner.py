"""Experiment execution with dependency injection.

CRIT-004: Refactored to use class-based architecture with injected dependencies.
All external dependencies (filesystem, subprocess, time, etc.) are now abstracted
via Protocol interfaces, enabling full unit test coverage without I/O.
"""

import sys
import os
from pathlib import Path
from typing import Optional
from cortex.core.protocols import (
    FileSystemService,
    ProcessExecutor,
    ConfigLoader,
    TimeProvider,
    EnvironmentProvider,
    ToolLocator,
    Logger
)
from cortex.utils.paths import (
    create_run_structure,
    create_kernel_directory,
    get_run_directory
)
from cortex.utils.config import generate_temp_config

# Constants
HARNESS_BINARY_PATH = 'src/engine/harness/cortex'
KERNEL_DATA_DIR = 'kernel-data'
HARNESS_LOG_FILE = 'harness.log'

# Environment variable whitelist (defense-in-depth for subprocess isolation)
ALLOWED_ENV_VARS = {
    'PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'LC_ALL', 'TERM',
    'PYTHONUNBUFFERED', 'CORTEX_OUTPUT_DIR', 'CORTEX_NO_INHIBIT', 'CORTEX_TRANSPORT_URI'
}
ALLOWED_ENV_PREFIXES = ['CORTEX_']


class HarnessRunner:
    """Orchestrates harness execution with dependency injection.

    This class replaces the function-based API in the original runner.py.
    All external dependencies are injected, making this fully testable.

    Args:
        filesystem: Filesystem operations abstraction
        process_executor: Subprocess execution abstraction
        config_loader: Configuration file loading abstraction
        time_provider: Time operations abstraction
        env_provider: Environment access abstraction
        tool_locator: External tool discovery abstraction
        logger: Logging abstraction
    """

    def __init__(
        self,
        filesystem: FileSystemService,
        process_executor: ProcessExecutor,
        config_loader: ConfigLoader,
        time_provider: TimeProvider,
        env_provider: EnvironmentProvider,
        tool_locator: ToolLocator,
        logger: Logger
    ):
        self.fs = filesystem
        self.process = process_executor
        self.config = config_loader
        self.time = time_provider
        self.env = env_provider
        self.tools = tool_locator
        self.log = logger

    def _cleanup_partial_run(self, run_dir: Path) -> None:
        """Clean up a partial run directory on failure.

        Args:
            run_dir: Path to the run directory to clean up
        """
        try:
            if not self.fs.exists(run_dir):
                return

            # Check if directory is empty or only contains empty subdirectories
            has_data = False
            kernel_data_path = f"{run_dir}/{KERNEL_DATA_DIR}"

            if self.fs.exists(kernel_data_path):
                for kernel_dir in self.fs.iterdir(kernel_data_path):
                    if self.fs.is_dir(kernel_dir):
                        # Check if kernel directory has any files
                        if any(self.fs.iterdir(kernel_dir)):
                            has_data = True
                            break

            # Only remove if no data was written
            if not has_data:
                self.fs.rmtree(run_dir)
                self.log.info(f"Cleaned up partial run directory: {run_dir}")
        except Exception as e:
            # Don't fail if cleanup fails - just log it
            self.log.warning(f"Could not clean up partial run directory {run_dir}: {e}")

    def run(self, config_path: str, run_name: str, verbose: bool = False, transport_uri: Optional[str] = None, env: Optional[dict] = None) -> Optional[str]:
        """Run the CORTEX harness with a given config.

        Args:
            config_path: Path to configuration file
            run_name: Name of the run for organizing results
            verbose: Show all output including stress-ng and telemetry
            transport_uri: Optional device adapter transport URI (e.g., tcp://192.168.1.100:9000)
            env: Optional environment variable overrides (merged with base environment)

        Returns:
            Run directory path if successful, None otherwise
        """
        # Validate harness binary
        if not self.fs.exists(HARNESS_BINARY_PATH):
            self.log.error(f"Harness binary not found at {HARNESS_BINARY_PATH}")
            self.log.info("Run 'cortex build' first")
            return None

        if not self.fs.is_file(HARNESS_BINARY_PATH):
            self.log.error(f"{HARNESS_BINARY_PATH} exists but is not a file")
            return None

        # Validate config file
        if not self.fs.exists(config_path):
            self.log.error(f"Config file not found: {config_path}")
            return None

        if not self.fs.is_file(config_path):
            self.log.error(f"{config_path} exists but is not a file")
            return None

        # Build command
        cmd = [HARNESS_BINARY_PATH, 'run', config_path]

        # Add platform-specific sleep prevention wrapper
        # Can be disabled with CORTEX_NO_INHIBIT=1 (useful when running under sudo)
        system = self.env.get_system_type()
        sleep_prevention_tool = None
        no_inhibit = self.env.get_environ().get('CORTEX_NO_INHIBIT', '0') == '1'

        if not no_inhibit:
            if system == 'Darwin':
                # macOS: use caffeinate
                if self.tools.has_tool('caffeinate'):
                    cmd = ['caffeinate', '-dims'] + cmd
                    sleep_prevention_tool = 'caffeinate'
            elif system == 'Linux':
                # Linux: systemd-inhibit requires polkit authentication
                # This works in interactive terminals but fails when:
                # - Running under sudo (polkit can't authenticate)
                # - Running in non-interactive scripts
                # Check for these conditions and skip if auth will likely fail
                env_vars = self.env.get_environ()
                is_interactive = sys.stdin.isatty()
                running_under_sudo = 'SUDO_USER' in env_vars

                if self.tools.has_tool('systemd-inhibit') and is_interactive and not running_under_sudo:
                    cmd = ['systemd-inhibit', '--what=sleep:idle'] + cmd
                    sleep_prevention_tool = 'systemd-inhibit'

        # Force unbuffered output for real-time progress updates
        if self.tools.has_tool('stdbuf'):
            cmd = ['stdbuf', '-o0', '-e0'] + cmd

        # Set environment variables - get base environment from DI provider
        base_env = self.env.get_environ()

        # Merge caller's env vars (sanitized, caller's values win on conflicts)
        if env is not None:
            # Defense-in-depth: whitelist env vars to prevent injection of LD_PRELOAD, etc.
            sanitized_env = {
                k: v for k, v in env.items()
                if k in ALLOWED_ENV_VARS or any(k.startswith(p) for p in ALLOWED_ENV_PREFIXES)
            }
            base_env.update(sanitized_env)

        # Set required env vars (always applied, override even caller's values)
        base_env['PYTHONUNBUFFERED'] = '1'

        # Pass run-specific output directory to harness
        # This overrides config's output.directory so kernel-data goes to the right place
        run_dir = get_run_directory(run_name)
        base_env['CORTEX_OUTPUT_DIR'] = str(run_dir)

        # Pass transport URI if specified
        if transport_uri:
            base_env['CORTEX_TRANSPORT_URI'] = transport_uri

        # Use base_env for all subsequent operations
        env = base_env

        # Notify user of sleep prevention status
        if sleep_prevention_tool:
            self.log.info(f"[cortex] Sleep prevention active ({sleep_prevention_tool}) for benchmark consistency")
            self.log.info(f"[cortex] Display will stay on during benchmark")
        elif no_inhibit:
            # Intentionally disabled (e.g., script handles it externally)
            pass
        elif system == 'Linux' and 'SUDO_USER' in self.env.get_environ():
            # Running under sudo - systemd-inhibit skipped (polkit auth issues)
            # Don't warn, the calling script should handle sleep prevention
            pass
        elif system in ['Darwin', 'Linux']:
            self.log.info(f"[cortex] Note: Ensure system won't sleep during benchmarks")

        # Helper to execute subprocess and wait for completion
        def _execute_and_wait(stdout_dest, stderr_dest, show_spinner):
            # Launch subprocess
            process_handle = self.process.popen(
                cmd,
                stdout=stdout_dest,
                stderr=stderr_dest,
                cwd='.',
                env=env
            )

            # Record start time for progress tracking
            start_time = self.time.current_time()
            spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

            # Wait for process to complete
            if show_spinner:
                # Clean mode: show spinner
                # NOTE: Use direct print() for spinner to maintain single-line terminal behavior.
                # Logger abstraction always adds newlines, which would flood console with thousands
                # of lines. This is the one place where terminal control trumps DI abstraction.
                while process_handle.poll() is None:
                    elapsed = self.time.current_time() - start_time
                    spinner_idx = int(elapsed * 2) % len(spinner_chars)
                    print(f"\r[Running... {spinner_chars[spinner_idx]} {elapsed:.0f}s elapsed]    ",
                          end='', flush=True, file=sys.stdout)
                    self.time.sleep(0.5)
                # Clear progress line
                print(f"\r{' ' * 60}\r", end='', flush=True, file=sys.stdout)
            else:
                # Verbose mode: just wait without spinner
                process_handle.wait()

            # Get return code
            return process_handle.poll()

        try:
            if verbose:
                # Verbose mode: let C harness print directly to terminal
                returncode = _execute_and_wait(stdout_dest=None, stderr_dest=None, show_spinner=False)
            else:
                # Clean mode: redirect to log file and show spinner
                log_file = f"{run_dir}/{HARNESS_LOG_FILE}"
                # Use context manager for proper file handle cleanup
                with self.fs.open(log_file, 'w', buffering=1) as log_file_handle:
                    returncode = _execute_and_wait(
                        stdout_dest=log_file_handle,
                        stderr_dest=log_file_handle,
                        show_spinner=True
                    )

            if returncode != 0:
                self.log.error(f"\nHarness execution failed (exit code {returncode})")
                if not verbose:
                    self.log.info(f"Check log file for details: {run_dir}/{HARNESS_LOG_FILE}")
                else:
                    self.log.info("Check output above for error details")
                return None

            # Return the run directory path
            if self.fs.exists(run_dir):
                return str(run_dir)

            return None  # Run directory not created

        except Exception as e:
            self.log.error(f"Error running harness: {e}")
            return None

    def run_single_kernel(
        self,
        kernel_name: str,
        run_name: str,
        duration: Optional[int] = None,
        repeats: Optional[int] = None,
        warmup: Optional[int] = None,
        calibration_state: Optional[str] = None,
        verbose: bool = False,
        transport_uri: Optional[str] = None
    ) -> Optional[str]:
        """Run benchmark for a single kernel using temp YAML generation.

        Args:
            kernel_name: Name of kernel to benchmark
            run_name: Name of the run for organizing results
            duration: Override duration (seconds)
            repeats: Override number of repeats
            warmup: Override warmup duration (seconds)
            calibration_state: Path to .cortex_state file for trainable kernels
            verbose: Show verbose output

        Returns:
            Run directory path if successful, None otherwise
        """
        # Create run directory structure
        run_structure = create_run_structure(run_name)

        self.log.info(f"Running benchmark for {kernel_name}...")

        # Generate temp config with overrides
        base_config = "primitives/configs/cortex.yaml"
        temp_config = generate_temp_config(
            base_config_path=base_config,
            kernel_filter=kernel_name,
            duration=duration,
            repeats=repeats,
            warmup=warmup,
            calibration_state=calibration_state
        )

        try:
            # Run harness with temp config
            results_dir = self.run(temp_config, run_name, verbose=verbose, transport_uri=transport_uri, env=None)

            if results_dir:
                self.log.info(f"✓ Benchmark complete: {results_dir}")
            else:
                # Cleanup: remove partial run directory on harness failure
                self._cleanup_partial_run(run_structure['run'])

            return results_dir
        finally:
            # Always clean up temp config
            try:
                os.unlink(temp_config)
            except Exception as e:
                self.log.warning(f"Failed to clean up temp config {temp_config}: {e}")

    def run_all_kernels(
        self,
        run_name: str,
        duration: Optional[int] = None,
        repeats: Optional[int] = None,
        warmup: Optional[int] = None,
        calibration_state: Optional[str] = None,
        verbose: bool = False,
        transport_uri: Optional[str] = None
    ) -> Optional[str]:
        """Run benchmarks for all available kernels in a single harness invocation.

        Uses C harness auto-detection to discover all built kernels, then runs them
        sequentially in one execution. This is more efficient and cleaner than the
        previous approach of generating N configs and running harness N times.

        Args:
            run_name: Name of the run for organizing results
            duration: Override duration (seconds)
            repeats: Override number of repeats
            warmup: Override warmup duration (seconds)
            calibration_state: Not supported in --all mode (must use --kernel)
            verbose: Show verbose output

        Returns:
            Run directory path if successful, None otherwise
        """
        # Reject calibration_state in auto-detect mode (fails silently otherwise)
        if calibration_state is not None:
            self.log.error("ERROR: --state cannot be used with --all mode")
            self.log.info("Reason: Auto-detect runs ALL kernels, but each trainable kernel")
            self.log.info("        needs its own specific calibration state (ICA ≠ CSP ≠ LDA)")
            self.log.info("")
            self.log.info("Solution: Use --kernel to specify which trainable kernel to run:")
            self.log.info(f"  cortex run --kernel ica --state {calibration_state}")
            return None

        # Create run directory structure
        create_run_structure(run_name)

        self.log.info("Running benchmarks for all kernels (auto-detection mode)...")

        run_dir = get_run_directory(run_name)
        self.log.info(f"Results will be saved to: {run_dir}")
        self.log.info("")

        # Generate temp config with overrides (no kernel filter = run all)
        base_config = "primitives/configs/cortex.yaml"
        temp_config = generate_temp_config(
            base_config_path=base_config,
            kernel_filter=None,  # No filter = run all kernels
            duration=duration,
            repeats=repeats,
            warmup=warmup,
            calibration_state=calibration_state
        )

        try:
            # Single harness invocation with temp config
            results_dir = self.run(temp_config, run_name, verbose=verbose, transport_uri=transport_uri, env=None)

            if results_dir:
                self.log.info("")
                self.log.info("=" * 80)
                self.log.info("Benchmark Complete")
                self.log.info("=" * 80)
                self.log.info(f"Results directory: {results_dir}")
                self.log.info("=" * 80)

            return results_dir
        finally:
            # Always clean up temp config
            try:
                os.unlink(temp_config)
            except Exception as e:
                self.log.warning(f"Failed to clean up temp config {temp_config}: {e}")
