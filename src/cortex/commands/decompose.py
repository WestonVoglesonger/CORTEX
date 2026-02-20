"""Decompose command - Post-benchmark latency decomposition (SE-5 Step 3).

Fits predicted latency to measured data, decomposing the residual into
I/O overhead (noop baseline), DVFS effects, and scheduling overhead.
Surfaces the decomposition tier from the device primitive.
"""
import json

from cortex.core import ConsoleLogger, RealFileSystemService, YamlConfigLoader
from cortex.utils.analyzer import TelemetryAnalyzer
import numpy as np

from cortex.utils.decomposition import (
    load_device_spec, load_prediction, attribute_latency,
    attribute_latency_distributional,
    PredictionResult, AttributionResult, DistributionalAttribution,
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

    # Reconstruct PredictionResult objects from prediction.json
    tier = pred_data.get('decomposition_tier', 0)
    use_distributional = tier >= 1
    predictions = _load_predictions(pred_data)
    if not predictions:
        print("Error: No predictions found in prediction file")
        return 1

    # Derive device execution latency for distributional path
    has_device_ts = ('device_tstart_ns' in df_real.columns
                     and 'device_tend_ns' in df_real.columns)
    if has_device_ts:
        df_real['device_latency_us'] = (
            df_real['device_tend_ns'] - df_real['device_tstart_ns']
        ) / 1000.0

    # Get noop latencies (full distribution for tier >= 1, scalar for tier 0)
    noop_df = df_real[df_real['plugin'] == 'noop']
    if use_distributional and has_device_ts:
        noop_latencies = noop_df['device_latency_us'].tolist() if not noop_df.empty else []
    else:
        noop_latencies = noop_df['latency_us'].tolist() if not noop_df.empty else []
    noop_baseline_us = float(np.median(noop_latencies)) if noop_latencies else 0.0

    if not noop_latencies:
        print("Warning: No noop kernel in telemetry. I/O baseline set to 0.")

    # Run attribution for each kernel
    results = []
    for pred in predictions:
        kernel_df = df_real[df_real['plugin'] == pred.kernel_name]
        if kernel_df.empty:
            print(f"Warning: No telemetry for kernel '{pred.kernel_name}', skipping")
            continue

        # Distributional path uses device execution time (matches prediction model)
        # Scalar path uses total window time (harness-level view)
        if use_distributional and has_device_ts:
            latencies = kernel_df['device_latency_us'].tolist()
        else:
            latencies = kernel_df['latency_us'].tolist()
        freqs = kernel_df['cpu_freq_mhz'].tolist() if 'cpu_freq_mhz' in kernel_df.columns else None

        if use_distributional and pred.instruction_count is not None and noop_latencies:
            attr = attribute_latency_distributional(pred, latencies, noop_latencies, freqs)
        else:
            attr = attribute_latency(pred, latencies, noop_baseline_us, freqs)
        results.append(attr)

    if not results:
        print("Error: No kernels matched between prediction and telemetry")
        return 1

    # Output — dispatch based on result type
    dev = device_spec.get('device', device_spec)
    has_distributional = any(isinstance(r, DistributionalAttribution) for r in results)

    if args.format == 'json':
        _output_json(results, dev, tier)
    elif args.format == 'markdown':
        if has_distributional:
            md = _generate_markdown_distributional(
                [r for r in results if isinstance(r, DistributionalAttribution)], dev, tier)
        else:
            md = _generate_markdown(results, dev, tier)
        print(md)
    else:
        if has_distributional:
            _output_table_distributional(
                [r for r in results if isinstance(r, DistributionalAttribution)], dev, tier)
        else:
            _output_table(results, dev, tier)

    # Write report if output dir specified
    if args.output:
        _write_report(results, dev, tier, args.output, fs)

    return 0



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
            instruction_count=p.get('instruction_count'),
            probe_freq_hz=p.get('probe_freq_hz'),
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
    has_distributional = any(isinstance(r, DistributionalAttribution) for r in results)
    if has_distributional:
        md = _generate_markdown_distributional(
            [r for r in results if isinstance(r, DistributionalAttribution)], dev, tier)
    else:
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


def _output_table_distributional(results, dev, tier=1):
    """Print distributional decomposition as formatted table with percentiles."""
    print(f"\nDistributional Latency Decomposition [Tier {tier}] — {dev.get('name', 'Unknown Device')}")
    print("=" * 130)
    print(f"{'Kernel':<16} {'':>6} {'Measured':>10} {'Compute':>10} {'Residual':>10} "
          f"{'Noop':>10} {'Net Resid':>10} {'Bound':>10} {'N':>6}")
    print("-" * 130)

    for r in sorted(results, key=lambda x: x.measured_p50_us, reverse=True):
        for label, mval, cval, rval, nval, nrval in [
            ("p50", r.measured_p50_us, r.compute_p50_us, r.residual_p50_us,
             r.noop_p50_us, r.net_residual_p50_us),
            ("p95", r.measured_p95_us, r.compute_p95_us, r.residual_p95_us,
             r.noop_p95_us, r.net_residual_p95_us),
            ("p99", r.measured_p99_us, r.compute_p99_us, r.residual_p99_us,
             r.noop_p99_us, r.net_residual_p99_us),
        ]:
            name_col = r.kernel_name if label == "p50" else ""
            n_col = str(r.n_windows) if label == "p50" else ""
            bound_col = r.bound if label == "p50" else ""
            print(f"{name_col:<16} {label:>6} {mval:>10.1f} {cval:>10.1f} "
                  f"{rval:>10.1f} {nval:>10.1f} {nrval:>10.1f} "
                  f"{bound_col:>10} {n_col:>6}")
        print("-" * 130)

    print("\nCompute = instruction_count / (freq * IPC). Residual = measured - compute.")
    print("Net Resid = residual - noop (quantile subtraction).")


def _generate_markdown_distributional(results, dev, tier=1):
    """Generate markdown report for distributional decomposition."""
    lines = [
        "# Distributional Latency Decomposition Report",
        "",
        f"**Device:** {dev.get('name', 'Unknown')}  ",
        f"**Decomposition Tier:** {tier}  ",
        "",
        "## Distributional Breakdown",
        "",
        "| Kernel | Pct | Measured (us) | Compute (us) | Residual (us) | Noop (us) | Net Residual (us) | Bound | N |",
        "|--------|-----|--------------|-------------|--------------|----------|-------------------|-------|---|",
    ]

    for r in sorted(results, key=lambda x: x.measured_p50_us, reverse=True):
        for label, mval, cval, rval, nval, nrval in [
            ("p50", r.measured_p50_us, r.compute_p50_us, r.residual_p50_us,
             r.noop_p50_us, r.net_residual_p50_us),
            ("p95", r.measured_p95_us, r.compute_p95_us, r.residual_p95_us,
             r.noop_p95_us, r.net_residual_p95_us),
            ("p99", r.measured_p99_us, r.compute_p99_us, r.residual_p99_us,
             r.noop_p99_us, r.net_residual_p99_us),
        ]:
            name = r.kernel_name if label == "p50" else ""
            bound = r.bound if label == "p50" else ""
            n = str(r.n_windows) if label == "p50" else ""
            lines.append(
                f"| {name} | {label} | {mval:.1f} | {cval:.1f} | "
                f"{rval:.1f} | {nval:.1f} | {nrval:.1f} | {bound} | {n} |"
            )

    lines.extend([
        "",
        "## Component Definitions",
        "",
        "- **Compute**: Per-window compute bound = instruction_count / (freq_i * IPC), IPC=1.0",
        "- **Residual**: measured - compute (clamped >= 0)",
        "- **Noop**: Harness overhead distribution",
        "- **Net Residual**: residual - noop (quantile subtraction, clamped >= 0)",
        "",
        "*Generated by `cortex decompose` (Tier 1 distributional)*",
    ])

    return '\n'.join(lines)
