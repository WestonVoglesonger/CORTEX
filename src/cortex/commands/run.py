"""Run experiments command."""
import sys
import platform
import subprocess
import argparse
from contextlib import contextmanager
from pathlib import Path
from cortex.utils.runner import HarnessRunner
from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.utils.paths import generate_run_name, create_run_structure
from cortex.utils.device import resolve_device, validate_capabilities, probe_pmu_available
from cortex.deploy import DeployerFactory, Deployer, DeploymentError
from cortex.core import (
    ConsoleLogger,
    RealFileSystemService,
    SubprocessExecutor,
    SystemTimeProvider,
    SystemEnvironmentProvider,
    SystemToolLocator,
    YamlConfigLoader,
)


@contextmanager
def _inhibit_host_sleep(verbose=False):
    """Prevent host machine from sleeping during benchmark.

    macOS: caffeinate -i -s (prevent idle + system sleep)
    Linux: systemd-inhibit (if available)
    Other: no-op
    """
    proc = None
    try:
        if platform.system() == "Darwin":
            proc = subprocess.Popen(
                ["caffeinate", "-i", "-s"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if verbose:
                print("Host sleep inhibited (caffeinate)")
        elif platform.system() == "Linux":
            # systemd-inhibit with sleep infinity as the held process
            proc = subprocess.Popen(
                ["systemd-inhibit", "--what=idle:sleep",
                 "--who=cortex", "--why=Benchmark running",
                 "sleep", "infinity"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if verbose:
                print("Host sleep inhibited (systemd-inhibit)")
        yield
    finally:
        if proc:
            proc.terminate()
            proc.wait()


def resolve_device_arg(args, config):
    """Resolve device/deployment string.

    Handles both device spec names (m1, rpi4) and deployment strings
    (ssh://pi@rpi, tcp://host:9000). DeployerFactory distinguishes them.

    Priority: CLI --device > config device: > None (auto-detect).

    Returns:
        Device string or None for auto-detect/local.
    """
    if hasattr(args, 'device') and args.device:
        return args.device

    if config and config.get('device'):
        return config['device']

    return None


def setup_parser(parser):
    """Setup argument parser for run command

    cortex run executes benchmarks without validation (fast iteration).
    For comprehensive verification, use 'cortex pipeline'.
    """
    parser.add_argument(
        '--kernel',
        help='Run single kernel (e.g., goertzel, notch_iir)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Run all available kernels (batch mode)'
    )
    parser.add_argument(
        '--config',
        help='Use custom config file (overrides --kernel and --all)'
    )
    parser.add_argument(
        '--run-name',
        help='Custom name for this run (default: auto-generated run-YYYY-MM-DD-NNN)'
    )
    parser.add_argument(
        '--dtype',
        choices=['f32', 'q15'],
        default='f32',
        help='Data type variant to run (default: f32)'
    )
    parser.add_argument(
        '--state',
        help='Path to calibration state file (.cortex_state) for trainable kernels'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose harness output'
    )
    parser.add_argument(
        '--device',
        help='Device primitive or deployment string. '
             'Examples: m1-macos | rpi4 | nvidia@192.168.1.123 | tcp://192.168.1.123:9000'
    )


def _run_with_deploy(deploy_string, run_fn, verbose, governor="performance"):
    """Handle deployment lifecycle around a run function.

    Args:
        deploy_string: Deploy string (e.g., ssh://pi@rpi) or None for local.
        run_fn: Callable(transport_uri) that runs the benchmark and returns results_dir.
        verbose: Show verbose output.
        governor: CPU frequency governor to set on remote device.

    Returns:
        CLI exit code (0 = success, 1 = failure).
    """
    with _inhibit_host_sleep(verbose=verbose):
        if deploy_string is None:
            results_dir = run_fn(transport_uri=None)
            return 0 if results_dir else 1

        try:
            result = DeployerFactory.from_device_string(deploy_string)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        if not isinstance(result, Deployer):
            # Transport URI string (e.g., tcp://host:9000)
            transport_uri = result
            if transport_uri != "local://":
                print(f"Manual mode: connecting to {transport_uri}")
            results_dir = run_fn(transport_uri=transport_uri)
            return 0 if results_dir else 1

        # Auto-deploy mode
        deployer = result
        print(f"Auto-deploy mode: deploying to {deploy_string}")
        try:
            deploy_result = deployer.deploy(verbose=verbose, skip_validation=True, governor=governor)
            results_dir = run_fn(transport_uri=deploy_result.transport_uri)

            if results_dir and hasattr(deployer, 'fetch_logs'):
                from cortex.utils.paths import get_deployment_dir
                deployment_dir = get_deployment_dir(results_dir.split('/')[-1] if '/' in str(results_dir) else results_dir)
                try:
                    print("\nFetching deployment logs...")
                    fetch_result = deployer.fetch_logs(str(deployment_dir))
                    if not fetch_result["success"]:
                        print(f"Log fetch issues: {fetch_result['errors']}")
                    else:
                        print(f"Deployment logs saved: {deployment_dir}/")
                except Exception as e:
                    print(f"Failed to fetch logs: {e}")

            return 0 if results_dir else 1

        except DeploymentError as e:
            print(f"\nDeployment failed: {e}")
            return 1
        finally:
            print("\nCleaning up deployment...")
            cleanup_result = deployer.cleanup()
            if not cleanup_result.success:
                print(f"Cleanup issues: {cleanup_result.errors}")


def _check_preflight(filesystem, process_executor, env_provider):
    """Print pre-flight tips: build status and PMU availability.

    Non-blocking, silent on success. Runs before benchmark dispatch.
    """
    # Build tip
    if not filesystem.exists('src/engine/harness/cortex'):
        print("Tip: Harness not built. Run `make all` first, "
              "then `cortex check-system` to verify setup.")
        return  # No point checking PMU if not built

    # PMU warning
    if not probe_pmu_available(filesystem, process_executor):
        system = env_provider.get_system_type()
        if system == 'Darwin':
            print("Note: PMU counters unavailable. Run with `sudo` "
                  "for instruction/cycle data. Latency benchmarks are valid without PMU.")
        elif system == 'Linux':
            print("Note: PMU counters unavailable. One-time fix: "
                  "`sudo setcap cap_perfmon=ep <adapter_path>`. "
                  "Latency benchmarks are valid without PMU.")
        else:
            print("Note: PMU counters unavailable. "
                  "Latency benchmarks are valid without PMU.")


def _analyze_pipeline_run(run_dir, filesystem):
    """Run per-pipeline analysis on pipeline-* subdirectories.

    Args:
        run_dir: Path to the run directory containing pipeline-* subdirs.
        filesystem: FileSystemService instance.
    """
    run_path = Path(run_dir)
    pipe_dirs = sorted(run_path.glob("pipeline-*"))
    if not pipe_dirs:
        return

    logger = ConsoleLogger()
    print(f"\nAnalyzing {len(pipe_dirs)} pipeline(s)...")

    for pipe_dir in pipe_dirs:
        if not pipe_dir.is_dir():
            continue
        analyzer = TelemetryAnalyzer(filesystem=filesystem, logger=logger)
        output_dir = str(pipe_dir / "analysis")
        success = analyzer.run_full_analysis(str(pipe_dir), output_dir=output_dir)
        status = "OK" if success else "no data"
        print(f"  {pipe_dir.name}: {status}")


def execute(args):
    """Execute run command."""
    print("=" * 80)
    print("CORTEX Benchmark Execution")
    print("=" * 80)
    print()

    # Get run name (from flag or interactive prompt)
    run_name = None
    if hasattr(args, 'run_name') and args.run_name:
        try:
            run_name = generate_run_name(args.run_name)
            print(f"Run name: {run_name}")
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    elif sys.stdin.isatty():
        print("Enter a custom name for this run, or press Enter for auto-naming:")
        print("(Auto-naming format: run-YYYY-MM-DD-NNN)")
        user_input = input("Run name: ").strip()
        if user_input:
            try:
                run_name = generate_run_name(user_input)
                print(f"Using run name: {run_name}")
            except ValueError as e:
                print(f"Error: {e}")
                return 1
        else:
            run_name = generate_run_name()
            print(f"Auto-generated run name: {run_name}")
    else:
        run_name = generate_run_name()
        print(f"Auto-generated run name: {run_name}")

    print()

    # Load config if config mode (needed for device resolution)
    filesystem = RealFileSystemService()
    config_loader = YamlConfigLoader(filesystem)
    config_dict = None
    if args.config:
        print(f"Using custom config: {args.config}")
        try:
            config_dict = config_loader.load_yaml(args.config)
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

    # Resolve device (--device handles both device specs and deployment strings)
    device_arg = resolve_device_arg(args, config_dict)
    device_spec = resolve_device(device_arg)
    if device_spec is not None:
        device_spec = validate_capabilities(device_spec)
        dev = device_spec.get('device', device_spec)
        print(f"Device: {dev.get('name', 'Unknown')}")
    elif device_arg:
        # Not a device spec — might be a deployment string, pass through
        device_spec = None

    # Determine deploy string: if device_arg looks like a deployment URI, use it.
    # Let DeployerFactory validate unknown strings before treating as typo —
    # this handles non-URI formats like serial:///dev/ttyUSB0.
    deploy_string = None
    if device_arg and ('://' in device_arg or '@' in device_arg):
        deploy_string = device_arg
    elif device_arg and device_spec is None:
        try:
            DeployerFactory.from_device_string(device_arg)
            deploy_string = device_arg
        except ValueError:
            print(f"Error: '{device_arg}' is not a recognized device spec or deployment string.")
            print("  Device specs: primitives/devices/*.yaml (e.g., m1-macos, rpi4)")
            print("  Deployment: user@host, tcp://host:port, ssh://user@host")
            return 1

    # Create production runner
    process_executor = SubprocessExecutor()
    runner = HarnessRunner(
        filesystem=filesystem,
        process_executor=process_executor,
        config_loader=config_loader,
        time_provider=SystemTimeProvider(),
        env_provider=SystemEnvironmentProvider(),
        tool_locator=SystemToolLocator(),
        logger=ConsoleLogger()
    )

    # Pre-flight checks (non-blocking tips) — skip for remote deployments
    # (PMU access is configured by the deployer on the remote device)
    env_provider = SystemEnvironmentProvider()
    if not deploy_string:
        _check_preflight(filesystem, process_executor, env_provider)

    # Extract governor from config for remote deployment
    governor = "performance"  # safe default
    if config_dict:
        governor = config_dict.get('power', {}).get('governor', 'performance')

    # Custom config mode
    if args.config:
        # Pipeline mode: config with 'pipelines' section triggers concurrent pipeline execution
        if config_dict and 'pipelines' in config_dict:
            captured = {}

            def run_fn(transport_uri):
                create_run_structure(run_name)
                results_dir = runner.run_pipelines(
                    args.config, run_name=run_name, verbose=args.verbose,
                    transport_uri=transport_uri, device_spec=device_spec,
                )
                captured['results_dir'] = results_dir
                return results_dir

            exit_code = _run_with_deploy(deploy_string, run_fn, args.verbose, governor=governor)

            if captured.get('results_dir'):
                _analyze_pipeline_run(captured['results_dir'], filesystem)

            return exit_code

        def run_fn(transport_uri):
            create_run_structure(run_name)
            return runner.run(
                args.config, run_name=run_name, verbose=args.verbose,
                transport_uri=transport_uri, device_spec=device_spec,
            )
        return _run_with_deploy(deploy_string, run_fn, args.verbose, governor=governor)

    # Single kernel mode
    if args.kernel:
        # Resolve kernel name with dtype qualifier
        kernel_qualified = args.kernel
        if args.dtype != 'f32':
            kernel_qualified = f"{args.kernel}/{args.dtype}"

        def run_fn(transport_uri):
            return runner.run_single_kernel(
                kernel_qualified, run_name=run_name,
                calibration_state=args.state,
                verbose=args.verbose, transport_uri=transport_uri,
                device_spec=device_spec,
            )
        return _run_with_deploy(deploy_string, run_fn, args.verbose, governor=governor)

    # Batch mode
    if args.all:
        def run_fn(transport_uri):
            return runner.run_all_kernels(
                run_name=run_name,
                calibration_state=args.state,
                verbose=args.verbose, transport_uri=transport_uri,
                device_spec=device_spec,
            )
        return _run_with_deploy(deploy_string, run_fn, args.verbose, governor=governor)

    # No mode specified
    print("Error: Must specify --kernel, --all, or --config")
    print("Examples:")
    print("  cortex run --kernel goertzel")
    print("  cortex run --all")
    print("  cortex run --config my_config.yaml")
    return 1
