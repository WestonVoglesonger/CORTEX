"""Profile command - Orchestrator running predict → run → decompose (SE-5).

Runs the full 3-step latency analysis workflow sequentially:
1. cortex predict   → static prediction table
2. cortex run       → telemetry.ndjson
3. cortex decompose → CHARACTERIZATION.md
"""
import argparse
from pathlib import Path

from cortex.utils.device import resolve_device, validate_capabilities
from cortex.utils.paths import generate_run_name, get_analysis_dir


def setup_parser(parser):
    """Setup argument parser for profile command."""
    # Device (shared across predict + decompose)
    parser.add_argument(
        '--device',
        help='Path to device spec YAML (optional if auto-detect works)'
    )

    # Kernel selection (shared across predict + run)
    kernel_group = parser.add_mutually_exclusive_group()
    kernel_group.add_argument(
        '--kernel',
        help='Single kernel to profile'
    )
    kernel_group.add_argument(
        '--chain',
        help='Comma-separated kernel names for chain profiling'
    )
    kernel_group.add_argument(
        '--all',
        action='store_true',
        dest='run_all',
        help='Profile all available kernels'
    )

    # Run parameters
    parser.add_argument(
        '--run-name',
        help='Custom name for this run (default: auto-generated)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        help='Benchmark duration in seconds'
    )
    parser.add_argument(
        '--repeats',
        type=int,
        help='Number of benchmark repeats'
    )
    parser.add_argument(
        '--warmup',
        type=int,
        help='Warmup duration in seconds'
    )

    # Predict parameters
    parser.add_argument(
        '--channels',
        type=int,
        default=64,
        help='Number of channels (default: 64)'
    )
    parser.add_argument(
        '--window-length',
        type=int,
        default=160,
        help='Window length in samples (default: 160)'
    )

    # Deployment
    parser.add_argument(
        '--deploy',
        help='Deployment strategy (e.g., ssh://pi@rpi, tcp://host:9000). Omit for local.'
    )

    # Output
    parser.add_argument(
        '--output', '-o',
        help='Output directory for reports'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Show verbose output'
    )


def execute(args):
    """Execute full profile workflow: predict → run → decompose."""
    print("=" * 80)
    print("CORTEX LATENCY PROFILE")
    print("=" * 80)

    # Step 0: Resolve device
    device_path = args.device
    device_spec = resolve_device(device_path)
    if device_spec is None:
        if device_path:
            print(f"Error: Device spec not found: {device_path}")
        else:
            print("Error: Could not auto-detect device. Use --device <path>.")
        return 1
    device_spec = validate_capabilities(device_spec)
    dev = device_spec.get('device', device_spec)
    print(f"Device: {dev.get('name', 'Unknown')}")

    # Generate run name
    if args.run_name:
        try:
            run_name = generate_run_name(args.run_name)
        except ValueError as e:
            print(f"Error: {e}")
            return 1
    else:
        run_name = generate_run_name()

    print(f"Run name: {run_name}")

    # ----------------------------------------------------------
    # Step 1: Predict
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("STEP 1: PREDICT (Static Analysis)")
    print("=" * 80)

    from cortex.commands import predict as predict_cmd

    predict_args = argparse.Namespace(
        device=device_path,
        kernel=args.kernel,
        chain=args.chain,
        config=False,
        output=None,
        format='table',
        channels=args.channels,
        window_length=args.window_length,
    )

    result = predict_cmd.execute(predict_args)
    if result != 0:
        print("\nPrediction failed")
        return 1

    # ----------------------------------------------------------
    # Step 2: Run (benchmark)
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("STEP 2: RUN (Benchmark)")
    print("=" * 80)

    from cortex.utils.runner import HarnessRunner
    from cortex.core import (
        ConsoleLogger, RealFileSystemService, SubprocessExecutor,
        SystemTimeProvider, SystemEnvironmentProvider, SystemToolLocator,
        YamlConfigLoader,
    )

    filesystem = RealFileSystemService()
    runner = HarnessRunner(
        filesystem=filesystem,
        process_executor=SubprocessExecutor(),
        config_loader=YamlConfigLoader(filesystem),
        time_provider=SystemTimeProvider(),
        env_provider=SystemEnvironmentProvider(),
        tool_locator=SystemToolLocator(),
        logger=ConsoleLogger(),
    )

    # Build kernel list for runner
    kernel_arg = args.kernel
    chain_arg = args.chain
    chain_kernels = None
    if chain_arg:
        chain_kernels = [k.strip() for k in chain_arg.split(',') if k.strip()]
        # Ensure noop is included for I/O baseline
        if 'noop' not in chain_kernels:
            print("Adding noop to chain for I/O baseline measurement")
            chain_kernels.append('noop')

    deploy_string = args.deploy

    def _run_benchmark(transport_uri=None):
        if kernel_arg:
            return runner.run_single_kernel(
                kernel_arg,
                run_name=run_name,
                duration=args.duration,
                repeats=args.repeats,
                warmup=args.warmup,
                verbose=args.verbose,
                transport_uri=transport_uri,
                device_spec=device_spec,
            )
        else:
            return runner.run_all_kernels(
                run_name=run_name,
                duration=args.duration,
                repeats=args.repeats,
                warmup=args.warmup,
                verbose=args.verbose,
                transport_uri=transport_uri,
                chain_kernels=chain_kernels,
                device_spec=device_spec,
            )

    if deploy_string is None:
        results_dir = _run_benchmark()
    else:
        from cortex.commands.run import _run_with_deploy
        # _run_with_deploy returns an exit code, but we need results_dir
        # Use a mutable container to capture it
        captured = {}

        def run_fn(transport_uri):
            r = _run_benchmark(transport_uri=transport_uri)
            captured['results_dir'] = r
            return r

        exit_code = _run_with_deploy(deploy_string, run_fn, args.verbose)
        if exit_code != 0:
            return exit_code
        results_dir = captured.get('results_dir')

    if not results_dir:
        print("\nBenchmark execution failed")
        return 1

    # ----------------------------------------------------------
    # Step 3: Decompose
    # ----------------------------------------------------------
    print("\n" + "=" * 80)
    print("STEP 3: DECOMPOSE (Post-Benchmark Characterization)")
    print("=" * 80)

    from cortex.commands import decompose as decompose_cmd

    output_dir = args.output or str(get_analysis_dir(run_name))

    # Always prefer the resolved device.yaml saved by the runner into
    # the results directory — this handles short names like "m1-macos" that
    # resolve_device() understands but open() does not.
    saved_device_yaml = f"{results_dir}/device.yaml"
    device_yaml = saved_device_yaml if Path(saved_device_yaml).exists() else device_path

    decompose_args = argparse.Namespace(
        run_name=results_dir,
        device=device_yaml,
        output=output_dir,
        format='table',
    )

    result = decompose_cmd.execute(decompose_args)

    if result != 0:
        print("\nCharacterization failed")
        return 1

    # Success
    print("\n" + "=" * 80)
    print("PROFILE COMPLETE")
    print("=" * 80)
    print(f"\nResults: {results_dir}/")
    print(f"Characterization: {output_dir}/CHARACTERIZATION.md")
    print("=" * 80)

    return 0
