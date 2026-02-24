"""Predict command - Static pre-benchmark latency prediction (SE-5 Step 1).

Replaces the old `decompose` command. Uses spec.yaml per-sample annotations
and device Roofline model to predict latency before benchmarking. Optionally
attaches instruction profile from objdump/otool as supplementary metadata.
"""
import json

from cortex.utils.decomposition import (
    RooflineDecomposer, load_device_spec, load_kernel_specs,
    save_prediction, PredictionResult,
)
from cortex.utils.device import resolve_device, validate_capabilities
from cortex.utils.discovery import discover_kernels


def setup_parser(parser):
    """Setup argument parser for predict command."""
    parser.add_argument(
        '--device',
        help='Path to device spec YAML (optional if auto-detect works)'
    )
    parser.add_argument(
        '--kernel',
        help='Single kernel to predict'
    )
    parser.add_argument(
        '--chain',
        help='Comma-separated kernel names for chain prediction'
    )
    parser.add_argument(
        '--config',
        action='store_true',
        help='Read kernel list from config plugins'
    )
    parser.add_argument(
        '--output', '-o',
        help='Write prediction.json to this path'
    )
    parser.add_argument(
        '--format',
        choices=['table', 'json'],
        default='table',
        help='Output format (default: table)'
    )
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


def execute(args):
    """Execute static latency prediction."""
    # Step 1: Load device spec
    device_arg = getattr(args, 'device', None)
    device_spec = resolve_device(device_arg)
    if device_spec is None:
        if device_arg:
            print(f"Error: Device not found: {device_arg}")
        else:
            print("Error: --device is required.")
            print("Available: " + ", ".join(
                p.stem for p in sorted(Path("primitives/devices").glob("*.yaml"))
            ) if Path("primitives/devices").exists() else "")
            print("See SDK docs for creating a device spec for your hardware.")
        return 1
    device_spec = validate_capabilities(device_spec)
    dev = device_spec.get('device', device_spec)
    print(f"Device: {dev.get('name', 'Unknown')}")

    # Step 2: Determine kernel list
    kernel_names = _resolve_kernel_list(args)
    if kernel_names is None:
        return 1

    if not kernel_names:
        print("Error: No kernels found to predict")
        return 1

    # Step 3: Load kernel specs and create decomposer
    kernel_specs = load_kernel_specs()
    decomposer = RooflineDecomposer(device_spec, kernel_specs)

    # Step 4: Run predictions
    is_chain = hasattr(args, 'chain') and args.chain
    if is_chain:
        chain_result = decomposer.predict_chain(
            kernel_names,
            window_length=args.window_length,
            channels=args.channels,
        )
        if chain_result is None or not chain_result.stages:
            print("Error: No predictions available for chain kernels")
            return 1
        results = chain_result.stages
    else:
        results = decomposer.predict_all(
            kernel_names,
            window_length=args.window_length,
            channels=args.channels,
        )

    if not results:
        print("Error: No kernels with sufficient data for prediction")
        return 1

    # Step 5: Output
    if args.format == 'json':
        _output_json(results, device_spec, is_chain)
    else:
        _output_table(results, device_spec, is_chain)

    # Step 6: Write prediction.json if requested
    if hasattr(args, 'output') and args.output:
        params = {
            "window_length": args.window_length,
            "channels": args.channels,
            "dtype_bytes": 4,
        }
        if is_chain:
            params["chain"] = [r.kernel_name for r in results]
        save_prediction(results, device_spec, params, args.output)
        print(f"\nPrediction saved: {args.output}")

    return 0


def _resolve_kernel_list(args):
    """Determine which kernels to predict.

    Returns list of kernel names, or None on error.
    """
    if hasattr(args, 'kernel') and args.kernel:
        return [args.kernel]

    if hasattr(args, 'chain') and args.chain:
        names = [k.strip() for k in args.chain.split(',') if k.strip()]
        if len(names) < 2:
            print("Error: --chain requires at least 2 kernel names")
            return None
        # Validate chain dimensions
        from cortex.utils.chain import validate_chain
        valid, error = validate_chain(names)
        if not valid:
            print(f"Error: Chain validation failed: {error}")
            return None
        return names

    if hasattr(args, 'config') and args.config:
        from cortex.utils.config import load_base_config
        try:
            config = load_base_config()
        except Exception as e:
            print(f"Error loading config: {e}")
            return None
        plugins = config.get('plugins', [])
        return [p['name'] for p in plugins if p.get('status') == 'ready']

    # Default: auto-discover all built kernels
    kernels = discover_kernels()
    return [k['name'] for k in kernels if k.get('built')]


def _output_table(results, device_spec, is_chain=False):
    """Print prediction as formatted table."""
    dev = device_spec.get('device', device_spec)
    mode = "Chain Prediction" if is_chain else "Latency Prediction"
    print(f"\n{mode} — {dev.get('name', 'Unknown Device')}")
    print("=" * 90)
    print(f"{'Kernel':<16} {'Compute':>10} {'Memory':>10} {'Peak':>10} "
          f"{'Bound':>10} {'OI':>8} {'Source':>10}")
    print(f"{'':16} {'(us)':>10} {'(us)':>10} {'(us)':>10} "
          f"{'':>10} {'F/B':>8} {'':>10}")
    print("-" * 90)

    for r in results:
        print(f"{r.kernel_name:<16} {r.theoretical_compute_us:>10.4f} "
              f"{r.theoretical_memory_us:>10.4f} {r.theoretical_peak_us:>10.4f} "
              f"{r.bound:>10} {r.operational_intensity:>8.2f} "
              f"{r.source:>10}")

    print("-" * 90)

    if is_chain:
        cumulative = sum(r.theoretical_peak_us for r in results)
        print(f"{'CUMULATIVE':<16} {'':>10} {'':>10} {cumulative:>10.4f}")
        print("\nNote: Inter-kernel overhead not included in cumulative estimate.")

    print("\nSource: pmu = hardware PMU instruction count, spec.yaml = per-sample annotation")


def _output_json(results, device_spec, is_chain=False):
    """Print prediction as JSON."""
    dev = device_spec.get('device', device_spec)
    output = {
        'device': dev.get('name', 'Unknown'),
        'mode': 'chain' if is_chain else 'individual',
        'predictions': [],
    }
    for r in results:
        entry = {
            'kernel': r.kernel_name,
            'theoretical_compute_us': round(r.theoretical_compute_us, 6),
            'theoretical_memory_us': round(r.theoretical_memory_us, 6),
            'theoretical_peak_us': round(r.theoretical_peak_us, 6),
            'bound': r.bound,
            'operational_intensity': round(r.operational_intensity, 6),
            'source': r.source,
        }
        output['predictions'].append(entry)

    if is_chain:
        output['cumulative_peak_us'] = round(
            sum(r.theoretical_peak_us for r in results), 6
        )

    print(json.dumps(output, indent=2))
