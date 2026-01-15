"""Generate synthetic dataset primitive instances

Creates self-describing dataset directories with spec.yaml and binary data.
"""
import sys
from pathlib import Path
from datetime import datetime
import yaml
import shutil


def setup_parser(parser):
    """Setup argument parser for generate command"""
    parser.add_argument(
        '--signal',
        default='pink_noise',
        choices=['pink_noise', 'sine_wave'],
        help='Signal type (default: pink_noise)'
    )
    parser.add_argument(
        '--channels',
        type=int,
        required=True,
        help='Number of channels'
    )
    parser.add_argument(
        '--duration',
        type=float,
        required=True,
        help='Duration in seconds'
    )
    parser.add_argument(
        '--output-dir',
        required=True,
        help='Output directory (creates dataset primitive instance)'
    )
    parser.add_argument(
        '--window-length',
        type=int,
        default=160,
        help='Window length in samples (default: 160)'
    )
    parser.add_argument(
        '--sample-rate',
        type=float,
        default=160.0,
        help='Sample rate in Hz (default: 160.0)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )
    parser.add_argument(
        '--amplitude',
        type=float,
        default=100.0,
        help='Amplitude in µV RMS (default: 100.0)'
    )
    parser.add_argument(
        '--frequency',
        type=float,
        help='Frequency in Hz (required for sine signal)'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing dataset directory'
    )


def execute(args):
    """Execute generate command"""
    print("=" * 80)
    print("CORTEX Synthetic Dataset Generator")
    print("=" * 80)

    # Validate sine requires frequency
    if args.signal == 'sine_wave' and args.frequency is None:
        print("\n✗ --frequency required for sine_wave signal")
        return 1

    # Check output directory
    output_dir = Path(args.output_dir)
    if output_dir.exists():
        if not args.overwrite:
            print(f"\n✗ Directory exists: {args.output_dir}")
            print("  Use --overwrite to replace")
            return 1
        print(f"\n⚠ Overwriting existing directory: {args.output_dir}")
        shutil.rmtree(output_dir)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nSignal:       {args.signal}")
    print(f"Channels:     {args.channels}")
    print(f"Duration:     {args.duration}s")
    print(f"Sample Rate:  {args.sample_rate} Hz")
    print(f"Seed:         {args.seed}")
    if args.signal == 'sine_wave':
        print(f"Frequency:    {args.frequency} Hz")
    else:
        print(f"Amplitude:    {args.amplitude} µV RMS")
    print()

    # Import generator
    try:
        # Get absolute path to generator module
        generator_path = Path(__file__).resolve().parents[3] / 'primitives' / 'datasets' / 'v1' / 'synthetic'
        if not generator_path.exists():
            raise ImportError(f"Generator path does not exist: {generator_path}")
        sys.path.insert(0, str(generator_path))
        from generator import SyntheticGenerator
    except ImportError as e:
        print(f"\n✗ Failed to import synthetic generator: {e}")
        print("  Ensure primitives/datasets/v1/synthetic/generator.py exists")
        return 1

    # Build generation parameters
    params = {
        'seed': args.seed
    }

    if args.signal == 'sine_wave':
        params['frequency_hz'] = args.frequency
        params['amplitude_peak'] = args.amplitude
    else:  # pink_noise
        params['amplitude_uv_rms'] = args.amplitude

    # Generate data
    print("Generating data...")
    try:
        gen = SyntheticGenerator()
        result = gen.generate(
            signal_type=args.signal,
            channels=args.channels,
            sample_rate_hz=int(args.sample_rate),
            duration_s=args.duration,
            params=params
        )
    except Exception as e:
        print(f"\n✗ Generation failed: {e}")
        shutil.rmtree(output_dir)  # Clean up
        return 1

    # Handle result (ndarray or file path for high-channel)
    data_path = output_dir / "data.float32"

    if isinstance(result, str):
        # High-channel mode returned temp file - move it
        shutil.move(result, data_path)
        file_size_bytes = data_path.stat().st_size
    else:
        # Low-channel mode returned ndarray - write it
        import numpy as np
        result.tofile(data_path)
        file_size_bytes = data_path.stat().st_size

    # Calculate actual samples
    samples_per_channel = int(args.duration * args.sample_rate)

    # Build reproducibility command
    repro_cmd = (
        f"cortex generate --signal {args.signal} "
        f"--channels {args.channels} "
        f"--duration {args.duration} "
        f"--sample-rate {args.sample_rate} "
        f"--seed {args.seed} "
    )
    if args.signal == 'sine_wave':
        repro_cmd += f"--frequency {args.frequency} "
    repro_cmd += f"--output-dir {args.output_dir}"

    # Build spec.yaml
    spec = {
        'dataset': {
            'name': f"synthetic-{args.signal}-{args.channels}ch",
            'version': 1,
            'type': 'generated',
            'description': f"Synthetic {args.signal} for {args.channels}-channel calibration",
            'generator_primitive': 'primitives/datasets/v1/synthetic',
            'generator_version': 1,
            'generation_timestamp': datetime.utcnow().isoformat() + 'Z'
        },
        'format': {
            'type': 'float32',
            'channels': args.channels,
            'sample_rate_hz': args.sample_rate,
            'window_length': args.window_length,
            'layout': 'interleaved',
            'endian': 'little'
        },
        'recordings': [{
            'id': 'data',
            'path': 'data.float32',
            'duration_seconds': args.duration,
            'samples_per_channel': samples_per_channel,
            'units': 'microvolts (µV)'
        }],
        'generation_parameters': params.copy(),
        'reproducibility': {
            'command': repro_cmd,
            'notes': 'Reproducible with same seed and parameters'
        }
    }
    spec['generation_parameters']['signal_type'] = args.signal
    spec['generation_parameters']['duration_s'] = args.duration

    # Write spec.yaml
    spec_path = output_dir / "spec.yaml"
    with open(spec_path, 'w') as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False)

    # Print success
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(f"✓ Generated dataset primitive: {args.output_dir}/")
    print(f"  Files:        spec.yaml, data.float32")
    print(f"  Data Size:    {file_size_mb:.2f} MB ({file_size_bytes:,} bytes)")
    print(f"  Samples:      {samples_per_channel:,} per channel")
    print()
    print("Usage:")
    print(f"  cortex calibrate --kernel csp --dataset {args.output_dir} --output state.cortex_state")
    print("=" * 80)

    return 0
