"""Unit tests for TelemetryAnalyzer with dependency injection.

CRIT-004 PR #2: These tests demonstrate minimal DI - we abstract I/O and logging,
but test business logic with real pandas/matplotlib. Fast, isolated, and pragmatic!
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, MagicMock, call, ANY
from pathlib import Path
from typing import List

from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.core.protocols import FileSystemService, Logger


class TestTelemetryAnalyzerInit:
    """Test TelemetryAnalyzer initialization."""

    def test_init_stores_dependencies(self):
        """Test that __init__ properly stores injected dependencies."""
        # Arrange
        fs = Mock(spec=FileSystemService)
        logger = Mock(spec=Logger)

        # Act
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        # Assert
        assert analyzer.fs is fs
        assert analyzer.log is logger


class TestExtractKernelName:
    """Test _extract_kernel_name static method."""

    def test_extract_from_kernel_data_structure_ndjson(self):
        """Test extraction from kernel-data structure with NDJSON."""
        # Arrange
        path = Path("results/run-2025-11-10-001/kernel-data/goertzel/telemetry.ndjson")

        # Act
        result = TelemetryAnalyzer._extract_kernel_name(path)

        # Assert
        assert result == "goertzel"

    def test_extract_from_kernel_data_structure_csv(self):
        """Test extraction from kernel-data structure with CSV."""
        # Arrange
        path = Path("results/batch_123/kernel-data/bandpass_fir/telemetry.csv")

        # Act
        result = TelemetryAnalyzer._extract_kernel_name(path)

        # Assert
        assert result == "bandpass_fir"

    def test_extract_with_underscores(self):
        """Test extraction with kernel names containing underscores."""
        # Arrange
        path = Path("results/test/kernel-data/notch_iir/telemetry.ndjson")

        # Act
        result = TelemetryAnalyzer._extract_kernel_name(path)

        # Assert
        assert result == "notch_iir"

    def test_extract_invalid_structure(self):
        """Test extraction fails gracefully with invalid structure."""
        # Arrange
        path = Path("results/telemetry.ndjson")

        # Act
        result = TelemetryAnalyzer._extract_kernel_name(path)

        # Assert
        assert result is None

    def test_extract_from_wrong_parent(self):
        """Test extraction returns None when parent is not kernel-data."""
        # Arrange
        path = Path("results/run-001/some-other-dir/goertzel/telemetry.ndjson")

        # Act
        result = TelemetryAnalyzer._extract_kernel_name(path)

        # Assert
        assert result is None


class TestLoadTelemetry:
    """Test load_telemetry method."""

    def setup_method(self):
        """Set up test dependencies."""
        self.fs = Mock(spec=FileSystemService)
        self.logger = Mock(spec=Logger)
        self.analyzer = TelemetryAnalyzer(filesystem=self.fs, logger=self.logger)

    def test_load_directory_not_found(self):
        """Test that load fails when directory doesn't exist."""
        # Arrange
        self.fs.exists.return_value = False

        # Act
        result = self.analyzer.load_telemetry("nonexistent_dir")

        # Assert
        assert result is None
        self.logger.error.assert_called_once()
        assert "not found" in self.logger.error.call_args[0][0]

    def test_load_no_telemetry_files(self):
        """Test that load fails when no telemetry files found."""
        # Arrange
        results_path = Path("results/run-001")
        self.fs.exists.side_effect = lambda p: str(p) == str(results_path)
        self.fs.glob.return_value = []  # No files found

        # Act
        result = self.analyzer.load_telemetry(str(results_path))

        # Assert
        assert result is None
        self.logger.error.assert_called()

    def test_load_single_ndjson_file(self, tmp_path):
        """Test loading a single NDJSON file."""
        # Arrange
        results_dir = tmp_path / "results/run-001"
        kernel_dir = results_dir / "kernel-data/goertzel"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        ndjson_file = kernel_dir / "telemetry.ndjson"

        # Create real NDJSON data
        ndjson_data = [
            {"latency_ns": 1000, "warmup": 0},
            {"latency_ns": 2000, "warmup": 0},
            {"latency_ns": 1500, "warmup": 1}
        ]
        with open(ndjson_file, 'w') as f:
            for record in ndjson_data:
                f.write(pd.Series(record).to_json() + '\n')

        # Mock filesystem to return our test file
        self.fs.exists.side_effect = lambda p: Path(p).exists()
        self.fs.glob.return_value = [ndjson_file]

        # Act
        result = self.analyzer.load_telemetry(str(results_dir))

        # Assert
        assert result is not None
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 3
        assert 'latency_us' in result.columns
        assert 'plugin' in result.columns
        assert result['plugin'].iloc[0] == 'goertzel'

    def test_load_multiple_kernels(self, tmp_path):
        """Test loading telemetry from multiple kernels."""
        # Arrange
        results_dir = tmp_path / "results/run-001"

        # Create data for two kernels
        kernel1_dir = results_dir / "kernel-data/goertzel"
        kernel2_dir = results_dir / "kernel-data/bandpass_fir"
        kernel1_dir.mkdir(parents=True, exist_ok=True)
        kernel2_dir.mkdir(parents=True, exist_ok=True)

        ndjson1 = kernel1_dir / "telemetry.ndjson"
        ndjson2 = kernel2_dir / "telemetry.ndjson"

        # Write test data
        with open(ndjson1, 'w') as f:
            f.write('{"latency_ns": 1000, "warmup": 0}\n')
            f.write('{"latency_ns": 1100, "warmup": 0}\n')

        with open(ndjson2, 'w') as f:
            f.write('{"latency_ns": 2000, "warmup": 0}\n')
            f.write('{"latency_ns": 2100, "warmup": 0}\n')

        # Mock filesystem
        self.fs.exists.side_effect = lambda p: Path(p).exists()
        self.fs.glob.return_value = [ndjson1, ndjson2]

        # Act
        result = self.analyzer.load_telemetry(str(results_dir))

        # Assert
        assert result is not None
        assert len(result) == 4
        assert set(result['plugin'].unique()) == {'goertzel', 'bandpass_fir'}

    def test_load_prefer_csv_format(self, tmp_path):
        """Test that CSV is preferred when specified."""
        # Arrange
        results_dir = tmp_path / "results/run-001"
        kernel_dir = results_dir / "kernel-data/goertzel"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        # Create both formats
        csv_file = kernel_dir / "telemetry.csv"
        ndjson_file = kernel_dir / "telemetry.ndjson"

        # Write CSV data
        csv_data = pd.DataFrame({
            'latency_ns': [1000, 2000],
            'warmup': [0, 0]
        })
        csv_data.to_csv(csv_file, index=False)

        # Write NDJSON data (different to verify CSV is used)
        with open(ndjson_file, 'w') as f:
            f.write('{"latency_ns": 9999, "warmup": 0}\n')

        # Mock filesystem - return CSV for csv glob, NDJSON for ndjson glob
        def mock_glob(path, pattern):
            if pattern.endswith('.csv'):
                return [csv_file]
            elif pattern.endswith('.ndjson'):
                return [ndjson_file]
            return []

        self.fs.exists.side_effect = lambda p: Path(p).exists()
        self.fs.glob.side_effect = mock_glob

        # Act
        result = self.analyzer.load_telemetry(str(results_dir), prefer_format='csv')

        # Assert
        assert result is not None
        assert len(result) == 2
        assert result['latency_ns'].iloc[0] == 1000  # From CSV, not NDJSON


class TestCalculateStatistics:
    """Test calculate_statistics method."""

    def setup_method(self):
        """Set up test dependencies."""
        self.fs = Mock(spec=FileSystemService)
        self.logger = Mock(spec=Logger)
        self.analyzer = TelemetryAnalyzer(filesystem=self.fs, logger=self.logger)

    def test_calculate_filters_warmup(self):
        """Test that statistics exclude warmup runs."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel1', 'kernel1'],
            'latency_us': [100, 200, 300, 999],  # Last one is warmup
            'warmup': [0, 0, 0, 1]
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert
        assert 'kernel1' in stats.index
        # Mean should be (100+200+300)/3 = 200, not including 999 warmup
        assert stats.loc['kernel1', 'latency_us_mean'] == 200.0

    def test_calculate_multiple_kernels(self):
        """Test statistics calculation for multiple kernels."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel2', 'kernel2'],
            'latency_us': [100, 200, 300, 400],
            'warmup': [0, 0, 0, 0]
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert
        assert len(stats) == 2
        assert stats.loc['kernel1', 'latency_us_mean'] == 150.0
        assert stats.loc['kernel2', 'latency_us_mean'] == 350.0

    def test_calculate_percentiles(self):
        """Test that percentiles are calculated correctly."""
        # Arrange
        # Create data with known percentiles
        values = list(range(1, 101))  # 1 to 100
        df = pd.DataFrame({
            'plugin': ['kernel1'] * 100,
            'latency_us': values,
            'warmup': [0] * 100
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert
        assert stats.loc['kernel1', 'latency_us_p95'] == 95.05  # 95th percentile
        assert stats.loc['kernel1', 'latency_us_p99'] == 99.01  # 99th percentile

    def test_calculate_min_max(self):
        """Test min and max calculation."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel1'],
            'latency_us': [100, 500, 300],
            'warmup': [0, 0, 0]
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert
        assert stats.loc['kernel1', 'latency_us_min'] == 100
        assert stats.loc['kernel1', 'latency_us_max'] == 500

    def test_calculate_std(self):
        """Test standard deviation calculation."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel1'],
            'latency_us': [10.0, 20.0, 30.0],
            'warmup': [0, 0, 0]
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert
        # Standard deviation of [10, 20, 30] is 10.0
        assert abs(stats.loc['kernel1', 'latency_us_std'] - 10.0) < 0.01

    def test_calculate_with_missing_data(self):
        """Test that calculation handles missing data gracefully."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1'],
            'latency_us': [100],
            'warmup': [1]  # All warmup - no actual data
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert - should handle empty group gracefully
        assert len(stats) == 0 or stats.empty


class TestPlotting:
    """Test plotting methods (minimal testing - verify calls, not visual output)."""

    def setup_method(self):
        """Set up test dependencies."""
        self.fs = Mock(spec=FileSystemService)
        self.logger = Mock(spec=Logger)
        self.analyzer = TelemetryAnalyzer(filesystem=self.fs, logger=self.logger)

    def test_plot_latency_comparison_creates_file(self, tmp_path):
        """Test that latency plot creates output file."""
        # Arrange - Create telemetry data and calculate statistics
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel2', 'kernel2'],
            'latency_us': [100, 200, 300, 400],
            'warmup': [0, 0, 0, 0]
        })
        stats = self.analyzer.calculate_statistics(df)
        output_path = str(tmp_path / "latency.png")

        # Act
        result = self.analyzer.plot_latency_comparison(stats, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()
        assert Path(output_path).stat().st_size > 0

    def test_plot_latency_with_invalid_path(self):
        """Test that plotting fails gracefully with invalid output path."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1'],
            'latency_us': [100],
            'warmup': [0]
        })
        stats = self.analyzer.calculate_statistics(df)
        output_path = "/nonexistent/directory/plot.png"

        # Act
        result = self.analyzer.plot_latency_comparison(stats, output_path)

        # Assert - should handle error gracefully
        assert result is False

    def test_plot_deadline_misses_creates_file(self, tmp_path):
        """Test that deadline miss plot creates output file."""
        # Arrange - Create telemetry data with deadline_missed column
        df = pd.DataFrame({
            'plugin': ['kernel1'] * 10,
            'latency_us': [100] * 5 + [15000] * 5,  # 5 within, 5 over 10ms deadline
            'deadline_missed': [False] * 5 + [True] * 5,
            'warmup': [0] * 10
        })

        # Calculate statistics to get miss_rate column
        stats = self.analyzer.calculate_statistics(df)
        output_path = str(tmp_path / "deadline.png")

        # Act
        result = self.analyzer.plot_deadline_misses(stats, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()

    def test_plot_cdf_creates_file(self, tmp_path):
        """Test that CDF plot creates output file."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1'] * 100,
            'latency_us': np.random.normal(1000, 100, 100),
            'warmup': [0] * 100
        })
        output_path = str(tmp_path / "cdf.png")

        # Act
        result = self.analyzer.plot_cdf_overlay(df, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()

    def test_plot_throughput_creates_file(self, tmp_path):
        """Test that throughput plot creates output file."""
        # Arrange - Create telemetry data and calculate statistics
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel2', 'kernel2'],
            'latency_us': [100, 200, 300, 400],
            'warmup': [0, 0, 0, 0]
        })
        stats = self.analyzer.calculate_statistics(df)
        output_path = str(tmp_path / "throughput.png")

        # Act
        result = self.analyzer.plot_throughput_comparison(stats, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()


class TestGenerateSummaryTable:
    """Test generate_summary_table method."""

    def setup_method(self):
        """Set up test dependencies."""
        # Use real filesystem for summary table tests (they write files)
        from cortex.core import RealFileSystemService
        self.fs = RealFileSystemService()
        self.logger = Mock(spec=Logger)
        self.analyzer = TelemetryAnalyzer(filesystem=self.fs, logger=self.logger)

    def test_generate_creates_markdown_file(self, tmp_path):
        """Test that summary table creates markdown file."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1', 'kernel1', 'kernel2', 'kernel2'],
            'latency_us': [100, 200, 300, 400],
            'warmup': [0, 0, 0, 0]
        })
        output_path = str(tmp_path / "SUMMARY.md")

        # Act
        result = self.analyzer.generate_summary_table(df, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()

        # Verify markdown content
        content = Path(output_path).read_text()
        assert "kernel1" in content
        assert "kernel2" in content
        assert "Mean" in content
        assert "P95" in content

    def test_generate_with_single_kernel(self, tmp_path):
        """Test summary generation with single kernel."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1'] * 10,
            'latency_us': list(range(100, 200, 10)),
            'warmup': [0] * 10
        })
        output_path = str(tmp_path / "SUMMARY.md")

        # Act
        result = self.analyzer.generate_summary_table(df, output_path)

        # Assert
        assert result is True
        content = Path(output_path).read_text()
        assert "kernel1" in content

    def test_generate_handles_write_error(self):
        """Test that generation handles write errors gracefully."""
        # Arrange
        df = pd.DataFrame({
            'plugin': ['kernel1'],
            'latency_us': [100],
            'warmup': [0]
        })
        output_path = "/nonexistent/directory/SUMMARY.md"

        # Act
        result = self.analyzer.generate_summary_table(df, output_path)

        # Assert
        assert result is False


class TestRunFullAnalysis:
    """Test run_full_analysis integration method."""

    def setup_method(self):
        """Set up test dependencies."""
        # Use real filesystem for full analysis tests (they write files)
        from cortex.core import RealFileSystemService
        self.fs = RealFileSystemService()
        self.logger = Mock(spec=Logger)
        self.analyzer = TelemetryAnalyzer(filesystem=self.fs, logger=self.logger)

    def test_full_analysis_pipeline(self, tmp_path):
        """Test complete analysis pipeline end-to-end."""
        # Arrange - Create real test data
        results_dir = tmp_path / "results/run-001"
        kernel_dir = results_dir / "kernel-data/goertzel"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        ndjson_file = kernel_dir / "telemetry.ndjson"
        with open(ndjson_file, 'w') as f:
            for i in range(100):
                f.write(f'{{"latency_ns": {1000 + i*10}, "warmup": {0 if i >= 10 else 1}}}\n')

        output_dir = tmp_path / "analysis"
        output_dir.mkdir(exist_ok=True)

        # Act (using real filesystem)
        result = self.analyzer.run_full_analysis(
            str(results_dir),
            str(output_dir),
            plots=['all'],
            format='png'
        )

        # Assert
        assert result is True
        assert (output_dir / "SUMMARY.md").exists()
        assert (output_dir / "latency_comparison.png").exists()
        assert (output_dir / "cdf_overlay.png").exists()

    def test_full_analysis_with_no_data(self):
        """Test that full analysis handles missing data gracefully."""
        # Act - Try to analyze non-existent directory
        result = self.analyzer.run_full_analysis(
            "/nonexistent/directory/that/does/not/exist",
            "/nonexistent/output"
        )

        # Assert
        assert result is False

    def test_full_analysis_custom_plots(self, tmp_path):
        """Test that only requested plots are generated."""
        # Arrange - Create minimal test data
        results_dir = tmp_path / "results/run-001"
        kernel_dir = results_dir / "kernel-data/goertzel"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        ndjson_file = kernel_dir / "telemetry.ndjson"
        with open(ndjson_file, 'w') as f:
            f.write('{"latency_ns": 1000, "warmup": 0}\n')

        output_dir = tmp_path / "analysis"
        output_dir.mkdir(exist_ok=True)

        # Act - Request only latency plot (using real filesystem)
        result = self.analyzer.run_full_analysis(
            str(results_dir),
            str(output_dir),
            plots=['latency'],
            format='png'
        )

        # Assert
        assert result is True
        assert (output_dir / "latency_comparison.png").exists()
        # CDF should not exist since it wasn't requested
        assert not (output_dir / "cdf_overlay.png").exists()


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
