"""Run experiments command with dependency injection.

CRIT-004: Updated to use new HarnessRunner class with injected dependencies.
"""
import sys
import argparse
from cortex.utils.runner import HarnessRunner
from cortex.utils.paths import generate_run_name, create_run_structure
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


def resolve_device_string(args, config) -> str:
    """
    Resolve device string with 3-level priority chain.

    Priority:
        1. CLI --device flag (highest)
        2. Config device: field
        3. Default "local://" (lowest)

    Args:
        args: Parsed command-line arguments
        config: Loaded config dict (or None)

    Returns:
        Device string for DeployerFactory.from_device_string()
    """
    # Priority 1: CLI --device flag
    if hasattr(args, 'device') and args.device:
        return args.device

    # Priority 2: Config device: field
    if config and 'device' in config:
        return config['device']

    # Priority 3: Default local
    return "local://"


def setup_parser(parser):
    """Setup argument parser for run command"""
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
        '--skip-validate',
        action='store_true',
        help='Skip oracle validation (faster, trust correctness)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose harness output'
    )
    parser.add_argument(
        '--device',
        help='Device connection string (auto-deploy or manual). '
             'Examples: nvidia@192.168.1.123 | tcp://192.168.1.123:9000 | local://'
    )


def execute(args):
    """Execute run command"""
    print("=" * 80)
    print("CORTEX Benchmark Execution")
    print("=" * 80)
    print()

    # Get run name (from flag or interactive prompt)
    run_name = None
    if hasattr(args, 'run_name') and args.run_name:
        # User provided --run-name flag
        try:
            run_name = generate_run_name(args.run_name)
            print(f"Run name: {run_name}")
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    elif sys.stdin.isatty():
        # Interactive prompt (only when stdin is a TTY)
        print("Enter a custom name for this run, or press Enter for auto-naming:")
        print("(Auto-naming format: run-YYYY-MM-DD-NNN)")
        user_input = input("Run name: ").strip()

        if user_input:
            # User provided custom name
            try:
                run_name = generate_run_name(user_input)
                print(f"Using run name: {run_name}")
            except ValueError as e:
                print(f"Error: {e}")
                return 1
        else:
            # Auto-generate name
            run_name = generate_run_name()
            print(f"Auto-generated run name: {run_name}")
    else:
        # Non-interactive mode (CI/scripts) - auto-generate without prompting
        run_name = generate_run_name()
        print(f"Auto-generated run name: {run_name}")

    print()

    # Create production runner with real dependencies
    filesystem = RealFileSystemService()
    runner = HarnessRunner(
        filesystem=filesystem,
        process_executor=SubprocessExecutor(),
        config_loader=YamlConfigLoader(filesystem),
        time_provider=SystemTimeProvider(),
        env_provider=SystemEnvironmentProvider(),
        tool_locator=SystemToolLocator(),
        logger=ConsoleLogger()
    )

    # Custom config mode
    if args.config:
        print(f"Using custom config: {args.config}")

        # Load config to check for device field
        try:
            config = runner.config_loader.load(args.config)
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

        # Resolve device string (CLI > config > default)
        device_string = resolve_device_string(args, config)

        # Parse device string (returns Deployer or transport URI)
        try:
            result = DeployerFactory.from_device_string(device_string)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        # Check if auto-deploy mode
        if isinstance(result, Deployer):
            deployer = result
            print(f"Auto-deploy mode: deploying to {device_string}")

            try:
                # Deploy
                deploy_result = deployer.deploy(
                    verbose=args.verbose,
                    skip_validation=args.skip_validate
                )

                # Create run directory structure (required by runner)
                create_run_structure(run_name)

                # Run benchmark using deployed adapter
                results_dir = runner.run(
                    args.config,
                    run_name=run_name,
                    verbose=args.verbose,
                    transport_uri=deploy_result.transport_uri
                )

                # Cleanup after benchmark completes
                print("\nCleaning up deployment...")
                cleanup_result = deployer.cleanup()
                if not cleanup_result.success:
                    print(f"⚠️  Cleanup issues: {cleanup_result.errors}")

                if results_dir:
                    print(f"\n✓ Benchmark complete")
                    print(f"Results: {results_dir}")
                    return 0
                else:
                    return 1

            except DeploymentError as e:
                print(f"\nDeployment failed: {e}")
                # Cleanup on deployment failure
                cleanup_result = deployer.cleanup()
                return 1

        else:
            # Manual mode: result is transport URI string
            transport_uri = result
            if transport_uri != "local://":
                print(f"Manual mode: connecting to {transport_uri}")

            # Create run directory structure (required by runner)
            create_run_structure(run_name)

            results_dir = runner.run(
                args.config,
                run_name=run_name,
                verbose=args.verbose,
                transport_uri=transport_uri
            )
            if results_dir:
                print(f"\n✓ Benchmark complete")
                print(f"Results: {results_dir}")
                return 0
            else:
                return 1

    # Single kernel mode
    if args.kernel:
        # Resolve device (no config in single kernel mode, so CLI or default)
        device_string = resolve_device_string(args, None)

        # Parse device string
        try:
            result = DeployerFactory.from_device_string(device_string)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        # Check if auto-deploy mode
        if isinstance(result, Deployer):
            deployer = result
            print(f"Auto-deploy mode: deploying to {device_string}")

            try:
                # Deploy
                deploy_result = deployer.deploy(
                    verbose=args.verbose,
                    skip_validation=args.skip_validate
                )

                # Create run directory structure (required by runner)
                create_run_structure(run_name)

                # Run benchmark using deployed adapter
                results_dir = runner.run_single_kernel(
                    args.kernel,
                    run_name=run_name,
                    duration=args.duration,
                    repeats=args.repeats,
                    warmup=args.warmup,
                    calibration_state=args.state,
                    verbose=args.verbose,
                    transport_uri=deploy_result.transport_uri
                )

                # Cleanup after benchmark completes
                print("\nCleaning up deployment...")
                cleanup_result = deployer.cleanup()
                if not cleanup_result.success:
                    print(f"⚠️  Cleanup issues: {cleanup_result.errors}")

                return 0 if results_dir else 1

            except DeploymentError as e:
                print(f"\nDeployment failed: {e}")
                # Cleanup on deployment failure
                cleanup_result = deployer.cleanup()
                return 1

        else:
            # Manual mode: result is transport URI string
            transport_uri = result
            if transport_uri != "local://":
                print(f"Manual mode: connecting to {transport_uri}")

            results_dir = runner.run_single_kernel(
                args.kernel,
                run_name=run_name,
                duration=args.duration,
                repeats=args.repeats,
                warmup=args.warmup,
                calibration_state=args.state,
                verbose=args.verbose,
                transport_uri=transport_uri
            )
            return 0 if results_dir else 1

    # Batch mode
    if args.all:
        # Resolve device (no config in batch mode, so CLI or default)
        device_string = resolve_device_string(args, None)

        # Parse device string
        try:
            result = DeployerFactory.from_device_string(device_string)
        except ValueError as e:
            print(f"Error: {e}")
            return 1

        # Check if auto-deploy mode
        if isinstance(result, Deployer):
            deployer = result
            print(f"Auto-deploy mode: deploying to {device_string}")

            try:
                # Deploy
                deploy_result = deployer.deploy(
                    verbose=args.verbose,
                    skip_validation=args.skip_validate
                )

                # Create run directory structure (required by runner)
                create_run_structure(run_name)

                # Run benchmark using deployed adapter
                results_dir = runner.run_all_kernels(
                    run_name=run_name,
                    duration=args.duration,
                    repeats=args.repeats,
                    warmup=args.warmup,
                    calibration_state=args.state,
                    verbose=args.verbose,
                    transport_uri=deploy_result.transport_uri
                )

                # Cleanup after benchmark completes
                print("\nCleaning up deployment...")
                cleanup_result = deployer.cleanup()
                if not cleanup_result.success:
                    print(f"⚠️  Cleanup issues: {cleanup_result.errors}")

                return 0 if results_dir else 1

            except DeploymentError as e:
                print(f"\nDeployment failed: {e}")
                # Cleanup on deployment failure
                cleanup_result = deployer.cleanup()
                return 1

        else:
            # Manual mode: result is transport URI string
            transport_uri = result
            if transport_uri != "local://":
                print(f"Manual mode: connecting to {transport_uri}")

            results_dir = runner.run_all_kernels(
                run_name=run_name,
                duration=args.duration,
                repeats=args.repeats,
                warmup=args.warmup,
                calibration_state=args.state,
                verbose=args.verbose,
                transport_uri=transport_uri
            )
            return 0 if results_dir else 1

    # No mode specified
    print("Error: Must specify --kernel, --all, or --config")
    print("Examples:")
    print("  cortex run --kernel goertzel")
    print("  cortex run --all")
    print("  cortex run --config my_config.yaml")
    return 1
