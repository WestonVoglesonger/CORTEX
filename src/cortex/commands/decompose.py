"""Decompose command - Post-benchmark latency decomposition (SE-5 Step 3).

Fits predicted latency to measured data, decomposing the residual into
I/O overhead (noop baseline), DVFS effects, and scheduling overhead.
Surfaces the decomposition tier from the device primitive.
"""
import json

from cortex.core import ConsoleLogger, RealFileSystemService, YamlConfigLoader
from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.utils.decomposition import (
    load_device_spec, load_prediction, attribute_latency,
    PredictionResult, AttributionResult,
)


def setup_parser(parser):
    """Setup argument parser for decompose command."""
    parser.add_argument(
        '--prediction',
        required=True,
        help='Path to prediction.json from cortex predict'
    )
    parser.add_argument(
        '--run-name',
        required=True,
        help='Run name or results directory to analyze'
    )
    parser.add_argument(
        '--device',
        required=True,
        help='Path to device spec YAML'
    )
    parser.add_argument(
        '--output', '-o',
        help='Output directory for decomposition report'
    )
    parser.add_argument(
        '--format',
        choices=['table', 'json', 'markdown'],
        default='table',
        help='Output format (default: table)'
    )


def execute(args):
    """Execute post-benchmark latency decomposition."""
    from cortex.utils.paths import get_run_directory

    fs = RealFileSystemService()
    logger = ConsoleLogger()

    # Load prediction.json
    try:
        pred_data = load_prediction(args.prediction)
    except FileNotFoundError:
        print(f"Error: Prediction file not found: {args.prediction}")
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid prediction JSON: {e}")
        return 1

    # Resolve run directory
    run_name = args.run_name
    if fs.exists(run_name):
        results_dir = run_name
    else:
        results_dir = str(get_run_directory(run_name))
        if not fs.exists(results_dir):
            print(f"Error: Run not found: {run_name}")
            return 1

    # Load device spec
    try:
        device_spec = load_device_spec(args.device)
    except FileNotFoundError:
        print(f"Error: Device spec not found: {args.device}")
        return 1

    # Load telemetry
    analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)
    df = analyzer.load_telemetry(results_dir, prefer_format='ndjson')
    if df is None or df.empty:
        print(f"Error: No telemetry data found in {results_dir}")
        return 1

    # Filter warmup
    df_real = df[df['warmup'] == 0].copy()

    # Extract noop baseline
    noop_baseline_us = _get_noop_baseline(df_real)

    # Reconstruct PredictionResult objects from prediction.json
    tier = pred_data.get('decomposition_tier', 0)
    predictions = _load_predictions(pred_data)
    if not predictions:
        print("Error: No predictions found in prediction file")
        return 1

    # Run attribution for each kernel
    results = []
    for pred in predictions:
        kernel_df = df_real[df_real['plugin'] == pred.kernel_name]
        if kernel_df.empty:
            print(f"Warning: No telemetry for kernel '{pred.kernel_name}', skipping")
            continue

        latencies = kernel_df['latency_us'].tolist()
        freqs = kernel_df['cpu_freq_mhz'].tolist() if 'cpu_freq_mhz' in kernel_df.columns else None

        attr = attribute_latency(pred, latencies, noop_baseline_us, freqs)
        results.append(attr)

    if not results:
        print("Error: No kernels matched between prediction and telemetry")
        return 1

    # Output
    dev = device_spec.get('device', device_spec)
    if args.format == 'json':
        _output_json(results, dev, tier)
    elif args.format == 'markdown':
        md = _generate_markdown(results, dev, tier)
        print(md)
    else:
        _output_table(results, dev, tier)

    # Write report if output dir specified
    if args.output:
        _write_report(results, dev, tier, args.output, fs)

    return 0


def _get_noop_baseline(df):
    """Extract noop median latency as I/O baseline."""
    noop = df[df['plugin'] == 'noop']
    if noop.empty:
        print("Warning: No noop kernel in telemetry. I/O baseline set to 0.")
        return 0.0
    return float(noop['latency_us'].median())


def _load_predictions(pred_data):
    """Reconstruct PredictionResult objects from prediction.json dict."""
    tier = pred_data.get('decomposition_tier', 0)
    results = []
    for p in pred_data.get('predictions', []):
        results.append(PredictionResult(
            kernel_name=p['kernel_name'],
            theoretical_compute_us=p['theoretical_compute_us'],
            theoretical_memory_us=p['theoretical_memory_us'],
            theoretical_io_us=p.get('theoretical_io_us', 0.0),
            theoretical_peak_us=p['theoretical_peak_us'],
            bound=p['bound'],
            operational_intensity=p.get('operational_intensity', 0.0),
            instruction_profile=None,
            source=p.get('source', 'unknown'),
            decomposition_tier=p.get('decomposition_tier', tier),
        ))
    return results


def _output_table(results, dev, tier=0):
    """Print decomposition as formatted table."""
    print(f"\nLatency Decomposition [Tier {tier}] — {dev.get('name', 'Unknown Device')}")
    print("=" * 105)
    print(f"{'Kernel':<16} {'Measured':>10} {'Predicted':>10} {'I/O':>8} "
          f"{'DVFS':>8} {'Sched':>8} {'Throttle':>8} {'Bound':>10}")
    print(f"{'':16} {'(us)':>10} {'(us)':>10} {'(us)':>8} "
          f"{'(us)':>8} {'(us)':>8} {'(%)':>8} {'':>10}")
    print("-" * 105)

    for r in sorted(results, key=lambda x: x.measured_median_us, reverse=True):
        dvfs = f"{r.dvfs_overhead_us:.1f}" if r.dvfs_overhead_us is not None else "N/A"
        print(f"{r.kernel_name:<16} {r.measured_median_us:>10.1f} "
              f"{r.predicted_peak_us:>10.4f} {r.io_overhead_us:>8.1f} "
              f"{dvfs:>8} {r.scheduling_overhead_us:>8.1f} "
              f"{r.throttled_window_pct:>7.1f}% {r.bound:>10}")

    print("-" * 105)
    print("\nI/O = noop baseline. DVFS = frequency-throttled overhead.")
    print("Sched = residual (scheduling, cache, OS jitter).")
    print("Throttle = % windows below nominal CPU frequency.")


def _output_json(results, dev, tier=0):
    """Print decomposition as JSON."""
    output = {
        'device': dev.get('name', 'Unknown'),
        'decomposition_tier': tier,
        'attributions': [],
    }
    for r in results:
        output['attributions'].append({
            'kernel': r.kernel_name,
            'measured_median_us': round(r.measured_median_us, 2),
            'predicted_peak_us': round(r.predicted_peak_us, 6),
            'io_overhead_us': round(r.io_overhead_us, 2),
            'dvfs_overhead_us': round(r.dvfs_overhead_us, 2) if r.dvfs_overhead_us is not None else None,
            'scheduling_overhead_us': round(r.scheduling_overhead_us, 2),
            'nominal_freq_mhz': r.nominal_freq_mhz,
            'throttled_window_pct': round(r.throttled_window_pct, 2),
            'bound': r.bound,
        })
    print(json.dumps(output, indent=2))


def _generate_markdown(results, dev, tier=0):
    """Generate markdown decomposition report."""
    lines = [
        "# Latency Decomposition Report",
        "",
        f"**Device:** {dev.get('name', 'Unknown')}  ",
        f"**Decomposition Tier:** {tier}  ",
        f"**CPU Peak:** {dev.get('cpu_peak_gflops', dev.get('peak_gflops', 'N/A'))} GFLOPS  ",
        f"**Memory BW:** {dev.get('memory_bandwidth_gb_s', 'N/A')} GB/s  ",
        "",
        "## Decomposition Breakdown",
        "",
        "| Kernel | Measured (us) | Predicted (us) | I/O (us) | DVFS (us) | Sched (us) | Throttled % | Bound |",
        "|--------|--------------|----------------|----------|-----------|------------|-------------|-------|",
    ]

    for r in sorted(results, key=lambda x: x.measured_median_us, reverse=True):
        dvfs = f"{r.dvfs_overhead_us:.1f}" if r.dvfs_overhead_us is not None else "N/A"
        lines.append(
            f"| {r.kernel_name} | {r.measured_median_us:.1f} | "
            f"{r.predicted_peak_us:.4f} | {r.io_overhead_us:.1f} | "
            f"{dvfs} | {r.scheduling_overhead_us:.1f} | "
            f"{r.throttled_window_pct:.1f} | {r.bound} |"
        )

    lines.extend([
        "",
        "## Component Definitions",
        "",
        "- **Predicted**: Theoretical minimum from Roofline model (max of compute, memory)",
        "- **I/O**: Noop kernel baseline — harness overhead (scheduling, data copy, syscalls)",
        "- **DVFS**: Overhead from CPU frequency throttling (median at throttled freq - median at nominal)",
        "- **Sched**: Residual (measured - predicted - I/O - DVFS) — OS jitter, cache, other platform effects",
        "- **Throttled %**: Fraction of windows where CPU ran below nominal frequency",
        "",
        "*Generated by `cortex decompose`*",
    ])

    return '\n'.join(lines)


def _write_report(results, dev, tier, output_dir, fs):
    """Write DECOMPOSITION.md report to output directory."""
    md = _generate_markdown(results, dev, tier)
    try:
        if not fs.exists(output_dir):
            fs.makedirs(output_dir, exist_ok=True)
        report_path = f"{output_dir}/DECOMPOSITION.md"
        with fs.open(report_path, 'w') as f:
            f.write(md)
        print(f"\nReport written to: {report_path}")
    except Exception as e:
        print(f"\nWarning: Could not write report: {e}")
