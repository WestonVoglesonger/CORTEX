"""Generate synthetic dataset from spec.yaml."""
import sys
from pathlib import Path
from datetime import datetime, timezone
import yaml
import shutil


def setup_parser(parser):
    """Setup argument parser for generate command"""
    parser.add_argument(
        '--spec',
        required=True,
        help='Path to spec.yaml with generation_parameters'
    )


def execute(args):
    """Execute generate command"""
    print("=" * 80)
    print("CORTEX Synthetic Dataset Generator")
    print("=" * 80)

    # Read spec.yaml
    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"\n✗ Spec not found: {args.spec}")
        return 1

    try:
        with open(spec_path) as f:
            spec = yaml.safe_load(f)
    except Exception as e:
        print(f"\n✗ Failed to parse spec: {e}")
        return 1

    # Validate required sections
    fmt = spec.get('format')
    gen_params = spec.get('generation_parameters')

    if not fmt:
        print("\n✗ Spec missing 'format' section")
        return 1
    if not gen_params:
        print("\n✗ Spec missing 'generation_parameters' section")
        return 1

    # Extract generation inputs from spec
    channels = fmt.get('channels')
    sample_rate = fmt.get('sample_rate_hz', 160.0)
    window_length = fmt.get('window_length', 160)
    signal_type = gen_params.get('signal_type')
    duration = gen_params.get('duration_s')
    seed = gen_params.get('seed', 42)

    if channels is None:
        print("\n✗ format.channels is required")
        return 1
    if signal_type is None:
        print("\n✗ generation_parameters.signal_type is required")
        return 1
    if duration is None:
        print("\n✗ generation_parameters.duration_s is required")
        return 1

    # Validate sine requires frequency
    if signal_type == 'sine_wave' and 'frequency_hz' not in gen_params:
        print("\n✗ generation_parameters.frequency_hz required for sine_wave signal")
        return 1

    output_dir = spec_path.parent

    print(f"\nSpec:         {args.spec}")
    print(f"Signal:       {signal_type}")
    print(f"Channels:     {channels}")
    print(f"Duration:     {duration}s")
    print(f"Sample Rate:  {sample_rate} Hz")
    print(f"Seed:         {seed}")
    if signal_type == 'sine_wave':
        print(f"Frequency:    {gen_params.get('frequency_hz')} Hz")
    else:
        print(f"Amplitude:    {gen_params.get('amplitude_uv_rms', 100.0)} µV RMS")
    print()

    # Import generator
    try:
        generator_path = Path(__file__).resolve().parents[3] / 'primitives' / 'datasets' / 'v1' / 'synthetic'
        if not generator_path.exists():
            raise ImportError(f"Generator path does not exist: {generator_path}")
        sys.path.insert(0, str(generator_path))
        from generator import SyntheticGenerator
    except ImportError as e:
        print(f"\n✗ Failed to import synthetic generator: {e}")
        print("  Ensure primitives/datasets/v1/synthetic/generator.py exists")
        return 1

    # Build params for generator (pass through everything from generation_parameters)
    params = {k: v for k, v in gen_params.items() if k not in ('signal_type', 'duration_s')}

    # Generate data
    print("Generating data...")
    try:
        gen = SyntheticGenerator()
        result = gen.generate(
            signal_type=signal_type,
            channels=channels,
            sample_rate_hz=int(sample_rate),
            duration_s=duration,
            params=params
        )
    except Exception as e:
        print(f"\n✗ Generation failed: {e}")
        return 1

    # Write data file next to spec.yaml
    data_path = output_dir / "data.float32"

    if isinstance(result, str):
        shutil.move(result, data_path)
    else:
        result.tofile(data_path)

    file_size_bytes = data_path.stat().st_size
    samples_per_channel = int(duration * sample_rate)

    # Backfill computed fields into spec
    if 'dataset' not in spec:
        spec['dataset'] = {}
    spec['dataset']['type'] = 'generated'
    spec['dataset']['generator_primitive'] = 'primitives/datasets/v1/synthetic'
    spec['dataset']['generation_timestamp'] = datetime.now(timezone.utc).isoformat()

    # Ensure format defaults are written
    fmt['type'] = 'float32'
    fmt['sample_rate_hz'] = sample_rate
    fmt['window_length'] = window_length
    fmt['layout'] = 'interleaved'
    fmt['endian'] = 'little'

    recording = {
        'id': 'data',
        'path': 'data.float32',
        'duration_seconds': duration,
        'samples_per_channel': samples_per_channel,
        'units': 'microvolts (µV)'
    }
    # Preserve user-added fields (e.g., label_pattern) from existing recording
    if spec.get('recordings') and len(spec['recordings']) > 0:
        existing = spec['recordings'][0]
        for key, value in existing.items():
            if key not in recording:
                recording[key] = value
    spec['recordings'] = [recording]

    # Write updated spec.yaml
    with open(spec_path, 'w') as f:
        yaml.dump(spec, f, default_flow_style=False, sort_keys=False)

    # Print success
    file_size_mb = file_size_bytes / (1024 * 1024)
    print(f"✓ Generated dataset: {output_dir}/")
    print(f"  Files:        spec.yaml, data.float32")
    print(f"  Data Size:    {file_size_mb:.2f} MB ({file_size_bytes:,} bytes)")
    print(f"  Samples:      {samples_per_channel:,} per channel")
    print()
    print("Usage:")
    print(f"  cortex calibrate --kernel csp --dataset {output_dir} --output state.cortex_state")
    print("=" * 80)

    return 0
