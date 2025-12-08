"""Experiment execution with dependency injection.

CRIT-004: Refactored to use class-based architecture with injected dependencies.
All external dependencies (filesystem, subprocess, time, etc.) are now abstracted
via Protocol interfaces, enabling full unit test coverage without I/O.
"""

import sys
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

# Constants
HARNESS_BINARY_PATH = 'src/engine/harness/cortex'
KERNEL_DATA_DIR = 'kernel-data'
HARNESS_LOG_FILE = 'harness.log'
GENERATED_CONFIG_DIR = 'primitives/configs/generated'


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

    def run(self, config_path: str, run_name: str, verbose: bool = False) -> Optional[str]:
        """Run the CORTEX harness with a given config.

        Args:
            config_path: Path to configuration file
            run_name: Name of the run for organizing results
            verbose: Show all output including stress-ng and telemetry

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

        # Set environment variables
        env = self.env.get_environ()
        env['PYTHONUNBUFFERED'] = '1'

        # Pass run-specific output directory to harness
        # This overrides config's output.directory so kernel-data goes to the right place
        run_dir = get_run_directory(run_name)
        env['CORTEX_OUTPUT_DIR'] = str(run_dir)

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
        verbose: bool = False
    ) -> Optional[str]:
        """Run benchmark for a single kernel.

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
        config_dir = Path(GENERATED_CONFIG_DIR)
        self.fs.mkdir(config_dir, parents=True, exist_ok=True)
        config_path = config_dir / f"{kernel_name}.yaml"

        self.log.info(f"Generating config for {kernel_name}...")

        if not generate_config(
            kernel_name,
            str(config_path),
            output_dir=str(kernel_dir),
            duration=duration,
            repeats=repeats,
            warmup=warmup
        ):
            # Cleanup: remove partial run directory on config generation failure
            self._cleanup_partial_run(run_structure['run'])
            return None

        self.log.info(f"Running benchmark for {kernel_name}...")

        # Run harness
        results_dir = self.run(str(config_path), run_name, verbose=verbose)

        if results_dir:
            self.log.info(f"✓ Benchmark complete: {results_dir}")
        else:
            # Cleanup: remove partial run directory on harness failure
            self._cleanup_partial_run(run_structure['run'])

        return results_dir

    def run_all_kernels(
        self,
        run_name: str,
        duration: Optional[int] = None,
        repeats: Optional[int] = None,
        warmup: Optional[int] = None,
        verbose: bool = False
    ) -> Optional[str]:
        """Run benchmarks for all available kernels.

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
        config_dir = Path(GENERATED_CONFIG_DIR)
        self.fs.mkdir(config_dir, parents=True, exist_ok=True)

        self.log.info("Generating configs for all kernels...")
        configs = generate_batch_configs(
            str(config_dir),
            duration=duration,
            repeats=repeats,
            warmup=warmup
        )

        if not configs:
            self.log.info("No kernels available to benchmark")
            return None

        self.log.info(f"Found {len(configs)} kernel(s) to benchmark")

        run_dir = get_run_directory(run_name)
        self.log.info(f"Results will be saved to: {run_dir}")
        self.log.info("")

        # Run each kernel
        results = []
        for i, (kernel_name, config_path) in enumerate(configs, 1):
            self.log.info("=" * 80)
            self.log.info(f"[{i}/{len(configs)}] Running {kernel_name}")
            self.log.info("=" * 80)

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
                self.log.info(f"✗ {kernel_name} failed (config generation)")
                self.log.info("")
                continue

            # Run harness
            result = self.run(config_path, run_name, verbose=verbose)

            if result:
                results.append((kernel_name, result))
                self.log.info(f"✓ {kernel_name} complete")
            else:
                self.log.info(f"✗ {kernel_name} failed")

            self.log.info("")

        # Summary
        self.log.info("=" * 80)
        self.log.info("Benchmark Summary")
        self.log.info("=" * 80)
        self.log.info(f"Completed: {len(results)}/{len(configs)} kernels")
        self.log.info(f"Results directory: {run_dir}")
        self.log.info("=" * 80)

        return str(run_dir) if results else None
