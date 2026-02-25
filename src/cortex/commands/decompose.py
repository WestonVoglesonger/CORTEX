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
    attribute_tail_latency, TailAttribution, TailFactor,
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
    parser.add_argument(
        '--tail-percentile', type=int, default=95,
        help='Percentile threshold for tail windows (default: 95)'
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
    noop_df = df_real[df_real['plugin'] == 'noop']
    noop_latencies = noop_df['latency_us'].tolist() if not noop_df.empty else None

    # PMU detection
    has_pmu = ('pmu_cycle_count' in df_real.columns
               and 'pmu_instruction_count' in df_real.columns
               and df_real['pmu_cycle_count'].sum() > 0)
    has_stall = (has_pmu
                 and 'pmu_backend_stall_cycles' in df_real.columns
                 and df_real['pmu_backend_stall_cycles'].sum() > 0)

    # Extract benchmark parameters from telemetry
    window_length = int(df_real['W'].iloc[0]) if 'W' in df_real.columns and not df_real.empty else 160
    channels = int(df_real['C'].iloc[0]) if 'C' in df_real.columns and not df_real.empty else 64

    # Discover kernel names (exclude noop)
    kernel_names = [name for name in df_real['plugin'].unique() if name != 'noop']

    # Single characterization path
    results = []
    tail_attributions = {}
    tail_percentile = getattr(args, 'tail_percentile', 95)
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

        # Tail-latency attribution (SE-7)
        tail_attr = attribute_tail_latency(
            df_real, plugin_name,
            tail_percentile=tail_percentile,
            device_spec=device_spec,
        )
        tail_attributions[plugin_name] = tail_attr

    if not results:
        print("Error: No kernels could be characterized (missing specs?)")
        return 1

    dev = device_spec.get('device', device_spec)
    _output_characterization(results, dev, args.format, tail_attributions)

    # Write report if output dir specified
    if args.output:
        _write_report(results, dev, args.output, fs, tail_attributions)

    return 0


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _output_characterization(results, dev, fmt, tail_attributions=None):
    """Dispatch to table/json/markdown formatter."""
    tail_attributions = tail_attributions or {}
    if fmt == 'json':
        _output_json(results, dev, tail_attributions)
    elif fmt == 'markdown':
        print(_generate_markdown(results, dev, tail_attributions))
    else:
        _output_table(results, dev, tail_attributions)


def _output_table(results, dev, tail_attributions=None):
    """Print characterization as formatted table."""
    tail_attributions = tail_attributions or {}
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

        # Tail-latency attribution (SE-7)
        ta = tail_attributions.get(r.kernel_name)
        if ta and ta.n_total_windows > 0:
            _output_tail_attribution_table(ta)

        print("-" * 68)


def _output_tail_attribution_table(ta):
    """Print tail-latency attribution section in table format."""
    print(f"\n  Tail-Latency Attribution (P{ta.tail_percentile})")
    print(f"  Tail factor: {ta.tail_factor:.1f}x (P99/P50)")
    verdict_label = {
        "platform": "Platform-dominated",
        "algorithmic": "Algorithmic-dominated",
        "mixed": "Mixed",
    }.get(ta.dominant_cause, ta.dominant_cause)
    print(f"  Verdict: {verdict_label} ({ta.confidence} confidence)")
    if ta.factors:
        print(f"    {ta.platform_explained_pct:.0%} of tail windows have platform anomalies")
        print(f"    {ta.algorithmic_pct:.0%} purely algorithmic")
        print()
        print(f"    {'Factor':<18} {'Tail prev.':<12} {'Base prev.':<12} {'Enrichment':<12} {'Threshold':<18}")
        for f in ta.factors:
            enr = f"\u221e" if f.enrichment == float('inf') else f"{f.enrichment:.1f}x"
            direction = "< " if f.direction == "low" else "> "
            if f.name == "backend_stalls":
                thr_str = f"{direction}{f.threshold:.0f}% cycles"
            elif f.name == "cpu_freq":
                thr_str = f"{direction}{f.threshold:.0f} MHz"
            elif f.name == "osnoise":
                thr_str = f"{direction}{f.threshold:.0f} ns"
            else:
                thr_str = f"{direction}{f.threshold}"
            print(f"    {f.name:<18} {f.tail_prevalence:<12.0%} {f.base_prevalence:<12.0%} {enr:<12} {thr_str:<18}")


def _output_json(results, dev, tail_attributions=None):
    """Print characterization as JSON."""
    tail_attributions = tail_attributions or {}
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
        ta = tail_attributions.get(r.kernel_name)
        if ta:
            entry['tail_attribution'] = {
                'tail_percentile': ta.tail_percentile,
                'tail_factor': round(ta.tail_factor, 3),
                'p50_us': round(ta.p50_us, 2),
                'p99_us': round(ta.p99_us, 2),
                'dominant_cause': ta.dominant_cause,
                'confidence': ta.confidence,
                'n_tail_windows': ta.n_tail_windows,
                'n_total_windows': ta.n_total_windows,
                'platform_explained_pct': round(ta.platform_explained_pct, 4),
                'algorithmic_pct': round(ta.algorithmic_pct, 4),
                'factors': [
                    {
                        'name': f.name,
                        'tail_prevalence': round(f.tail_prevalence, 4),
                        'base_prevalence': round(f.base_prevalence, 4),
                        'enrichment': None if f.enrichment == float('inf') else round(f.enrichment, 3),
                        'threshold': round(f.threshold, 2),
                        'direction': f.direction,
                    }
                    for f in ta.factors
                ],
            }
        output['characterizations'].append(entry)
    print(json.dumps(output, indent=2))


def _generate_markdown(results, dev, tail_attributions=None):
    """Generate markdown characterization report."""
    tail_attributions = tail_attributions or {}
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

        # Tail-latency attribution (SE-7)
        ta = tail_attributions.get(r.kernel_name)
        if ta and ta.n_total_windows > 0:
            lines.extend(_generate_tail_attribution_markdown(ta))
            lines.append("")

    lines.append("*Generated by `cortex decompose`*")

    return '\n'.join(lines)


def _generate_tail_attribution_markdown(ta):
    """Generate markdown lines for tail-latency attribution section."""
    lines = []
    verdict_label = {
        "platform": "Platform-dominated",
        "algorithmic": "Algorithmic-dominated",
        "mixed": "Mixed",
    }.get(ta.dominant_cause, ta.dominant_cause)

    lines.append(f"### Tail-Latency Attribution")
    lines.append("")
    lines.append(f"Tail factor: {ta.tail_factor:.1f}x (P99/P50)  ")
    lines.append(f"Verdict: {verdict_label} ({ta.confidence} confidence)  ")

    if ta.factors:
        base_avg = sum(f.base_prevalence for f in ta.factors) / len(ta.factors) if ta.factors else 0
        lines.append(
            f"  - {ta.platform_explained_pct:.0%} of tail windows have platform anomalies"
        )
        lines.append(
            f"  - {ta.algorithmic_pct:.0%} purely algorithmic (no platform anomalies detected)"
        )
        lines.append("")
        lines.append("#### Platform Factors")
        lines.append("")
        lines.append("| Factor | Tail prev. | Base prev. | Enrichment | Threshold |")
        lines.append("|--------|------------|------------|------------|-----------|")
        for f in ta.factors:
            enr = "\u221e" if f.enrichment == float('inf') else f"{f.enrichment:.1f}x"
            direction = "< " if f.direction == "low" else "> "
            if f.name == "backend_stalls":
                thr_str = f"{direction}{f.threshold:.0f}% cycles"
            elif f.name == "cpu_freq":
                thr_str = f"{direction}{f.threshold:.0f} MHz"
            elif f.name == "osnoise":
                thr_str = f"{direction}{f.threshold:.0f} ns"
            else:
                thr_str = f"{direction}{f.threshold}"
            label = {"cpu_freq": "Low CPU freq", "osnoise": "High osnoise",
                     "backend_stalls": "Backend stalls"}.get(f.name, f.name)
            lines.append(
                f"| {label} | {f.tail_prevalence:.0%} | {f.base_prevalence:.0%} | {enr} | {thr_str} |"
            )
    elif "insufficient" in ta.dominant_cause:
        lines.append(f"  - {ta.dominant_cause}")
    else:
        lines.append("  - No platform data available for factor analysis")

    return lines


def _write_report(results, dev, output_dir, fs, tail_attributions=None):
    """Write CHARACTERIZATION.md report to output directory."""
    md = _generate_markdown(results, dev, tail_attributions)
    try:
        if not fs.exists(output_dir):
            fs.mkdir(output_dir, parents=True, exist_ok=True)
        report_path = f"{output_dir}/CHARACTERIZATION.md"
        with fs.open(report_path, 'w') as f:
            f.write(md)
        print(f"\nReport written to: {report_path}")
    except Exception as e:
        print(f"\nWarning: Could not write report: {e}")
