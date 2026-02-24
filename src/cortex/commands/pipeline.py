"""Pipeline command - Full end-to-end benchmarking"""
from cortex.commands import build, validate, run, analyze
from cortex.utils.runner import HarnessRunner
from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.utils.paths import generate_run_name, get_analysis_dir
from cortex.utils.build_helper import smart_build
from cortex.utils.config import load_base_config
from cortex.utils.discovery import discover_kernels
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
import argparse
import sys

def setup_parser(parser):
    """Setup argument parser for pipeline command"""
    parser.add_argument(
        '--run-name',
        help='Custom name for this pipeline run (default: auto-generated)'
    )
    parser.add_argument(
        '--skip-build',
        action='store_true',
        help='Skip build step (assume already built)'
    )
    parser.add_argument(
        '--skip-validate',
        action='store_true',
        help='Skip kernel validation step'
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
        '--verbose', '-v',
        action='store_true',
        help='Show verbose output'
    )
    parser.add_argument(
        '--skip-system-check',
        action='store_true',
        help='Skip pre-flight system configuration check'
    )
    parser.add_argument(
        '--device',
        help='Device connection string (auto-deploy or manual). '
             'Examples: nvidia@192.168.1.123 | tcp://192.168.1.123:9000 | local://'
    )

def execute(args):
    """Execute full pipeline"""
    print("=" * 80)
    print("CORTEX FULL PIPELINE")
    print("=" * 80)

    # Generate run name
    if hasattr(args, 'run_name') and args.run_name:
        try:
            run_name = generate_run_name(args.run_name)
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    else:
        run_name = generate_run_name()

    print(f"\nRun name: {run_name}")

    # Load default config to check for device field
    fs = RealFileSystemService()
    config_loader = YamlConfigLoader(fs)
    try:
        config = config_loader.load_yaml("primitives/configs/cortex.yaml")
    except Exception:
        config = None  # Config loading failed, proceed with CLI/default

    # Parse device string (CLI > config > default)
    device_string = None
    if hasattr(args, 'device') and args.device:
        device_string = args.device  # Priority 1: CLI flag
    elif config and 'device' in config:
        device_string = config['device']  # Priority 2: Config field
    else:
        device_string = "local://"  # Priority 3: Default

    try:
        device_result = DeployerFactory.from_device_string(device_string)
    except ValueError as e:
        print(f"\nError: {e}")
        return 1

    # Determine if auto-deploy mode
    is_auto_deploy = isinstance(device_result, Deployer)
    if is_auto_deploy:
        print(f"\n🚀 Auto-deploy mode: {device_string}")
        print("   → Build: On device (via deployment)")
        print("   → Validate: On device (if Python available)")
        print("   → Benchmark: On device")
    elif device_string != "local://":
        print(f"\n🔗 Manual mode: {device_string}")
        print("   → Build: On host")
        print("   → Validate: On host")
        print("   → Benchmark: On device")

    # Step 0: System Configuration Check (pre-flight)
    if not args.skip_system_check:
        print("\n" + "=" * 80)
        print("PRE-FLIGHT: SYSTEM CONFIGURATION CHECK")
        print("=" * 80)
        print()

        from cortex.commands import check_system
        check_args = argparse.Namespace(verbose=args.verbose)
        exit_code = check_system.execute(check_args)
        all_pass = (exit_code == 0)

        if not all_pass:
            print()
            # Check if running in interactive terminal
            if sys.stdin.isatty():
                # Interactive: prompt user
                response = input("System check found critical issues. Continue anyway? [y/N]: ")
                if response.lower() not in ['y', 'yes']:
                    print("Pipeline aborted.")
                    return 1
            else:
                # Non-interactive (CI/CD, scripts): warn and continue
                print("⚠️  System check found critical issues.")
                print("    Continuing in non-interactive mode (use --skip-system-check to suppress)")
            print()

    print("\nThis will:")
    step_num = 0
    if not args.skip_system_check:
        step_num += 1
        print(f"  {step_num}. Check system configuration (pre-flight)")
    if is_auto_deploy:
        step_num += 1
        print(f"  {step_num}. Deploy to remote device")
    else:
        if not args.skip_build:
            step_num += 1
            print(f"  {step_num}. Build all components")
        if not args.skip_validate:
            step_num += 1
            print(f"  {step_num}. Validate kernels")
    step_num += 1
    print(f"  {step_num}. Run all kernel benchmarks")
    step_num += 1
    print(f"  {step_num}. Generate comparison analysis")
    print()

    # Step 1: Build (smart incremental) - Skip in auto-deploy mode
    if not args.skip_build and not is_auto_deploy:
        print("\n" + "=" * 80)
        print("STEP 1: BUILD (Smart Incremental)")
        print("=" * 80)

        # Determine which kernels we'll run
        try:
            base_config = load_base_config()
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

        # Get list of kernels that will be run
        if 'plugins' in base_config and base_config['plugins']:
            # Explicit mode: build only listed kernels
            kernel_names = [p['name'] for p in base_config['plugins'] if p.get('status') == 'ready']
            print(f"Building kernels from config: {kernel_names}")

            # Get spec URIs for these kernels
            all_kernels = discover_kernels()
            kernel_map = {k['display_name']: k for k in all_kernels}
            kernel_spec_uris = [kernel_map[name]['spec_uri'] for name in kernel_names if name in kernel_map]
        else:
            # Auto-detect mode: build all built kernels (or check if they need rebuilding)
            print("Auto-detect mode: checking all kernels")
            kernels = discover_kernels()
            kernel_spec_uris = [k['spec_uri'] for k in kernels if k.get('spec_uri')]

        print(f"\nChecking {len(kernel_spec_uris)} kernel(s)...")
        print()

        # Smart incremental build
        build_result = smart_build(
            kernel_spec_uris,
            force_rebuild=False,
            verbose=args.verbose
        )

        if not build_result['success']:
            print("\n✗ Build failed")
            for error in build_result['errors']:
                print(f"  - {error}")
            return 1

        # Summary
        print("\n" + "=" * 80)
        print("Build Summary")
        print("=" * 80)
        if build_result['harness_rebuilt']:
            print("  ✓ Harness rebuilt")
        else:
            print("  ✓ Harness up-to-date")

        if build_result['kernels_rebuilt']:
            print(f"  ✓ {len(build_result['kernels_rebuilt'])} kernel(s) rebuilt:")
            for k in build_result['kernels_rebuilt']:
                print(f"     - {k}")
        if build_result['kernels_skipped']:
            print(f"  ⊙ {len(build_result['kernels_skipped'])} kernel(s) up-to-date")

        print("=" * 80)

    # Step 2: Validate - Skip in auto-deploy mode
    if not args.skip_validate and not is_auto_deploy:
        print("\n" + "=" * 80)
        step_num = 2 if not args.skip_build else 1
        print(f"STEP {step_num}: VALIDATE")
        print("=" * 80)

        validate_args = argparse.Namespace(
            kernel=None,
            verbose=args.verbose
        )

        result = validate.execute(validate_args)
        if result != 0:
            print("\n✗ Validation failed")
            return 1

    # Auto-deploy: Deploy to device
    deployer = None
    transport_uri = None
    if is_auto_deploy:
        deployer = device_result
        print("\n" + "=" * 80)
        step_num = 2 if not args.skip_build else 1
        print(f"STEP {step_num}: DEPLOY TO DEVICE")
        print("=" * 80)
    else:
        # Manual or local mode
        transport_uri = device_result if isinstance(device_result, str) else None

    # Wrap deployment and benchmark in try/finally to ensure cleanup
    try:
        # Deploy if auto-deploy mode
        if is_auto_deploy:
            try:
                deploy_result = deployer.deploy(
                    verbose=args.verbose,
                    skip_validation=args.skip_validate
                )
                transport_uri = deploy_result.transport_uri
                print(f"\n✓ Deployment complete: {transport_uri}")
            except DeploymentError as e:
                print(f"\n✗ Deployment failed: {e}")
                return 1

        # Step 3: Run all benchmarks
        print("\n" + "=" * 80)
        if is_auto_deploy:
            step_num += 1
        else:
            step_num = 3 if not args.skip_build and not args.skip_validate else (2 if not args.skip_build or not args.skip_validate else 1)
        print(f"STEP {step_num}: RUN BENCHMARKS")
        print("=" * 80)

        # Create runner with production dependencies
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

        # Run all kernels with default config
        results_dir = runner.run_all_kernels(
            run_name=run_name,
            duration=args.duration,
            repeats=args.repeats,
            warmup=args.warmup,
            verbose=args.verbose,
            transport_uri=transport_uri
        )

        if not results_dir:
            print("\n✗ Benchmark execution failed")
            return 1

        # Fetch logs BEFORE cleanup (in finally block to ensure it runs)
        if deployer and hasattr(deployer, 'fetch_logs'):
            from cortex.utils.paths import get_deployment_dir
            deployment_dir = get_deployment_dir(run_name)

            try:
                print("\n" + "=" * 80)
                print("FETCHING LOGS: Retrieving deployment logs")
                print("=" * 80)
                fetch_result = deployer.fetch_logs(str(deployment_dir))
                if not fetch_result["success"]:
                    print(f"⚠️  Log fetch issues: {fetch_result['errors']}")
                else:
                    print(f"✓ Deployment logs saved: {deployment_dir}/")
            except Exception as e:
                print(f"⚠️  Failed to fetch logs: {e}")

    finally:
        # Cleanup deployment if auto-deploy mode (always runs)
        if deployer:
            print("\n" + "=" * 80)
            print("CLEANUP: Removing deployment")
            print("=" * 80)
            cleanup_result = deployer.cleanup()
            if cleanup_result.success:
                print("✓ Device cleaned")
            else:
                print(f"⚠️  Cleanup issues: {cleanup_result.errors}")

    # Step 4: Analyze results
    print("\n" + "=" * 80)
    step_num += 1
    print(f"STEP {step_num}: ANALYZE RESULTS")
    print("=" * 80)

    # Get analysis directory for this run
    analysis_dir = str(get_analysis_dir(run_name))

    # Create analyzer with production dependencies (reuse filesystem from runner)
    analyzer = TelemetryAnalyzer(
        filesystem=filesystem,
        logger=ConsoleLogger()
    )

    success = analyzer.run_full_analysis(
        results_dir,
        output_dir=analysis_dir,
        plots=['all'],
        format='png',
        telemetry_format='ndjson'
    )

    if not success:
        print("\n✗ Analysis failed")
        return 1

    # Success summary
    print("\n" + "=" * 80)
    print("✓ PIPELINE COMPLETE!")
    print("=" * 80)
    print("\nResults:")
    print(f"  Run directory: {results_dir}/")
    print(f"  Kernel data: {results_dir}/kernel-data/")
    print(f"  Analysis plots: {analysis_dir}/")
    print(f"  Summary table: {analysis_dir}/SUMMARY.md")
    print("\nNext steps:")
    print(f"  cat {analysis_dir}/SUMMARY.md")
    print(f"  open {analysis_dir}/latency_comparison.png")
    print(f"  open {results_dir}/kernel-data/*/report.html")
    print("=" * 80)

    return 0
