"""Run experiments command"""
from cortex_cli.core.runner import run_single_kernel, run_all_kernels

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
        help='Show verbose harness output'
    )

def execute(args):
    """Execute run command"""
    print("=" * 80)
    print("CORTEX Benchmark Execution")
    print("=" * 80)
    print()

    # Custom config mode
    if args.config:
        from cortex_cli.core.runner import run_harness
        print(f"Using custom config: {args.config}")
        results_dir = run_harness(args.config, verbose=args.verbose)
        if results_dir:
            print(f"\n✓ Benchmark complete")
            print(f"Results: {results_dir}")
            return 0
        else:
            return 1

    # Single kernel mode
    if args.kernel:
        results_dir = run_single_kernel(
            args.kernel,
            duration=args.duration,
            repeats=args.repeats,
            warmup=args.warmup,
            verbose=args.verbose
        )
        return 0 if results_dir else 1

    # Batch mode
    if args.all:
        results_dir = run_all_kernels(
            duration=args.duration,
            repeats=args.repeats,
            warmup=args.warmup,
            verbose=args.verbose
        )
        return 0 if results_dir else 1

    # No mode specified
    print("Error: Must specify --kernel, --all, or --config")
    print("Examples:")
    print("  cortex run --kernel goertzel")
    print("  cortex run --all")
    print("  cortex run --config my_config.yaml")
    return 1
