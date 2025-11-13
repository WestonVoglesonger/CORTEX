"""Clean build artifacts and results command"""
import os
import shutil
import subprocess
from pathlib import Path

def setup_parser(parser):
    """Setup argument parser for clean command"""
    parser.add_argument(
        '--results',
        action='store_true',
        help='Clean only results directory'
    )
    parser.add_argument(
        '--build',
        action='store_true',
        help='Clean only build artifacts'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Clean everything (default if no option specified)'
    )

def execute(args):
    """Execute clean command"""
    # Default to --all if no specific option given
    if not args.results and not args.build:
        args.all = True

    cleaned_items = []

    # Clean build artifacts
    if args.build or args.all:
        print("Cleaning build artifacts...")

        # Run make clean
        try:
            result = subprocess.run(
                ['make', 'clean'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                cleaned_items.append("Build artifacts (make clean)")
            else:
                print(f"Warning: make clean failed: {result.stderr}")
        except Exception as e:
            print(f"Warning: Could not run make clean: {e}")

        # Clean generated configs
        gen_configs = Path('primitives/configs/generated')
        if gen_configs.exists():
            try:
                shutil.rmtree(gen_configs)
                cleaned_items.append("Generated configs")
            except Exception as e:
                print(f"Warning: Could not clean generated configs: {e}")

    # Clean results
    if args.results or args.all:
        print("Cleaning results...")

        results_dir = Path('results')
        if results_dir.exists():
            # Count directories
            result_dirs = list(results_dir.iterdir())
            count = len(result_dirs)

            try:
                shutil.rmtree(results_dir)
                results_dir.mkdir()
                cleaned_items.append(f"Results directory ({count} run(s))")
            except Exception as e:
                print(f"Warning: Could not clean results directory: {e}")

        # Clean analysis directory
        analysis_dir = Path('results/analysis')
        if analysis_dir.exists():
            try:
                shutil.rmtree(analysis_dir)
                cleaned_items.append("Analysis outputs")
            except Exception as e:
                print(f"Warning: Could not clean analysis directory: {e}")

    # Report what was cleaned
    if cleaned_items:
        print("\nCleaned:")
        for item in cleaned_items:
            print(f"  ✓ {item}")
        print("\nDone!")
        return 0
    else:
        print("Nothing to clean.")
        return 0
