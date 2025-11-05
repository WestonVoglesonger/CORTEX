#!/usr/bin/env python3
"""
CORTEX Benchmark Suite CLI
Main entry point for all benchmarking operations.
"""
import argparse
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cortex_cli.commands import (
    build, run, analyze, pipeline,
    list_kernels, validate, clean
)

def main():
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
        elif args.command == 'clean':
            sys.exit(clean.execute(args))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
