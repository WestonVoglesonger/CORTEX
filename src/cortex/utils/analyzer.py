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

                # Add plugin column if not present
                if 'plugin' not in df.columns:
                    df['plugin'] = kernel_name

                dataframes.append(df)

            except pd.errors.ParserError as e:
                self.log.error(f"Failed to parse {file_path}: {e}")
                continue
            except Exception as e:
                import traceback
                self.log.error(f"Error loading {file_path}: {e}")
                traceback.print_exc()
                continue

        if not dataframes:
            self.log.warning("No telemetry data found in any files")
            self.log.warning(f"Check that kernel runs completed successfully in {results_dir}")
            return None

        # Combine all telemetry (real pandas concat)
        df = pd.concat(dataframes, ignore_index=True)

        # Calculate latency in microseconds if needed
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
        if 'deadline_met' in df_no_warmup.columns:
            deadline_stats = df_no_warmup.groupby('plugin')['deadline_met'].agg([
                ('total_samples', 'count'),
                ('deadline_misses', lambda x: (x == 0).sum())
            ])
            deadline_stats['miss_rate'] = (
                deadline_stats['deadline_misses'] / deadline_stats['total_samples'] * 100
            )
            stats = stats.join(deadline_stats)

        return stats

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
            plt.close()
            self.log.info(f"Saved latency comparison plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save latency plot: {e}")
            plt.close()
            return False

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
            plt.close()
            self.log.info(f"Saved deadline miss plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save deadline miss plot: {e}")
            plt.close()
            return False

    def plot_cdf_overlay(self, df: pd.DataFrame, output_path: str,
                        format: str = 'png') -> bool:
        """Generate CDF overlay plot for latency distributions.

        Args:
            df: Telemetry DataFrame (not statistics)
            output_path: Path to save plot
            format: Image format

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

        ax.set_xlabel('Latency (μs)')
        ax.set_ylabel('Cumulative Probability')
        ax.set_title('Latency CDF Comparison')
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            plt.close()
            self.log.info(f"Saved CDF plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save CDF plot: {e}")
            plt.close()
            return False

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
        throughput = 1_000_000 / df['latency_us_mean']

        ax.bar(kernels, throughput, color='seagreen', alpha=0.8)
        ax.set_xlabel('Kernel')
        ax.set_ylabel('Throughput (ops/sec)')
        ax.set_title('Kernel Throughput Comparison')
        ax.tick_params(axis='x', rotation=45)

        plt.tight_layout()

        try:
            plt.savefig(output_path, dpi=300, bbox_inches='tight', format=format)
            plt.close()
            self.log.info(f"Saved throughput plot: {output_path}")
            return True
        except Exception as e:
            self.log.error(f"Failed to save throughput plot: {e}")
            plt.close()
            return False

    @staticmethod
    def _calculate_deadline_from_config(config_path: str = "primitives/configs/cortex.yaml") -> float:
        """Calculate deadline from config file.

        Static method - uses real yaml parsing.

        Args:
            config_path: Path to config file

        Returns:
            Deadline in microseconds
        """
        import yaml

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            # Extract deadline from config
            deadline_ms = config.get('benchmark', {}).get('parameters', {}).get('deadline_ms', 1000)
            return deadline_ms * 1000  # Convert to microseconds
        except Exception:
            return 1000_000  # Default 1000ms = 1,000,000μs

    def generate_summary_table(self, df: pd.DataFrame, output_path: str) -> bool:
        """Generate markdown summary table.

        Args:
            df: Statistics DataFrame
            output_path: Path to save markdown file

        Returns:
            True if table saved successfully, False otherwise
        """
        # Ensure output directory exists
        self.fs.mkdir(Path(output_path).parent, parents=True, exist_ok=True)

        # Calculate summary stats using real pandas
        stats = self.calculate_statistics(df)

        # Round values for readability
        stats_rounded = stats.round(2)

        # Generate markdown
        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(output_path, 'w') as f:
            f.write(f"# Benchmark Summary\n\n")
            f.write(f"Generated: {timestamp}\n\n")
            f.write("## Latency Statistics (μs)\n\n")

            # Write table header
            f.write("| Kernel | Mean | Median | P95 | P99 | Min | Max | Std Dev |\n")
            f.write("|--------|------|--------|-----|-----|-----|-----|----------|\n")

            # Write table rows
            for kernel_name in stats_rounded.index:
                row = stats_rounded.loc[kernel_name]
                f.write(f"| {kernel_name} "
                       f"| {row.get('latency_us_mean', 'N/A')} "
                       f"| {row.get('latency_us_median', 'N/A')} "
                       f"| {row.get('latency_us_p95', 'N/A')} "
                       f"| {row.get('latency_us_p99', 'N/A')} "
                       f"| {row.get('latency_us_min', 'N/A')} "
                       f"| {row.get('latency_us_max', 'N/A')} "
                       f"| {row.get('latency_us_std', 'N/A')} |\n")

            # Add deadline miss info if available
            if 'miss_rate' in stats_rounded.columns:
                f.write("\n## Deadline Miss Rates\n\n")
                f.write("| Kernel | Miss Rate (%) | Total Samples | Misses |\n")
                f.write("|--------|---------------|---------------|--------|\n")

                for kernel_name in stats_rounded.index:
                    row = stats_rounded.loc[kernel_name]
                    f.write(f"| {kernel_name} "
                           f"| {row.get('miss_rate', 'N/A')} "
                           f"| {row.get('total_samples', 'N/A')} "
                           f"| {row.get('deadline_misses', 'N/A')} |\n")

        self.log.info(f"Saved summary table: {output_path}")
        return True

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
        self.fs.mkdir(Path(output_dir), parents=True, exist_ok=True)

        # Load telemetry data
        df = self.load_telemetry(results_dir, prefer_format=telemetry_format)
        if df is None or df.empty:
            self.log.error("No telemetry data loaded - aborting analysis")
            return False

        # Calculate statistics
        stats = self.calculate_statistics(df)

        # Generate plots
        plot_results = {}

        if 'latency' in plots:
            output_path = f"{output_dir}/latency_comparison.{format}"
            plot_results['latency'] = self.plot_latency_comparison(stats, output_path, format)

        if 'deadline' in plots:
            output_path = f"{output_dir}/deadline_misses.{format}"
            plot_results['deadline'] = self.plot_deadline_misses(stats, output_path, format)

        if 'cdf' in plots:
            output_path = f"{output_dir}/latency_cdf.{format}"
            plot_results['cdf'] = self.plot_cdf_overlay(df, output_path, format)

        if 'throughput' in plots:
            output_path = f"{output_dir}/throughput_comparison.{format}"
            plot_results['throughput'] = self.plot_throughput_comparison(stats, output_path, format)

        # Generate summary table
        summary_path = f"{output_dir}/SUMMARY.md"
        summary_success = self.generate_summary_table(df, summary_path)

        # Print summary
        successful_plots = sum(1 for v in plot_results.values() if v)
        self.log.info(f"\nAnalysis complete!")
        self.log.info(f"  Generated {successful_plots}/{len(plot_results)} plots")
        self.log.info(f"  Summary table: {'✓' if summary_success else '✗'}")
        self.log.info(f"  Output directory: {output_dir}")

        return successful_plots > 0 or summary_success
