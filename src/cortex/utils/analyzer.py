"""Data analysis and visualization with dependency injection.

CRIT-004 PR #2: Refactored to use minimal dependency injection.
Abstracts I/O and logging, uses real pandas/matplotlib for deterministic operations.
"""
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path
from typing import List, Optional

from cortex.core.protocols import FileSystemService, Logger

# Sentinel matching CORTEX_STAGE_NOT_CHAINED in telemetry.h
STAGE_INDEX_NOT_CHAINED = 0xFFFFFFFF

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (10, 6)
plt.rcParams['font.size'] = 11

# Pandas version compatibility
# include_groups parameter was added in pandas 2.2.0
PANDAS_VERSION = tuple(map(int, pd.__version__.split('.')[:2]))
SUPPORTS_INCLUDE_GROUPS = PANDAS_VERSION >= (2, 2)


class TelemetryAnalyzer:
    """Analyzes telemetry data with minimal dependency injection.

    Uses minimal DI pattern:
    - Abstracts I/O operations (FileSystemService)
    - Abstracts logging (Logger)
    - Uses real pandas for data transformations (deterministic)
    - Uses real matplotlib for plotting (deterministic)

    This approach balances testability with pragmatism:
    - Easy to test with mocked filesystem and logger
    - Business logic tested with real pandas/matplotlib
    - Industry-standard approach for data science code

    Args:
        filesystem: Filesystem operations abstraction
        logger: Logging abstraction
    """

    def __init__(self, filesystem: FileSystemService, logger: Logger):
        self.fs = filesystem
        self.log = logger
        self.system_info = {}  # Store system/device metadata

    @staticmethod
    def _extract_kernel_name(file_path: Path) -> Optional[str]:
        """Extract kernel name from telemetry file path.

        Static method - no dependencies needed.

        Supports structure: kernel-data/<kernel>/telemetry.{csv,ndjson}

        Args:
            file_path: Path to telemetry file

        Returns:
            Kernel name or None if not found
        """
        # New structure: kernel name is parent directory
        # e.g., results/run-2025-11-10-001/kernel-data/bandpass_fir/telemetry.ndjson
        parent_dir = file_path.parent.name

        # Check if we're in the expected structure
        if file_path.parent.parent.name == "kernel-data":
            return parent_dir if parent_dir else None

        return None

    def load_telemetry(self, results_dir: str, prefer_format: str = 'ndjson') -> Optional[pd.DataFrame]:
        """Load all telemetry files from a results directory.

        Uses FileSystemService for I/O, real pandas for parsing.
        Prefers NDJSON over CSV by default for better structured data handling.

        Args:
            results_dir: Path to batch results directory
            prefer_format: Preferred format ('ndjson' or 'csv')

        Returns:
            DataFrame with all telemetry data, or None if no data found
        """
        results_path = Path(results_dir)

        if not self.fs.exists(results_path):
            self.log.error(f"Results directory not found: {results_dir}")
            return None

        # Find all telemetry files (use FileSystemService for glob)
        ndjson_files = list(self.fs.glob(results_path, "kernel-data/*/telemetry.ndjson"))
        csv_files = list(self.fs.glob(results_path, "kernel-data/*/telemetry.csv"))

        # Determine which files to use based on preference
        if prefer_format == 'ndjson' and ndjson_files:
            files_to_load = ndjson_files
            file_format = 'ndjson'
        elif prefer_format == 'csv' and csv_files:
            files_to_load = csv_files
            file_format = 'csv'
        elif ndjson_files:
            files_to_load = ndjson_files
            file_format = 'ndjson'
        elif csv_files:
            files_to_load = csv_files
            file_format = 'csv'
        else:
            # Check if directory has kernel-data structure
            kernel_data_dir = results_path / "kernel-data"
            if not self.fs.exists(kernel_data_dir):
                self.log.error(f"No kernel-data directory found in {results_dir}")
                self.log.info(f"Expected structure: {results_dir}/kernel-data/<kernel>/telemetry.*")
                self.log.info("Run 'cortex run --all' to generate results first")
            else:
                kernel_dirs = list(self.fs.glob(kernel_data_dir, "*"))
                if not kernel_dirs:
                    self.log.error("kernel-data directory exists but is empty")
                else:
                    self.log.error(f"Found {len(kernel_dirs)} kernel directories but no telemetry files")
                    self.log.info(f"Directories found: {[d.name for d in kernel_dirs]}")
                    self.log.info("This may indicate all kernel runs failed")
            return None

        self.log.info(f"Loading {len(files_to_load)} {file_format.upper()} file(s)...")

        # Load all telemetry files using real pandas
        dataframes = []
        for file_path in files_to_load:
            kernel_name = self._extract_kernel_name(file_path)
            if not kernel_name:
                self.log.warning(f"Could not extract kernel name from {file_path}, skipping")
                continue

            try:
                # Use real pandas for deterministic parsing
                if file_format == 'ndjson':
                    df = pd.read_json(file_path, lines=True)
                else:  # csv
                    df = pd.read_csv(file_path)

                # Extract and remove system_info metadata rows (NDJSON only)
                if '_type' in df.columns:
                    system_info_rows = df[df['_type'] == 'system_info']
                    if not system_info_rows.empty:
                        # Store system info (only keep first occurrence per kernel)
                        if kernel_name not in self.system_info:
                            info = system_info_rows.iloc[0].to_dict()
                            # Extract relevant metadata
                            self.system_info[kernel_name] = {
                                'device_hostname': info.get('device_hostname'),
                                'device_cpu': info.get('device_cpu'),
                                'device_os': info.get('device_os'),
                                'host_os': info.get('os'),
                                'host_cpu': info.get('cpu'),
                            }
                    # Remove system_info rows from telemetry data
                    df = df[df['_type'] != 'system_info'].copy()

                # Add or normalize plugin column
                if 'plugin' not in df.columns:
                    df['plugin'] = kernel_name
                else:
                    # Replace "(unnamed)" placeholder with actual kernel name
                    df.loc[df['plugin'] == '(unnamed)', 'plugin'] = kernel_name

                dataframes.append(df)

            except pd.errors.ParserError as e:
                self.log.error(f"Failed to parse {file_path}: {e}")
                continue
            except Exception as e:
                import traceback
                self.log.error(f"Error loading {file_path}: {e}")
                self.log.debug(traceback.format_exc())  # Use logger instead of print_exc
                continue

        if not dataframes:
            self.log.warning("No telemetry data found in any files")
            self.log.warning(f"Check that kernel runs completed successfully in {results_dir}")
            return None

        # Combine all telemetry (real pandas concat)
        df = pd.concat(dataframes, ignore_index=True)

        # Derive latency from timestamps if not already present
        if 'latency_ns' not in df.columns:
            if 'start_ts_ns' in df.columns and 'end_ts_ns' in df.columns:
                df['latency_ns'] = df['end_ts_ns'] - df['start_ts_ns']
                self.log.info("Derived latency_ns from start_ts_ns/end_ts_ns")
            else:
                self.log.error("Cannot derive latency: missing start_ts_ns/end_ts_ns columns")
                return None

        # Calculate latency in microseconds
        if 'latency_us' not in df.columns and 'latency_ns' in df.columns:
            df['latency_us'] = df['latency_ns'] / 1000.0

        self.log.info(f"Loaded {len(df)} telemetry records from {len(dataframes)} kernel(s)")
        return df

    def calculate_statistics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate latency statistics per kernel.

        Uses real pandas for deterministic aggregations.

        Args:
            df: Telemetry DataFrame with 'plugin', 'latency_us', 'warmup' columns

        Returns:
            DataFrame with statistics per kernel
        """
        # Filter out warmup runs (real pandas filtering)
        df_no_warmup = df[df['warmup'] == 0].copy()

        # Calculate statistics per kernel (real pandas groupby/agg)
        stats = df_no_warmup.groupby('plugin').agg({
            'latency_us': [
                'mean',
                'median',
                ('p95', lambda x: x.quantile(0.95)),
                ('p99', lambda x: x.quantile(0.99)),
                'min',
                'max',
                'std'
            ]
        })

        # Flatten column names
        stats.columns = ['_'.join(col).strip() if col[1] else col[0]
                        for col in stats.columns.values]

        # Calculate deadline miss rate if deadline info available
        if 'deadline_missed' in df_no_warmup.columns:
            # Derive deadline_met from deadline_missed for clarity (no copy needed - already copied on line 196)
            df_no_warmup['deadline_met'] = ~df_no_warmup['deadline_missed'].astype(bool)

            deadline_stats = df_no_warmup.groupby('plugin')['deadline_met'].agg([
                ('total_samples', 'count'),
                ('deadline_misses', lambda x: (x == 0).sum())
            ])
            deadline_stats['miss_rate'] = (
                deadline_stats['deadline_misses'] / deadline_stats['total_samples'] * 100
            )
            stats = stats.join(deadline_stats)

        return stats

    def calculate_chain_statistics(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Calculate per-stage latency statistics for chained pipeline runs.

        Groups telemetry by stage_index (set by dispatch_chain in scheduler.c),
        computes per-stage latency stats, percentage contribution, and
        end-to-end latency per window.

        Args:
            df: Telemetry DataFrame with 'stage_index', 'latency_us', 'warmup' columns

        Returns:
            DataFrame with per-stage statistics, or None if not a chain run
        """
        if 'stage_index' not in df.columns:
            self.log.info("No stage_index column; not a chain run")
            return None

        # Filter warmup and non-chain records
        df_chain = df[(df['warmup'] == 0) & (df['stage_index'] != STAGE_INDEX_NOT_CHAINED)].copy()
        if df_chain.empty:
            self.log.info("No chained telemetry records found")
            return None

        # Per-stage statistics
        stage_stats = df_chain.groupby('stage_index').agg({
            'latency_us': [
                'mean',
                'median',
                ('p95', lambda x: x.quantile(0.95)),
                ('p99', lambda x: x.quantile(0.99)),
            ],
            'plugin': 'first',
        })

        # Flatten multi-level columns and rename 'plugin' -> 'kernel'
        flat_names = []
        for col in stage_stats.columns:
            if col[1] and col[1] != 'first':
                flat_names.append(f'{col[0]}_{col[1]}')
            elif col[0] == 'plugin':
                flat_names.append('kernel')
            else:
                flat_names.append(col[0])
        stage_stats.columns = flat_names

        # Calculate end-to-end latency per window (sum of all stages)
        # Filter to complete windows only (all stages present) to avoid
        # partial windows from failed stages skewing the distribution.
        n_stages = df_chain['stage_index'].nunique()
        stages_per_window = df_chain.groupby('window_index')['stage_index'].nunique()
        complete_windows = stages_per_window[stages_per_window == n_stages].index
        df_complete = df_chain[df_chain['window_index'].isin(complete_windows)]
        e2e = df_complete.groupby('window_index')['latency_us'].sum()
        e2e_stats = {
            'e2e_mean': float(e2e.mean()),
            'e2e_p50': float(e2e.median()),
            'e2e_p95': float(e2e.quantile(0.95)),
            'e2e_p99': float(e2e.quantile(0.99)),
        }

        # Calculate percentage contribution per stage
        total_mean = stage_stats['latency_us_mean'].sum()
        if total_mean > 0:
            stage_stats['pct_contribution'] = (
                stage_stats['latency_us_mean'] / total_mean * 100
            )
        else:
            stage_stats['pct_contribution'] = 0.0

        # Sort by stage index
        stage_stats = stage_stats.sort_index()

        # Log the pipeline summary
        kernels = stage_stats['kernel'].tolist()
        self.log.info(f"Pipeline: {' -> '.join(kernels)}")
        self.log.info(f"End-to-end P50: {e2e_stats['e2e_p50']:.1f} us")
        for _idx, row in stage_stats.iterrows():
            self.log.info(
                f"  {row['kernel']:<20s} {row['latency_us_mean']:>8.1f} us  "
                f"({row['pct_contribution']:>5.1f}%)"
            )

        # Attach e2e stats as metadata
        stage_stats.attrs['e2e'] = e2e_stats

        return stage_stats

    def plot_latency_comparison(self, df: pd.DataFrame, output_path: str,
                                format: str = 'png') -> bool:
        """Generate latency comparison bar chart.

        Uses real matplotlib with 'Agg' backend for deterministic plotting.
        Uses FileSystemService for directory creation.

        Args:
            df: Statistics DataFrame from calculate_statistics()
            output_path: Path to save plot
            format: Image format ('png', 'pdf', 'svg')

        Returns:
            True if plot saved successfully, False otherwise
        """
        # Ensure output directory exists (FileSystemService)
        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        # Real matplotlib plotting
        fig, ax = plt.subplots(figsize=(10, 6))

        kernels = df.index
        latencies = df['latency_us_mean']

        ax.bar(kernels, latencies, color='steelblue', alpha=0.8)
        ax.set_xlabel('Kernel')
        ax.set_ylabel('Mean Latency (μs)')
        ax.set_title('Kernel Latency Comparison')
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            self.log.info(f"Saved latency comparison plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save latency plot: {e}")
            return False
        finally:
            plt.close('all')

    def plot_deadline_misses(self, df: pd.DataFrame, output_path: str,
                            format: str = 'png') -> bool:
        """Generate deadline miss rate bar chart.

        Uses real matplotlib with 'Agg' backend for deterministic plotting.

        Args:
            df: Statistics DataFrame with deadline miss info
            output_path: Path to save plot
            format: Image format

        Returns:
            True if plot saved successfully, False otherwise
        """
        # Ensure output directory exists
        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        # Check if deadline data available
        if 'miss_rate' not in df.columns:
            self.log.warning("No deadline miss data available for plotting")
            return False

        # Real matplotlib plotting
        fig, ax = plt.subplots(figsize=(10, 6))

        kernels = df.index
        miss_rates = df['miss_rate']

        ax.bar(kernels, miss_rates, color='coral', alpha=0.8)
        ax.set_xlabel('Kernel')
        ax.set_ylabel('Deadline Miss Rate (%)')
        ax.set_title('Deadline Miss Rate by Kernel')
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            self.log.info(f"Saved deadline miss plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save deadline miss plot: {e}")
            return False
        finally:
            plt.close('all')

    def plot_cdf_overlay(self, df: pd.DataFrame, output_path: str,
                        format: str = 'png', deadline_us: float = 10000.0) -> bool:
        """Generate CDF overlay plot for latency distributions.

        Args:
            df: Telemetry DataFrame (not statistics)
            output_path: Path to save plot
            format: Image format
            deadline_us: Deadline threshold in microseconds (default: 10000 = 10ms)

        Returns:
            True if plot saved successfully, False otherwise
        """
        # Ensure output directory exists
        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        # Filter out warmup runs
        df_no_warmup = df[df['warmup'] == 0]

        # Real matplotlib plotting
        fig, ax = plt.subplots(figsize=(10, 6))

        # Get unique plugins and colors
        plugins = df_no_warmup['plugin'].unique()
        colors = plt.cm.tab10(range(len(plugins)))

        # Plot CDF for each plugin
        for plugin, color in zip(plugins, colors):
            plugin_data = df_no_warmup[df_no_warmup['plugin'] == plugin]['latency_us']

            # Sort data for CDF
            sorted_data = np.sort(plugin_data)
            cdf = np.arange(1, len(sorted_data) + 1) / len(sorted_data)

            ax.plot(sorted_data, cdf, label=plugin, color=color, linewidth=2)

        # Set logarithmic x-axis scale
        ax.set_xscale('log')
        
        # Set clear tick marks for presentation
        # Find reasonable range based on data
        all_latencies = df_no_warmup['latency_us']
        min_lat = all_latencies.min()
        max_lat = all_latencies.max()
        
        # Generate tick positions: 10, 100, 1k, 10k, 100k, etc.
        tick_positions = []
        tick_labels = []
        start_power = int(np.floor(np.log10(max(1, min_lat))))
        end_power = int(np.ceil(np.log10(max(1, max_lat))))
        
        for power in range(start_power, end_power + 1):
            for multiplier in [1, 2, 5]:
                tick_val = multiplier * (10 ** power)
                if tick_val >= min_lat * 0.5 and tick_val <= max_lat * 2:
                    tick_positions.append(tick_val)
                    if tick_val < 1000:
                        tick_labels.append(f'{int(tick_val)}')
                    elif tick_val < 1000000:
                        tick_labels.append(f'{int(tick_val/1000)}k')
                    else:
                        tick_labels.append(f'{int(tick_val/1000000)}M')
        
        # Use a simpler approach: standard log ticks
        ax.set_xticks([10, 100, 1000, 10000, 100000])
        ax.set_xticklabels(['10', '100', '1k', '10k', '100k'])

        # Add deadline threshold line
        ax.axvline(x=deadline_us, color='red', linestyle='--', linewidth=2, 
                   label=f'Deadline ({deadline_us/1000:.0f}ms)')

        ax.set_xlabel('Latency (μs, log scale)')
        ax.set_ylabel('Cumulative Probability')
        ax.set_title('Kernel Latency Profiles (Log Scale)')
        ax.legend()
        ax.grid(True, alpha=0.3, which='both')

        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            self.log.info(f"Saved CDF plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save CDF plot: {e}")
            return False
        finally:
            plt.close('all')

    def plot_throughput_comparison(self, df: pd.DataFrame, output_path: str,
                                   format: str = 'png') -> bool:
        """Generate throughput comparison bar chart.

        Args:
            df: Statistics DataFrame
            output_path: Path to save plot
            format: Image format

        Returns:
            True if plot saved successfully, False otherwise
        """
        # Ensure output directory exists
        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        # Calculate throughput (ops/sec) from mean latency
        if 'latency_us_mean' not in df.columns:
            self.log.warning("No latency data available for throughput calculation")
            return False

        # Real matplotlib plotting
        fig, ax = plt.subplots(figsize=(10, 6))

        kernels = df.index
        # Throughput = 1 / (latency_us / 1_000_000) = 1_000_000 / latency_us
        # Protect against division by zero
        latency_mean = df['latency_us_mean'].replace(0, np.nan)
        throughput = 1_000_000 / latency_mean

        ax.bar(kernels, throughput, color='seagreen', alpha=0.8)
        ax.set_xlabel('Kernel')
        ax.set_ylabel('Throughput (ops/sec)')
        ax.set_title('Kernel Throughput Comparison')
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            self.log.info(f"Saved throughput plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save throughput plot: {e}")
            return False
        finally:
            plt.close('all')

    def generate_summary_table(self, df: pd.DataFrame, output_path: str,
                               chain_stats: Optional[pd.DataFrame] = None) -> bool:
        """Generate markdown summary table.

        Args:
            df: Telemetry DataFrame (raw data with 'warmup' column)
            output_path: Path to save markdown file
            chain_stats: Per-stage chain statistics from calculate_chain_statistics(), or None

        Returns:
            True if table saved successfully, False otherwise
        """
        try:
            # Ensure output directory exists
            self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

            # Calculate summary stats using real pandas
            stats = self.calculate_statistics(df)

            # Round values for readability
            stats_rounded = stats.round(2)

            # Generate markdown in memory
            timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
            markdown_lines = []

            markdown_lines.append("# Latency Comparison Summary\n\n")
            markdown_lines.append(f"Generated: {timestamp}\n\n")

            # Add device/system information if available
            if self.system_info:
                # Get first kernel's info (assume all same device for a run)
                first_kernel = list(self.system_info.keys())[0]
                info = self.system_info[first_kernel]

                # Determine if remote execution
                # For local execution, device_* fields match host_* fields
                # For remote execution, they differ
                device_host = info.get('device_hostname', '')
                device_cpu = info.get('device_cpu', '')
                device_os = info.get('device_os', '')
                host_cpu = info.get('host_cpu', '')
                host_os = info.get('host_os', '')

                # Remote if device fields differ from host fields
                is_remote = (device_host and host_os and
                           (device_cpu != host_cpu or device_os != host_os))

                markdown_lines.append("## Execution Environment\n\n")
                if is_remote:
                    markdown_lines.append(f"- **Execution Mode**: Remote\n")
                    markdown_lines.append(f"- **Device**: {device_host or 'Unknown'}\n")
                    markdown_lines.append(f"- **Device CPU**: {info.get('device_cpu') or 'Unknown'}\n")
                    markdown_lines.append(f"- **Device OS**: {info.get('device_os') or 'Unknown'}\n")
                else:
                    markdown_lines.append(f"- **Execution Mode**: Local\n")
                    markdown_lines.append(f"- **CPU**: {info.get('host_cpu') or info.get('device_cpu') or 'Unknown'}\n")
                    markdown_lines.append(f"- **OS**: {info.get('host_os') or info.get('device_os') or 'Unknown'}\n")
                markdown_lines.append("\n")

            markdown_lines.append("## Latency Statistics (μs)\n\n")

            # Write table header
            markdown_lines.append("| Kernel | Mean | Median | P95 | P99 | Min | Max | Std Dev |\n")
            markdown_lines.append("|--------|------|--------|-----|-----|-----|-----|----------|\n")

            # Write table rows
            for kernel_name in stats_rounded.index:
                row = stats_rounded.loc[kernel_name]
                markdown_lines.append(
                    f"| {kernel_name} "
                    f"| {row.get('latency_us_mean', 'N/A')} "
                    f"| {row.get('latency_us_median', 'N/A')} "
                    f"| {row.get('latency_us_p95', 'N/A')} "
                    f"| {row.get('latency_us_p99', 'N/A')} "
                    f"| {row.get('latency_us_min', 'N/A')} "
                    f"| {row.get('latency_us_max', 'N/A')} "
                    f"| {row.get('latency_us_std', 'N/A')} |\n"
                )

            # Add deadline miss info if available
            if 'miss_rate' in stats_rounded.columns:
                markdown_lines.append("\n## Deadline Miss Rates\n\n")
                markdown_lines.append("| Kernel | Miss Rate (%) | Total Samples | Misses |\n")
                markdown_lines.append("|--------|---------------|---------------|--------|\n")

                for kernel_name in stats_rounded.index:
                    row = stats_rounded.loc[kernel_name]
                    markdown_lines.append(
                        f"| {kernel_name} "
                        f"| {row.get('miss_rate', 'N/A')} "
                        f"| {row.get('total_samples', 'N/A')} "
                        f"| {row.get('deadline_misses', 'N/A')} |\n"
                    )

            # Add pipeline chain breakdown if available
            if chain_stats is not None:
                markdown_lines.append("\n## Pipeline Chain Breakdown\n\n")
                markdown_lines.append("| Stage | Kernel | Mean | Median | P95 | P99 | Contribution % |\n")
                markdown_lines.append("|-------|--------|------|--------|-----|-----|----------------|\n")

                for stage_idx, row in chain_stats.iterrows():
                    markdown_lines.append(
                        f"| {stage_idx} "
                        f"| {row['kernel']} "
                        f"| {row['latency_us_mean']:.2f} "
                        f"| {row['latency_us_median']:.2f} "
                        f"| {row['latency_us_p95']:.2f} "
                        f"| {row['latency_us_p99']:.2f} "
                        f"| {row['pct_contribution']:.1f} |\n"
                    )

                e2e = chain_stats.attrs.get('e2e', {})
                if e2e:
                    markdown_lines.append(
                        f"\n**End-to-end latency:** "
                        f"Mean {e2e['e2e_mean']:.2f} μs | "
                        f"P50 {e2e['e2e_p50']:.2f} μs | "
                        f"P95 {e2e['e2e_p95']:.2f} μs | "
                        f"P99 {e2e['e2e_p99']:.2f} μs\n"
                    )

            # Write using DI abstraction
            markdown_content = ''.join(markdown_lines)
            self.fs.write_file(output_path, markdown_content)
            self.log.info(f"Saved summary table: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save summary table: {e}")
            return False

    def plot_freq_latency_scatter(self, df: pd.DataFrame, output_path: str,
                                  format: str = 'png') -> bool:
        """Generate scatter plot of CPU frequency vs latency, colored by kernel.

        Requires 'cpu_freq_mhz' column in telemetry (SE-4). Skips if not present
        or all values are 0 (macOS).

        Args:
            df: Telemetry DataFrame (raw data)
            output_path: Path to save plot
            format: Image format

        Returns:
            True if plot saved successfully, False otherwise
        """
        if 'cpu_freq_mhz' not in df.columns:
            self.log.info("No cpu_freq_mhz column; skipping freq-latency scatter")
            return False

        df_plot = df[(df['warmup'] == 0) & (df['cpu_freq_mhz'] > 0)]
        if df_plot.empty:
            self.log.info("No non-zero CPU frequency data; skipping freq-latency scatter")
            return False

        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        fig, ax = plt.subplots(figsize=(10, 6))
        plugins = df_plot['plugin'].unique()
        colors = plt.cm.tab10(range(len(plugins)))

        for plugin, color in zip(plugins, colors):
            subset = df_plot[df_plot['plugin'] == plugin]
            ax.scatter(subset['cpu_freq_mhz'], subset['latency_us'],
                       label=plugin, color=color, alpha=0.4, s=10)

        ax.set_xlabel('CPU Frequency (MHz)')
        ax.set_ylabel('Latency (us)')
        ax.set_title('CPU Frequency vs Latency')
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            self.log.info(f"Saved freq-latency scatter: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save freq-latency scatter: {e}")
            return False
        finally:
            plt.close('all')

    def detect_freq_transitions(self, df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """Detect windows where CPU frequency changed and compute latency delta.

        Args:
            df: Telemetry DataFrame with cpu_freq_mhz column

        Returns:
            DataFrame with transition points and latency deltas, or None
        """
        if 'cpu_freq_mhz' not in df.columns:
            return None

        df_real = df[(df['warmup'] == 0) & (df['cpu_freq_mhz'] > 0)].copy()
        if df_real.empty:
            return None

        rows = []
        for plugin in df_real['plugin'].unique():
            pdata = df_real[df_real['plugin'] == plugin].sort_values('window_index')
            freqs = pdata['cpu_freq_mhz'].values
            latencies = pdata['latency_us'].values
            indices = pdata['window_index'].values

            for i in range(1, len(freqs)):
                if freqs[i] != freqs[i - 1]:
                    rows.append({
                        'plugin': plugin,
                        'window_index': int(indices[i]),
                        'freq_before_mhz': int(freqs[i - 1]),
                        'freq_after_mhz': int(freqs[i]),
                        'latency_before_us': float(latencies[i - 1]),
                        'latency_after_us': float(latencies[i]),
                        'latency_delta_us': float(latencies[i] - latencies[i - 1]),
                    })

        if not rows:
            return None
        return pd.DataFrame(rows)

    def plot_platform_state_timeline(self, df: pd.DataFrame, output_path: str,
                                      format: str = 'png') -> bool:
        """Generate dual-axis timeline: latency + CPU frequency over window index.

        Args:
            df: Telemetry DataFrame (raw data)
            output_path: Path to save plot
            format: Image format

        Returns:
            True if plot saved successfully, False otherwise
        """
        if 'cpu_freq_mhz' not in df.columns:
            self.log.info("No cpu_freq_mhz column; skipping platform state timeline")
            return False

        df_plot = df[(df['warmup'] == 0) & (df['cpu_freq_mhz'] > 0)]
        if df_plot.empty:
            self.log.info("No non-zero CPU frequency data; skipping platform state timeline")
            return False

        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        fig, ax1 = plt.subplots(figsize=(14, 6))
        ax2 = ax1.twinx()

        # Plot latency per kernel on primary axis
        plugins = df_plot['plugin'].unique()
        colors = plt.cm.tab10(range(len(plugins)))

        for plugin, color in zip(plugins, colors):
            subset = df_plot[df_plot['plugin'] == plugin].sort_values('window_index')
            ax1.plot(subset['window_index'], subset['latency_us'],
                     label=f"{plugin} latency", color=color, alpha=0.6, linewidth=0.5)

        # Plot CPU frequency on secondary axis (use first kernel's data)
        first_kernel = df_plot[df_plot['plugin'] == plugins[0]].sort_values('window_index')
        ax2.plot(first_kernel['window_index'], first_kernel['cpu_freq_mhz'],
                 label='CPU Freq', color='red', linewidth=1.5, alpha=0.8)

        ax1.set_xlabel('Window Index')
        ax1.set_ylabel('Latency (us)')
        ax2.set_ylabel('CPU Frequency (MHz)')
        ax1.set_title('Platform State Timeline: Latency & CPU Frequency')

        # Combine legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=8)

        ax1.grid(True, alpha=0.3)
        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            self.log.info(f"Saved platform state timeline: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save platform state timeline: {e}")
            return False
        finally:
            plt.close('all')

    def compare_runs(self, df_baseline: pd.DataFrame, df_candidate: pd.DataFrame,
                     alpha: float = 0.05) -> Optional[pd.DataFrame]:
        """Compare two benchmark runs with statistical tests.

        For each kernel present in both runs, computes Welch's t-test,
        Cohen's d effect size, and relative change in mean latency.

        Args:
            df_baseline: Telemetry DataFrame from baseline run
            df_candidate: Telemetry DataFrame from candidate run
            alpha: Significance level (default 0.05)

        Returns:
            DataFrame with per-kernel comparison, or None if no common kernels
        """
        # Filter warmup
        b = df_baseline[df_baseline['warmup'] == 0]
        c = df_candidate[df_candidate['warmup'] == 0]

        common_kernels = sorted(set(b['plugin'].unique()) & set(c['plugin'].unique()))
        if not common_kernels:
            self.log.warning("No common kernels between baseline and candidate")
            return None

        # Try to import scipy for statistical tests
        try:
            from scipy.stats import ttest_ind
            has_scipy = True
        except ImportError:
            self.log.warning("scipy not installed; statistical tests unavailable (raw means only)")
            has_scipy = False

        rows = []
        for kernel in common_kernels:
            b_lat = b[b['plugin'] == kernel]['latency_us'].values
            c_lat = c[c['plugin'] == kernel]['latency_us'].values

            b_mean = float(np.mean(b_lat))
            c_mean = float(np.mean(c_lat))
            b_std = float(np.std(b_lat, ddof=1)) if len(b_lat) > 1 else 0.0
            c_std = float(np.std(c_lat, ddof=1)) if len(c_lat) > 1 else 0.0

            relative_change = ((c_mean - b_mean) / b_mean * 100) if b_mean > 0 else 0.0

            p_value = None
            cohens_d = None
            significant = False

            if has_scipy and len(b_lat) > 1 and len(c_lat) > 1:
                stat, p_value = ttest_ind(b_lat, c_lat, equal_var=False)
                significant = p_value < alpha

                # Cohen's d (pooled std)
                pooled_std = np.sqrt((b_std**2 + c_std**2) / 2)
                if pooled_std > 0:
                    cohens_d = float((c_mean - b_mean) / pooled_std)

            rows.append({
                'kernel': kernel,
                'baseline_mean': b_mean,
                'baseline_std': b_std,
                'baseline_n': len(b_lat),
                'candidate_mean': c_mean,
                'candidate_std': c_std,
                'candidate_n': len(c_lat),
                'relative_change_pct': relative_change,
                'p_value': p_value,
                'cohens_d': cohens_d,
                'significant': significant,
            })

        return pd.DataFrame(rows)

    def run_full_analysis(self, results_dir: str, output_dir: str,
                         plots: List[str] = None, format: str = 'png',
                         telemetry_format: str = 'ndjson') -> bool:
        """Run complete analysis pipeline.

        Args:
            results_dir: Directory containing benchmark results
            output_dir: Directory to save analysis outputs
            plots: List of plot types to generate ('all', 'latency', 'deadline', 'cdf', 'throughput')
            format: Image format for plots
            telemetry_format: Format preference for telemetry ('ndjson' or 'csv')

        Returns:
            True if analysis completed successfully, False otherwise
        """
        # Default to all plots
        if plots is None or 'all' in plots:
            plots = ['latency', 'deadline', 'cdf', 'throughput']

        self.log.info("Starting full analysis pipeline...")

        # Create output directory
        try:
            self.fs.mkdir(Path(output_dir), parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            self.log.error(f"Cannot create output directory: {e}")
            return False

        # Load telemetry data
        df = self.load_telemetry(results_dir, prefer_format=telemetry_format)
        if df is None or df.empty:
            self.log.error("No telemetry data loaded - aborting analysis")
            return False

        # Calculate statistics
        stats = self.calculate_statistics(df)
        chain_stats = self.calculate_chain_statistics(df)

        # Generate plots
        plot_results = {}

        if 'latency' in plots:
            output_path = f"{output_dir}/latency_comparison.{format}"
            plot_results['latency'] = self.plot_latency_comparison(stats, output_path, format)

        if 'deadline' in plots:
            output_path = f"{output_dir}/deadline_misses.{format}"
            plot_results['deadline'] = self.plot_deadline_misses(stats, output_path, format)

        if 'cdf' in plots:
            output_path = f"{output_dir}/cdf_overlay.{format}"
            plot_results['cdf'] = self.plot_cdf_overlay(df, output_path, format)

        if 'throughput' in plots:
            output_path = f"{output_dir}/throughput_comparison.{format}"
            plot_results['throughput'] = self.plot_throughput_comparison(stats, output_path, format)

        # Platform correlation plots (SE-7): auto-generate when freq data present
        if 'cpu_freq_mhz' in df.columns and (df['cpu_freq_mhz'] > 0).any():
            self.log.info("CPU frequency data detected — generating platform correlation plots")

            freq_scatter_path = f"{output_dir}/freq_latency_scatter.{format}"
            plot_results['freq_scatter'] = self.plot_freq_latency_scatter(df, freq_scatter_path, format)

            timeline_path = f"{output_dir}/platform_state_timeline.{format}"
            plot_results['platform_timeline'] = self.plot_platform_state_timeline(df, timeline_path, format)

            transitions = self.detect_freq_transitions(df)
            if transitions is not None and not transitions.empty:
                trans_path = f"{output_dir}/freq_transitions.csv"
                try:
                    transitions.to_csv(trans_path, index=False)
                    self.log.info(f"Saved {len(transitions)} frequency transitions: {trans_path}")
                except Exception as e:
                    self.log.warning(f"Failed to save transitions CSV: {e}")

        # Generate summary table
        summary_path = f"{output_dir}/SUMMARY.md"
        summary_success = self.generate_summary_table(df, summary_path, chain_stats=chain_stats)

        # Print summary
        successful_plots = sum(1 for v in plot_results.values() if v)
        self.log.info(f"\nAnalysis complete!")
        self.log.info(f"  Generated {successful_plots}/{len(plot_results)} plots")
        self.log.info(f"  Summary table: {'✓' if summary_success else '✗'}")
        self.log.info(f"  Output directory: {output_dir}")

        return successful_plots > 0 or summary_success
