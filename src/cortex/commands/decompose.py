"""Decompose command - Post-benchmark latency characterization (SE-5).

Characterizes kernel latency distributions using roofline classification,
distribution landmarks, and optional PMU enrichment. Every platform gets
a characterization; richer platforms get richer output.
"""
import json

from cortex.core import ConsoleLogger, RealFileSystemService, YamlConfigLoader
from cortex.utils.analyzer import TelemetryAnalyzer

from cortex.utils.decomposition import (
    load_device_spec, load_kernel_specs, characterize_kernel,
    _pmu_unavailable_reason,
)


def setup_parser(parser):
    """Setup argument parser for decompose command."""
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
    """Execute post-benchmark latency characterization."""
    from cortex.utils.paths import get_run_directory

    fs = RealFileSystemService()
    logger = ConsoleLogger()

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

    # Load kernel specs
    kernel_specs = load_kernel_specs()

    # Load telemetry
    analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)
    df = analyzer.load_telemetry(results_dir, prefer_format='ndjson')
    if df is None or df.empty:
        print(f"Error: No telemetry data found in {results_dir}")
        return 1

    # Filter warmup
    df_real = df[df['warmup'] == 0].copy()

    # Device timestamps — present for native adapters (same clock domain)
    has_device_ts = ('device_tstart_ns' in df_real.columns
                     and 'device_tend_ns' in df_real.columns)
    if has_device_ts:
        df_real['device_latency_us'] = (
            df_real['device_tend_ns'] - df_real['device_tstart_ns']
        ) / 1000.0

    # Noop — cross-validation only, not load-bearing
    # Use device-side timing when available (excludes adapter protocol overhead)
    noop_df = df_real[df_real['plugin'] == 'noop']
    if not noop_df.empty and has_device_ts:
        noop_latencies = noop_df['device_latency_us'].tolist()
    elif not noop_df.empty:
        noop_latencies = noop_df['latency_us'].tolist()
    else:
        noop_latencies = None

    # PMU detection
    has_pmu = ('pmu_cycle_count' in df_real.columns
               and 'pmu_instruction_count' in df_real.columns
               and df_real['pmu_cycle_count'].sum() > 0)
    has_stall = (has_pmu
                 and 'pmu_backend_stall_cycles' in df_real.columns
                 and df_real['pmu_backend_stall_cycles'].sum() > 0)

    if not has_pmu:
        reason = _pmu_unavailable_reason()
        # Strip the "no PMU data" prefix — we provide our own framing
        hint = reason.replace("no PMU data", "").strip(" ()")
        if hint:
            print(f"\nPMU data: Not available. {hint.capitalize()}.")
        else:
            print("\nPMU data: Not available.")
        print("Latency characterization proceeds without compute/memory decomposition.\n")

    # Extract benchmark parameters from telemetry
    window_length = int(df_real['W'].iloc[0]) if 'W' in df_real.columns and not df_real.empty else 160
    channels = int(df_real['C'].iloc[0]) if 'C' in df_real.columns and not df_real.empty else 64

    # Discover kernel names (exclude noop)
    kernel_names = [name for name in df_real['plugin'].unique() if name != 'noop']

    # Single characterization path
    results = []
    for plugin_name in kernel_names:
        kernel_df = df_real[df_real['plugin'] == plugin_name]

        if kernel_df.empty:
            continue

        device_lats = (kernel_df['device_latency_us'].tolist()
                       if has_device_ts else None)

        result = characterize_kernel(
            plugin_name,
            outer_latencies_us=kernel_df['latency_us'].tolist(),
            device_latencies_us=device_lats,
            device_spec=device_spec,
            kernel_specs=kernel_specs,
            window_length=window_length,
            channels=channels,
            noop_latencies_us=noop_latencies,
            per_window_cycle_counts=(kernel_df['pmu_cycle_count'].tolist()
                                     if has_pmu else None),
            per_window_instruction_counts=(kernel_df['pmu_instruction_count'].tolist()
                                           if has_pmu else None),
            per_window_backend_stall_counts=(kernel_df['pmu_backend_stall_cycles'].tolist()
                                             if has_stall else None),
        )
        if result:
            results.append(result)

    if not results:
        print("Error: No kernels could be characterized (missing specs?)")
        return 1

    dev = device_spec.get('device', device_spec)
    _output_characterization(results, dev, args.format)

    # Write report if output dir specified
    if args.output:
        _write_report(results, dev, args.output, fs)

    return 0


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _output_characterization(results, dev, fmt):
    """Dispatch to table/json/markdown formatter."""
    if fmt == 'json':
        _output_json(results, dev)
    elif fmt == 'markdown':
        print(_generate_markdown(results, dev))
    else:
        _output_table(results, dev)


def _output_table(results, dev):
    """Print characterization as formatted table."""
    device_name = dev.get('name', 'Unknown Device')
    print(f"\nLatency Characterization — {device_name}")
    print("=" * 68)

    for r in results:
        prov = r.provenance
        timing_src = prov.get('best_us', 'measured/timing')

        print(f"\nKernel: {r.kernel_name}")
        print(f"  Bound: {r.bound} (OI={r.operational_intensity:.1f})"
              f"{'':>20}[{prov.get('bound', 'estimated/roofline')}]")

        ws_kb = r.working_set_bytes / 1024
        l1_info = ""
        if r.fits_in_l1 is not None:
            l1_kb = dev.get('l1_cache_kb', '?')
            l1_info = f" (fits in L1: {l1_kb} KB)" if r.fits_in_l1 else f" (exceeds L1: {l1_kb} KB)"
        print(f"  Working set: {ws_kb:.0f} KB{l1_info}"
              f"{'':>4}[{prov.get('working_set_bytes', 'estimated/static')}]")

        print(f"\n  Floor (roofline): {r.roofline_floor_us:>8.4f} us"
              f"{'':>14}[{prov.get('roofline_floor_us', 'estimated/roofline')}]")
        print(f"  Best (p5):        {r.best_us:>8.1f} us"
              f"{'':>14}[{timing_src}]")
        print(f"  Typical (p50):    {r.typical_us:>8.1f} us"
              f"{'':>14}[{timing_src}]")
        print(f"  Tail (p99):       {r.tail_us:>8.1f} us"
              f"{'':>14}[{timing_src}]")

        print(f"\n  Best-to-typical gap: {r.best_to_typical_gap_us:>5.1f} us"
              f"{'':>11}[{timing_src}]")
        print(f"  Tail risk:           {r.tail_risk_us:>5.1f} us"
              f"{'':>11}[{timing_src}]")

        # PMU enrichment
        if r.ipc is not None:
            print(f"\n  IPC:                 {r.ipc:>5.1f}"
                  f"{'':>16}[{prov.get('ipc', 'measured/PMU')}]")
        elif "ipc" in r.unavailable:
            print(f"\n  IPC:                   N/A"
                  f"{'':>16}[{r.unavailable['ipc']}]")

        if r.effective_freq_ghz is not None:
            print(f"  Effective freq:      {r.effective_freq_ghz:>5.1f} GHz"
                  f"{'':>12}[{prov.get('effective_freq_ghz', 'measured/PMU+timing')}]")
        elif "effective_freq_ghz" in r.unavailable:
            print(f"  Effective freq:        N/A"
                  f"{'':>12}[{r.unavailable['effective_freq_ghz']}]")

        if r.frequency_tax_pct is not None:
            print(f"  Frequency tax:       {r.frequency_tax_pct:>5.1f}%"
                  f"{'':>13}[{prov.get('frequency_tax_pct', 'measured/PMU+timing')}]")
        elif "frequency_tax_pct" in r.unavailable:
            print(f"  Frequency tax:         N/A"
                  f"{'':>13}[{r.unavailable['frequency_tax_pct']}]")

        # Kernel time decomposition (compute vs memory stall)
        if r.backend_stall_pct is not None:
            compute_pct = 100 - r.backend_stall_pct
            print(f"\n  Compute time:        {r.compute_time_us:>5.1f} us ({compute_pct:>4.1f}%)"
                  f"  [{prov.get('compute_time_us', 'measured/PMU+timing')}]")
            print(f"  Memory stall:        {r.memory_stall_time_us:>5.1f} us ({r.backend_stall_pct:>4.1f}%)"
                  f"  [{prov.get('memory_stall_time_us', 'measured/PMU+timing')}]")
        elif "backend_stall_pct" in r.unavailable:
            print(f"\n  Compute/memory split:  N/A"
                  f"{'':>10}[{r.unavailable['backend_stall_pct']}]")

        # Noop cross-validation
        if r.noop_p50_us is not None:
            print(f"\n  Noop (p50):          {r.noop_p50_us:>5.1f} us"
                  f"{'':>11}[{prov.get('noop_p50_us', 'measured/timing/noop')}]")

        print(f"\n  N windows: {r.n_windows}")
        print("-" * 68)


def _output_json(results, dev):
    """Print characterization as JSON."""
    output = {
        'device': dev.get('name', 'Unknown'),
        'characterizations': [],
    }
    for r in results:
        entry = {
            'kernel': r.kernel_name,
            'bound': r.bound,
            'operational_intensity': round(r.operational_intensity, 4),
            'working_set_bytes': r.working_set_bytes,
            'fits_in_l1': r.fits_in_l1,
            'roofline_floor_us': round(r.roofline_floor_us, 6),
            'roofline_compute_us': round(r.roofline_compute_us, 6),
            'roofline_memory_us': round(r.roofline_memory_us, 6),
            'best_us': round(r.best_us, 2),
            'typical_us': round(r.typical_us, 2),
            'tail_us': round(r.tail_us, 2),
            'best_to_typical_gap_us': round(r.best_to_typical_gap_us, 2),
            'tail_risk_us': round(r.tail_risk_us, 2),
            'noop_p50_us': round(r.noop_p50_us, 2) if r.noop_p50_us is not None else None,
            'ipc': round(r.ipc, 3) if r.ipc is not None else None,
            'effective_freq_ghz': round(r.effective_freq_ghz, 3) if r.effective_freq_ghz is not None else None,
            'frequency_tax_pct': round(r.frequency_tax_pct, 2) if r.frequency_tax_pct is not None else None,
            'backend_stall_pct': round(r.backend_stall_pct, 2) if r.backend_stall_pct is not None else None,
            'compute_time_us': round(r.compute_time_us, 2) if r.compute_time_us is not None else None,
            'memory_stall_time_us': round(r.memory_stall_time_us, 2) if r.memory_stall_time_us is not None else None,
            'n_windows': r.n_windows,
            'provenance': r.provenance,
            'unavailable': r.unavailable,
        }
        output['characterizations'].append(entry)
    print(json.dumps(output, indent=2))


def _generate_markdown(results, dev):
    """Generate markdown characterization report."""
    lines = [
        "# Latency Characterization Report",
        "",
        f"**Device:** {dev.get('name', 'Unknown')}  ",
        f"**CPU Peak:** {dev.get('cpu_peak_gflops', dev.get('peak_gflops', 'N/A'))} GFLOPS  ",
        f"**Memory BW:** {dev.get('memory_bandwidth_gb_s', 'N/A')} GB/s  ",
        "",
    ]

    for r in results:
        prov = r.provenance
        timing_src = prov.get('best_us', 'measured/timing')

        lines.extend([
            f"## {r.kernel_name}",
            "",
            f"| Metric | Value | Provenance |",
            f"|--------|-------|------------|",
            f"| Bound | {r.bound} (OI={r.operational_intensity:.1f}) | {prov.get('bound', 'estimated/roofline')} |",
            f"| Working set | {r.working_set_bytes / 1024:.0f} KB | {prov.get('working_set_bytes', 'estimated/static')} |",
            f"| Floor (roofline) | {r.roofline_floor_us:.4f} us | {prov.get('roofline_floor_us', 'estimated/roofline')} |",
            f"| Best (p5) | {r.best_us:.1f} us | {timing_src} |",
            f"| Typical (p50) | {r.typical_us:.1f} us | {timing_src} |",
            f"| Tail (p99) | {r.tail_us:.1f} us | {timing_src} |",
            f"| Best-to-typical gap | {r.best_to_typical_gap_us:.1f} us | {timing_src} |",
            f"| Tail risk | {r.tail_risk_us:.1f} us | {timing_src} |",
        ])

        if r.ipc is not None:
            lines.append(f"| IPC | {r.ipc:.1f} | {prov.get('ipc', 'measured/PMU')} |")
        if r.effective_freq_ghz is not None:
            lines.append(f"| Effective freq | {r.effective_freq_ghz:.1f} GHz | {prov.get('effective_freq_ghz', 'measured/PMU+timing')} |")
        if r.frequency_tax_pct is not None:
            lines.append(f"| Frequency tax | {r.frequency_tax_pct:.1f}% | {prov.get('frequency_tax_pct', 'measured/PMU+timing')} |")
        if r.backend_stall_pct is not None:
            compute_pct = 100 - r.backend_stall_pct
            lines.append(f"| Compute time | {r.compute_time_us:.1f} us ({compute_pct:.1f}%) | {prov.get('compute_time_us', 'measured/PMU+timing')} |")
            lines.append(f"| Memory stall | {r.memory_stall_time_us:.1f} us ({r.backend_stall_pct:.1f}%) | {prov.get('memory_stall_time_us', 'measured/PMU+timing')} |")
        if r.noop_p50_us is not None:
            lines.append(f"| Noop (p50) | {r.noop_p50_us:.1f} us | {prov.get('noop_p50_us', 'measured/timing/noop')} |")

        lines.extend([
            f"| N windows | {r.n_windows} | |",
            "",
        ])

    lines.append("*Generated by `cortex decompose`*")

    return '\n'.join(lines)


def _write_report(results, dev, output_dir, fs):
    """Write CHARACTERIZATION.md report to output directory."""
    md = _generate_markdown(results, dev)
    try:
        if not fs.exists(output_dir):
            fs.mkdir(output_dir, parents=True, exist_ok=True)
        report_path = f"{output_dir}/CHARACTERIZATION.md"
        with fs.open(report_path, 'w') as f:
            f.write(md)
        print(f"\nReport written to: {report_path}")
    except Exception as e:
        print(f"\nWarning: Could not write report: {e}")
