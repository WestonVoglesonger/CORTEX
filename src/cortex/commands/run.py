"""Run experiments command with dependency injection.

CRIT-004: Updated to use new HarnessRunner class with injected dependencies.
"""
import sys
import argparse
from pathlib import Path
from cortex.utils.runner import HarnessRunner
from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.utils.paths import generate_run_name, create_run_structure
from cortex.utils.device import resolve_device, validate_capabilities
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


def resolve_device_arg(args, config):
    """Resolve device primitive name/path.

    Priority: CLI --device > config device: > None (auto-detect).

    Returns:
        Device primitive name/path or None for auto-detect.
    """
    if hasattr(args, 'device') and args.device:
        return args.device

    if config and config.get('device'):
        return config['device']

    return None


def resolve_deploy_arg(args, config):
    """Resolve deployment strategy.

    Priority: CLI --deploy > config deploy: > None (local execution).

    Returns:
        Deploy string or None for local execution.
    """
    if hasattr(args, 'deploy') and args.deploy:
        return args.deploy

    if config and config.get('deploy'):
        return config['deploy']

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
        '--duration',
        type=int,
        help='Override benchmark duration (seconds)'
    )
    parser.add_argument(
        '--repeats',
        type=int,
        help='Override number of repeats'
    )
    parser.add_argument(
        '--warmup',
        type=int,
        help='Override warmup duration (seconds)'
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
        help='Device primitive name or YAML path (e.g., m1, rpi4). Auto-detects if omitted.'
    )
    parser.add_argument(
        '--deploy',
        help='Deployment strategy (e.g., ssh://pi@rpi, tcp://host:9000). Omit for local.'
    )


def _run_with_deploy(deploy_string, run_fn, verbose):
    """Handle deployment lifecycle around a run function.

    Args:
        deploy_string: Deploy string (e.g., ssh://pi@rpi) or None for local.
        run_fn: Callable(transport_uri) that runs the benchmark and returns results_dir.
        verbose: Show verbose output.

    Returns:
        CLI exit code (0 = success, 1 = failure).
    """
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
        deploy_result = deployer.deploy(verbose=verbose, skip_validation=True)
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

    # Load config if config mode (needed for device/deploy resolution)
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

    # Resolve device primitive (--device = what hardware)
    device_arg = resolve_device_arg(args, config_dict)
    device_spec = resolve_device(device_arg)
    if device_spec is not None:
        device_spec = validate_capabilities(device_spec)
        dev = device_spec.get('device', device_spec)
        print(f"Device: {dev.get('name', 'Unknown')}")
    elif device_arg:
        print(f"Error: Device not found: {device_arg}")
        return 1

    # Resolve deploy strategy (--deploy = how to reach it)
    deploy_string = resolve_deploy_arg(args, config_dict)

    # Create production runner
    runner = HarnessRunner(
        filesystem=filesystem,
        process_executor=SubprocessExecutor(),
        config_loader=config_loader,
        time_provider=SystemTimeProvider(),
        env_provider=SystemEnvironmentProvider(),
        tool_locator=SystemToolLocator(),
        logger=ConsoleLogger()
    )

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
                    duration=args.duration, repeats=args.repeats,
                    warmup=args.warmup,
                )
                captured['results_dir'] = results_dir
                return results_dir

            exit_code = _run_with_deploy(deploy_string, run_fn, args.verbose)

            if captured.get('results_dir'):
                _analyze_pipeline_run(captured['results_dir'], filesystem)

            return exit_code

        def run_fn(transport_uri):
            create_run_structure(run_name)
            return runner.run(
                args.config, run_name=run_name, verbose=args.verbose,
                transport_uri=transport_uri, device_spec=device_spec,
            )
        return _run_with_deploy(deploy_string, run_fn, args.verbose)

    # Single kernel mode
    if args.kernel:
        def run_fn(transport_uri):
            return runner.run_single_kernel(
                args.kernel, run_name=run_name,
                duration=args.duration, repeats=args.repeats,
                warmup=args.warmup, calibration_state=args.state,
                verbose=args.verbose, transport_uri=transport_uri,
                device_spec=device_spec,
            )
        return _run_with_deploy(deploy_string, run_fn, args.verbose)

    # Batch mode
    if args.all:
        def run_fn(transport_uri):
            return runner.run_all_kernels(
                run_name=run_name,
                duration=args.duration, repeats=args.repeats,
                warmup=args.warmup, calibration_state=args.state,
                verbose=args.verbose, transport_uri=transport_uri,
                device_spec=device_spec,
            )
        return _run_with_deploy(deploy_string, run_fn, args.verbose)

    # No mode specified
    print("Error: Must specify --kernel, --all, or --config")
    print("Examples:")
    print("  cortex run --kernel goertzel")
    print("  cortex run --all")
    print("  cortex run --config my_config.yaml")
    return 1
