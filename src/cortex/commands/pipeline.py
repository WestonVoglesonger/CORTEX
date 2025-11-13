"""Pipeline command - Full end-to-end benchmarking"""
from cortex.commands import build, validate, run, analyze
from cortex.utils.runner import run_all_kernels
from cortex.utils.analyzer import run_full_analysis
from cortex.utils.paths import generate_run_name, get_analysis_dir
import argparse

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
    print("\nThis will:")
    if not args.skip_build:
        print("  1. Build all components")
    if not args.skip_validate:
        print(f"  {2 if not args.skip_build else 1}. Validate kernels")
    step = 3 if not args.skip_build and not args.skip_validate else (2 if not args.skip_build or not args.skip_validate else 1)
    print(f"  {step}. Run all kernel benchmarks")
    print(f"  {step+1}. Generate comparison analysis")
    print()

    # Step 1: Build
    if not args.skip_build:
        print("\n" + "=" * 80)
        print("STEP 1: BUILD")
        print("=" * 80)

        build_args = argparse.Namespace(
            clean=True,
            verbose=args.verbose,
            kernels_only=False,
            jobs=None
        )

        result = build.execute(build_args)
        if result != 0:
            print("\n✗ Build failed")
            return 1

    # Step 2: Validate
    if not args.skip_validate:
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

    # Step 3: Run all benchmarks
    print("\n" + "=" * 80)
    step_num = 3 if not args.skip_build and not args.skip_validate else (2 if not args.skip_build or not args.skip_validate else 1)
    print(f"STEP {step_num}: RUN BENCHMARKS")
    print("=" * 80)

    results_dir = run_all_kernels(
        run_name=run_name,
        duration=args.duration,
        repeats=args.repeats,
        warmup=args.warmup,
        verbose=args.verbose
    )

    if not results_dir:
        print("\n✗ Benchmark execution failed")
        return 1

    # Step 4: Analyze results
    print("\n" + "=" * 80)
    step_num += 1
    print(f"STEP {step_num}: ANALYZE RESULTS")
    print("=" * 80)

    # Get analysis directory for this run
    analysis_dir = str(get_analysis_dir(run_name))

    success = run_full_analysis(
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
