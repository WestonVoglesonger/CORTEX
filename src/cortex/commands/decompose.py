"""Decompose command - Post-benchmark latency characterization (SE-5/SE-7).

Characterizes kernel latency distributions using distribution landmarks,
optional PMU enrichment, and tail-latency attribution.
Every platform gets a characterization; richer platforms get richer output.
"""
import json
from dataclasses import asdict

from cortex.core import ConsoleLogger, RealFileSystemService
from cortex.utils.analyzer import TelemetryAnalyzer

from cortex.utils.decomposition import (
    load_device_spec, characterize_kernel,
    attribute_tail, _pmu_unavailable_reason,
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
        required=False,
        default=None,
        help='Path to device spec YAML (optional, enriches PMU analysis)'
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

    # Load device spec (optional)
    if args.device:
        try:
            device_spec = load_device_spec(args.device)
        except FileNotFoundError:
            print(f"Error: Device spec not found: {args.device}")
            return 1
    else:
        device_spec = {}

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

    # OS noise detection
    has_osnoise = ('osnoise_total_ns' in df_real.columns
                   and df_real['osnoise_total_ns'].sum() > 0)

    # CPU frequency per window (may be all zeros on macOS)
    has_cpu_freq = ('freq_mhz' in df_real.columns
                    and df_real['freq_mhz'].sum() > 0)

    if not has_pmu:
        reason = _pmu_unavailable_reason()
        # Strip the "no PMU data" prefix — we provide our own framing
        hint = reason.replace("no PMU data", "").strip(" ()")
        if hint:
            print(f"\nPMU data: Not available. {hint.capitalize()}.")
        else:
            print("\nPMU data: Not available.")
        print("Latency characterization proceeds without compute/memory decomposition.\n")

    # Discover kernel names (exclude noop)
    kernel_names = [name for name in df_real['plugin'].unique() if name != 'noop']

    # Characterization + tail attribution per kernel
    results = []          # (CharacterizationResult, TailAttribution) tuples
    for plugin_name in kernel_names:
        kernel_df = df_real[df_real['plugin'] == plugin_name]

        if kernel_df.empty:
            continue

        outer_lats = kernel_df['latency_us'].tolist()
        device_lats = (kernel_df['device_latency_us'].tolist()
                       if has_device_ts else None)
        cycle_counts = (kernel_df['pmu_cycle_count'].tolist()
                        if has_pmu else None)
        insn_counts = (kernel_df['pmu_instruction_count'].tolist()
                       if has_pmu else None)
        stall_counts = (kernel_df['pmu_backend_stall_cycles'].tolist()
                        if has_stall else None)

        # Best-available latency array for attribution (device > outer)
        attr_lats = device_lats if device_lats else outer_lats

        char_result = characterize_kernel(
            plugin_name,
            outer_latencies_us=outer_lats,
            device_latencies_us=device_lats,
            device_spec=device_spec,
            noop_latencies_us=noop_latencies,
            per_window_cycle_counts=cycle_counts,
            per_window_instruction_counts=insn_counts,
            per_window_backend_stall_counts=stall_counts,
        )

        # Tail attribution (SE-7)
        tail_result = attribute_tail(
            plugin_name,
            latencies_us=attr_lats,
            noop_latencies_us=noop_latencies,
            per_window_freq_mhz=(kernel_df['freq_mhz'].tolist()
                                     if has_cpu_freq else None),
            per_window_osnoise_ns=(kernel_df['osnoise_total_ns'].tolist()
                                   if has_osnoise else None),
            per_window_cycle_counts=cycle_counts,
            per_window_backend_stall_counts=stall_counts,
        )

        if char_result and tail_result:
            results.append((char_result, tail_result))

    if not results:
        print("Error: No kernels could be characterized (no telemetry data?)")
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

    for r, ta in results:
        prov = r.provenance
        timing_src = prov.get('best_us', 'measured/timing')

        print(f"\nKernel: {r.kernel_name}")
        print(f"\n  Best (p5):        {r.best_us:>8.1f} us"
              f"{'':>14}[{timing_src}]")
        print(f"  Typical (p50):    {r.typical_us:>8.1f} us"
              f"{'':>14}[{timing_src}]")
        print(f"  Tail (p99):       {r.tail_us:>8.1f} us"
              f"{'':>14}[{timing_src}]")

        print(f"\n  Best-to-typical gap: {r.best_to_typical_gap_us:>5.1f} us"
              f"{'':>11}[{timing_src}]")
        print(f"  Tail risk:           {r.tail_risk_us:>5.1f} us"
              f"{'':>11}[{timing_src}]")

        # Tail attribution (SE-7) — always show Tier 1
        _print_tail_attribution(ta)

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

        # Kernel time decomposition (compute vs backend stall)
        if r.backend_stall_pct is not None:
            compute_pct = 100 - r.backend_stall_pct
            print(f"\n  Compute time:        {r.compute_time_us:>5.1f} us ({compute_pct:>4.1f}%)"
                  f"  [{prov.get('compute_time_us', 'measured/PMU+timing')}]")
            print(f"  Backend stall:       {r.memory_stall_time_us:>5.1f} us ({r.backend_stall_pct:>4.1f}%)"
                  f"  [{prov.get('memory_stall_time_us', 'measured/PMU+timing')}]")
            print(f"    (includes memory, data dependency, and port contention stalls)")
        elif "backend_stall_pct" in r.unavailable:
            print(f"\n  Compute/stall split:   N/A"
                  f"{'':>10}[{r.unavailable['backend_stall_pct']}]")

        # Noop cross-validation
        if r.noop_p50_us is not None:
            print(f"\n  Noop (p50):          {r.noop_p50_us:>5.1f} us"
                  f"{'':>11}[{prov.get('noop_p50_us', 'measured/timing/noop')}]")

        print(f"\n  N windows: {r.n_windows}")
        print("-" * 68)


def _fmt_pvalue(p, prefix="p="):
    """Format a p-value for display (e.g. 'p=0.032' or 'p<0.001').

    Args:
        p: The p-value.
        prefix: Text before the value. Use 'p=' for inline, '' for table cells.
    """
    if p >= 0.001:
        return f"{prefix}{p:.3g}"
    return f"{prefix.rstrip('=')}<0.001" if prefix else "<0.001"


def _print_tail_attribution(ta):
    """Print tail attribution section for a single kernel."""
    print(f"\n  Tail ratio (P99/P50): {ta.tail_ratio:>5.1f}x"
          f"{'':>11}[{ta.provenance.get('tail_ratio', 'measured/timing')}]")
    if ta.normalized_ratio is not None:
        print(f"  Normalized (vs noop): {ta.normalized_ratio:>5.1f}x"
              f"{'':>11}[{ta.provenance.get('normalized_ratio', 'measured/timing')}]")
    print(f"  Verdict: {ta.verdict}"
          f"{'':>4}[tier-{ta.tier}]")

    # Tier 2: Cohort comparison
    if ta.tier >= 2 and ta.tail_cohort_size is not None:
        print(f"\n  Tail cohort (>P95): {ta.tail_cohort_size} windows"
              f" vs typical (P25-P75): {ta.typical_cohort_size} windows")
        for name, comp in sorted(ta.covariate_comparisons.items()):
            arrow = ""
            if comp.direction == "higher_in_tail":
                arrow = " ^"
            elif comp.direction == "lower_in_tail":
                arrow = " v"
            sig = _fmt_pvalue(comp.mann_whitney_p)
            print(f"    {name}: tail median={comp.tail_median:.1f},"
                  f" typical median={comp.typical_median:.1f}"
                  f"  ({sig}){arrow}")

        # Frequency stratification
        if ta.stable_freq_p99_us is not None:
            ks_str = _fmt_pvalue(ta.freq_ks_pvalue, prefix="KS p=")
            print(f"\n  Frequency stratification:")
            print(f"    P99 at stable freq:      {ta.stable_freq_p99_us:>8.1f} us")
            print(f"    P99 during transitions:  {ta.unstable_freq_p99_us:>8.1f} us"
                  f"  ({ks_str})")

    # Tier 3: Shapley decomposition
    if ta.tier >= 3 and ta.shapley_pct is not None:
        print(f"\n  Shapley attribution (R²={ta.model_r_squared:.2f}):")
        for name, pct in sorted(ta.shapley_pct.items(), key=lambda x: -x[1]):
            print(f"    {name}: {pct:>5.1f}%")
        print(f"    algorithmic: {ta.algorithmic_residual_pct:>5.1f}%")


def _output_json(results, dev):
    """Print characterization as JSON."""
    output = {
        'device': dev.get('name', 'Unknown'),
        'characterizations': [],
    }
    for r, ta in results:
        entry = {
            'kernel': r.kernel_name,
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
            'tail_attribution': _tail_attribution_to_dict(ta),
        }
        output['characterizations'].append(entry)
    print(json.dumps(output, indent=2))


def _tail_attribution_to_dict(ta):
    """Convert TailAttribution to a JSON-serializable dict."""
    d = {
        'kernel_name': ta.kernel_name,
        'n_windows': ta.n_windows,
        'tier': ta.tier,
        'tail_ratio': round(ta.tail_ratio, 3),
        'noop_tail_ratio': round(ta.noop_tail_ratio, 3) if ta.noop_tail_ratio is not None else None,
        'normalized_ratio': round(ta.normalized_ratio, 3) if ta.normalized_ratio is not None else None,
        'verdict': ta.verdict,
    }
    if ta.tier >= 2:
        d['tail_cohort_size'] = ta.tail_cohort_size
        d['typical_cohort_size'] = ta.typical_cohort_size
        d['covariate_comparisons'] = {
            name: asdict(comp) for name, comp in ta.covariate_comparisons.items()
        }
        if ta.stable_freq_p99_us is not None:
            d['freq_stratification'] = {
                'stable_p99_us': round(ta.stable_freq_p99_us, 2),
                'unstable_p99_us': round(ta.unstable_freq_p99_us, 2),
                'ks_pvalue': ta.freq_ks_pvalue,
            }
    if ta.tier >= 3:
        d['shapley'] = {
            'model_r_squared': round(ta.model_r_squared, 4),
            'attribution_pct': {k: round(v, 1) for k, v in ta.shapley_pct.items()},
            'algorithmic_residual_pct': round(ta.algorithmic_residual_pct, 1),
        }
    d['provenance'] = ta.provenance
    return d


def _generate_markdown(results, dev):
    """Generate markdown characterization report."""
    lines = [
        "# Latency Characterization Report",
        "",
        f"**Device:** {dev.get('name', 'Unknown')}  ",
        "",
    ]

    for r, ta in results:
        prov = r.provenance
        timing_src = prov.get('best_us', 'measured/timing')

        lines.extend([
            f"## {r.kernel_name}",
            "",
            f"| Metric | Value | Provenance |",
            f"|--------|-------|------------|",
            f"| Best (p5) | {r.best_us:.1f} us | {timing_src} |",
            f"| Typical (p50) | {r.typical_us:.1f} us | {timing_src} |",
            f"| Tail (p99) | {r.tail_us:.1f} us | {timing_src} |",
            f"| Best-to-typical gap | {r.best_to_typical_gap_us:.1f} us | {timing_src} |",
            f"| Tail risk | {r.tail_risk_us:.1f} us | {timing_src} |",
            f"| Tail ratio (P99/P50) | {ta.tail_ratio:.1f}x | tier-{ta.tier} |",
        ])
        if ta.normalized_ratio is not None:
            lines.append(f"| Normalized ratio (vs noop) | {ta.normalized_ratio:.1f}x | tier-{ta.tier} |")
        lines.append(f"| Tail verdict | {ta.verdict} | tier-{ta.tier} |")

        if r.ipc is not None:
            lines.append(f"| IPC | {r.ipc:.1f} | {prov.get('ipc', 'measured/PMU')} |")
        if r.effective_freq_ghz is not None:
            lines.append(f"| Effective freq | {r.effective_freq_ghz:.1f} GHz | {prov.get('effective_freq_ghz', 'measured/PMU+timing')} |")
        if r.frequency_tax_pct is not None:
            lines.append(f"| Frequency tax | {r.frequency_tax_pct:.1f}% | {prov.get('frequency_tax_pct', 'measured/PMU+timing')} |")
        if r.backend_stall_pct is not None:
            compute_pct = 100 - r.backend_stall_pct
            lines.append(f"| Compute time | {r.compute_time_us:.1f} us ({compute_pct:.1f}%) | {prov.get('compute_time_us', 'measured/PMU+timing')} |")
            lines.append(f"| Backend stall | {r.memory_stall_time_us:.1f} us ({r.backend_stall_pct:.1f}%) | {prov.get('memory_stall_time_us', 'measured/PMU+timing')} |")
        if r.noop_p50_us is not None:
            lines.append(f"| Noop (p50) | {r.noop_p50_us:.1f} us | {prov.get('noop_p50_us', 'measured/timing/noop')} |")

        lines.extend([
            f"| N windows | {r.n_windows} | |",
            "",
        ])

        # Tier 2/3 details as sub-sections
        if ta.tier >= 2 and ta.covariate_comparisons:
            lines.extend([
                f"### Tail Attribution (Tier {ta.tier})",
                "",
                f"Tail cohort (>P95): {ta.tail_cohort_size} windows,"
                f" typical (P25-P75): {ta.typical_cohort_size} windows",
                "",
                "| Covariate | Tail Median | Typical Median | p-value | Direction |",
                "|-----------|-------------|----------------|---------|-----------|",
            ])
            for name, comp in sorted(ta.covariate_comparisons.items()):
                p_str = _fmt_pvalue(comp.mann_whitney_p, prefix="")
                lines.append(
                    f"| {name} | {comp.tail_median:.1f} | {comp.typical_median:.1f}"
                    f" | {p_str} | {comp.direction} |"
                )
            lines.append("")

        if ta.tier >= 3 and ta.shapley_pct:
            lines.extend([
                f"**Shapley Attribution (R²={ta.model_r_squared:.2f}):**",
                "",
                "| Source | Attribution |",
                "|--------|------------|",
            ])
            for name, pct in sorted(ta.shapley_pct.items(), key=lambda x: -x[1]):
                lines.append(f"| {name} | {pct:.1f}% |")
            lines.append(f"| algorithmic (residual) | {ta.algorithmic_residual_pct:.1f}% |")
            lines.append("")

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
    except (OSError, IOError) as e:
        print(f"\nWarning: Could not write report to {output_dir}: {e}")
