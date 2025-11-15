"""Pipeline command - Full end-to-end benchmarking"""
from cortex.commands import build, validate, run, analyze
from cortex.utils.runner import run_all_kernels
from cortex.utils.analyzer import run_full_analysis
from cortex.utils.paths import generate_run_name, get_analysis_dir
from cortex.utils.build_helper import smart_build
from cortex.utils.config import load_base_config
from cortex.utils.discovery import discover_kernels
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
    parser.add_argument(
        '--skip-system-check',
        action='store_true',
        help='Skip pre-flight system configuration check'
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

    # Step 0: System Configuration Check (pre-flight)
    if not args.skip_system_check:
        print("\n" + "=" * 80)
        print("PRE-FLIGHT: SYSTEM CONFIGURATION CHECK")
        print("=" * 80)
        print()

        from cortex.commands import check_system
        check_args = argparse.Namespace(verbose=args.verbose)
        checks, all_pass = check_system.run_all_checks()
        check_system.print_results(checks, verbose=args.verbose)

        if not all_pass:
            print()
            response = input("System check found critical issues. Continue anyway? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                print("Pipeline aborted.")
                return 1
            print()

    print("\nThis will:")
    step_num = 0
    if not args.skip_system_check:
        step_num += 1
        print(f"  {step_num}. Check system configuration (pre-flight)")
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

    # Step 1: Build (smart incremental)
    if not args.skip_build:
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
