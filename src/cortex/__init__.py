"""
CORTEX CLI - Brain-Computer Interface Kernel Benchmarking Pipeline

A command-line interface for automating BCI kernel benchmarks, analysis,
and report generation.
"""
import argparse
import sys

__version__ = "0.2.0"
__author__ = "Avi Kumar, Weston Voglesonger"

def main():
    """Main CLI entry point"""
    from cortex.commands import (
        build, run, analyze, pipeline,
        list_kernels, validate, clean, check_system, calibrate, generate
    )

    parser = argparse.ArgumentParser(
        prog='cortex',
        description='CORTEX: BCI Kernel Benchmarking Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  cortex build                      # Build all components
  cortex run --all                  # Run all kernel benchmarks
  cortex run --kernel goertzel      # Run single kernel
  cortex analyze results/batch_123  # Analyze results
  cortex pipeline                   # Full pipeline (build+run+analyze)
  cortex list                       # Show available kernels
  cortex validate                   # Test kernels against oracles
  cortex check-system               # Check system configuration

  # Calibration workflow (trainable kernels)
  cortex generate --channels 64 --duration 60 --output-dir calib_64ch
  cortex calibrate --kernel csp --dataset calib_64ch --labels "100x0,100x1" --output state.cortex_state
  cortex run --kernel csp --state state.cortex_state

For more info: https://github.com/WestonVoglesonger/CORTEX
        '''
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Build command
    build_parser = subparsers.add_parser('build', help='Build all components')
    build.setup_parser(build_parser)

    # Run command
    run_parser = subparsers.add_parser('run', help='Run experiments')
    run.setup_parser(run_parser)

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze results')
    analyze.setup_parser(analyze_parser)

    # Pipeline command
    pipeline_parser = subparsers.add_parser('pipeline', help='Full pipeline')
    pipeline.setup_parser(pipeline_parser)

    # List command
    list_parser = subparsers.add_parser('list', help='List available kernels')
    list_kernels.setup_parser(list_parser)

    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate kernels')
    validate.setup_parser(validate_parser)

    # Clean command
    clean_parser = subparsers.add_parser('clean', help='Clean build/results')
    clean.setup_parser(clean_parser)

    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate synthetic dataset primitive')
    generate.setup_parser(generate_parser)

    # Calibrate command (ABI v3)
    calibrate_parser = subparsers.add_parser('calibrate', help='Calibrate trainable kernels (ABI v3)')
    calibrate.setup_parser(calibrate_parser)

    # Check-system command
    check_system_parser = subparsers.add_parser('check-system', help='Check system configuration for benchmarking')
    check_system.setup_parser(check_system_parser)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handler
    try:
        if args.command == 'build':
            sys.exit(build.execute(args))
        elif args.command == 'run':
            sys.exit(run.execute(args))
        elif args.command == 'analyze':
            sys.exit(analyze.execute(args))
        elif args.command == 'pipeline':
            sys.exit(pipeline.execute(args))
        elif args.command == 'list':
            sys.exit(list_kernels.execute(args))
        elif args.command == 'validate':
            sys.exit(validate.execute(args))
        elif args.command == 'generate':
            sys.exit(generate.execute(args))
        elif args.command == 'calibrate':
            sys.exit(calibrate.execute(args))
        elif args.command == 'clean':
            sys.exit(clean.execute(args))
        elif args.command == 'check-system':
            sys.exit(check_system.execute(args))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
