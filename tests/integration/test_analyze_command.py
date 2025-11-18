"""Integration tests for analyze command with real dependencies.

CRIT-004 PR #2: These tests use real implementations to verify TelemetryAnalyzer
end-to-end functionality. Uses real pandas/matplotlib, real filesystem.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
import pandas as pd

from cortex.utils.analyzer import TelemetryAnalyzer
from cortex.core import ConsoleLogger, RealFileSystemService


class TestTelemetryAnalyzerIntegration:
    """Integration tests with real filesystem and pandas/matplotlib."""

    def setup_method(self):
        """Set up integration test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.filesystem = RealFileSystemService()
        self.logger = ConsoleLogger()

        self.analyzer = TelemetryAnalyzer(
            filesystem=self.filesystem,
            logger=self.logger
        )

    def teardown_method(self):
        """Clean up temp directory after test."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_load_telemetry_real_ndjson_files(self):
        """Test loading real NDJSON telemetry files from filesystem."""
        # Create realistic directory structure
        results_dir = self.temp_dir / "results/run-2025-11-17-001"
        kernel1_dir = results_dir / "kernel-data/goertzel"
        kernel2_dir = results_dir / "kernel-data/bandpass_fir"

        kernel1_dir.mkdir(parents=True, exist_ok=True)
        kernel2_dir.mkdir(parents=True, exist_ok=True)

        # Write realistic telemetry data
        ndjson1 = kernel1_dir / "telemetry.ndjson"
        ndjson2 = kernel2_dir / "telemetry.ndjson"

        # Goertzel kernel data (faster)
        with open(ndjson1, 'w') as f:
            for i in range(100):
                warmup = 1 if i < 10 else 0
                latency_ns = 1000 + (i * 5)  # Incrementing latencies
                f.write(f'{{"latency_ns": {latency_ns}, "warmup": {warmup}}}\n')

        # Bandpass FIR kernel data (slower)
        with open(ndjson2, 'w') as f:
            for i in range(100):
                warmup = 1 if i < 10 else 0
                latency_ns = 2000 + (i * 10)  # Higher latencies
                f.write(f'{{"latency_ns": {latency_ns}, "warmup": {warmup}}}\n')

        # Act - Load telemetry
        df = self.analyzer.load_telemetry(str(results_dir))

        # Assert
        assert df is not None
        assert len(df) == 200  # 100 from each kernel
        assert set(df['plugin'].unique()) == {'goertzel', 'bandpass_fir'}
        assert 'latency_us' in df.columns
        assert 'warmup' in df.columns

        # Verify latency conversion (ns -> us)
        assert df['latency_us'].min() > 0
        assert df['latency_us'].max() < df['latency_ns'].max()

    def test_load_telemetry_real_csv_files(self):
        """Test loading real CSV telemetry files from filesystem."""
        # Create directory structure
        results_dir = self.temp_dir / "results/csv-test"
        kernel_dir = results_dir / "kernel-data/notch_iir"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        # Write CSV data
        csv_file = kernel_dir / "telemetry.csv"
        csv_data = pd.DataFrame({
            'latency_ns': [1000, 1100, 1200, 1300],
            'warmup': [1, 0, 0, 0]
        })
        csv_data.to_csv(csv_file, index=False)

        # Act
        df = self.analyzer.load_telemetry(str(results_dir), prefer_format='csv')

        # Assert
        assert df is not None
        assert len(df) == 4
        assert df['plugin'].iloc[0] == 'notch_iir'

    def test_calculate_statistics_real_pandas(self):
        """Test statistics calculation with real pandas operations."""
        # Create test data
        df = pd.DataFrame({
            'plugin': ['kernel1'] * 100 + ['kernel2'] * 100,
            'latency_us': list(range(100, 200)) + list(range(200, 300)),
            'warmup': [1] * 10 + [0] * 90 + [1] * 10 + [0] * 90
        })

        # Act
        stats = self.analyzer.calculate_statistics(df)

        # Assert
        assert len(stats) == 2
        assert 'kernel1' in stats.index
        assert 'kernel2' in stats.index

        # Verify statistics structure
        assert ('latency_us', 'mean') in stats.columns
        assert ('latency_us', 'median') in stats.columns
        assert ('latency_us', 'p95') in stats.columns
        assert ('latency_us', 'p99') in stats.columns

        # Verify warmup filtering worked (should exclude first 10 of each)
        # kernel1: mean of 110..199 = 154.5
        # kernel2: mean of 210..299 = 254.5
        assert abs(stats.loc['kernel1', ('latency_us', 'mean')] - 154.5) < 0.1
        assert abs(stats.loc['kernel2', ('latency_us', 'mean')] - 254.5) < 0.1

    def test_plot_latency_comparison_real_matplotlib(self):
        """Test latency comparison plotting with real matplotlib."""
        # Create test data
        df = pd.DataFrame({
            'plugin': ['kernel1'] * 50 + ['kernel2'] * 50,
            'latency_us': [100 + i for i in range(50)] + [200 + i for i in range(50)],
            'warmup': [0] * 100
        })

        output_path = str(self.temp_dir / "latency_comparison.png")

        # Act
        result = self.analyzer.plot_latency_comparison(df, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()
        assert Path(output_path).stat().st_size > 1000  # Real PNG should be >1KB

    def test_plot_cdf_overlay_real_matplotlib(self):
        """Test CDF overlay plotting with real matplotlib."""
        # Create test data with realistic distribution
        import numpy as np
        np.random.seed(42)  # Reproducible

        df = pd.DataFrame({
            'plugin': ['kernel1'] * 1000 + ['kernel2'] * 1000,
            'latency_us': list(np.random.normal(1000, 100, 1000)) + \
                         list(np.random.normal(1500, 150, 1000)),
            'warmup': [0] * 2000
        })

        output_path = str(self.temp_dir / "cdf_overlay.png")

        # Act
        result = self.analyzer.plot_cdf_overlay(df, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()
        assert Path(output_path).stat().st_size > 1000

    def test_generate_summary_table_real_filesystem(self):
        """Test summary table generation with real filesystem I/O."""
        # Create test data
        df = pd.DataFrame({
            'plugin': ['goertzel'] * 100 + ['bandpass_fir'] * 100 + ['notch_iir'] * 100,
            'latency_us': list(range(100, 200)) + list(range(150, 250)) + list(range(200, 300)),
            'warmup': [0] * 300
        })

        output_path = str(self.temp_dir / "SUMMARY.md")

        # Act
        result = self.analyzer.generate_summary_table(df, output_path)

        # Assert
        assert result is True
        assert Path(output_path).exists()

        # Verify markdown content
        content = Path(output_path).read_text()
        assert "Latency Comparison Summary" in content
        assert "goertzel" in content
        assert "bandpass_fir" in content
        assert "notch_iir" in content
        assert "Mean" in content
        assert "Median" in content
        assert "P95" in content
        assert "P99" in content
        assert "μs" in content  # Microsecond unit

    def test_full_analysis_pipeline_end_to_end(self):
        """Test complete analysis pipeline with real filesystem and libraries."""
        # Create realistic benchmark results structure
        results_dir = self.temp_dir / "results/integration-test-001"
        output_dir = self.temp_dir / "analysis"

        # Create two kernel results
        for kernel_name, base_latency in [('goertzel', 1000), ('bandpass_fir', 1500)]:
            kernel_dir = results_dir / f"kernel-data/{kernel_name}"
            kernel_dir.mkdir(parents=True, exist_ok=True)

            ndjson_file = kernel_dir / "telemetry.ndjson"
            with open(ndjson_file, 'w') as f:
                for i in range(100):
                    warmup = 1 if i < 10 else 0
                    latency_ns = base_latency + (i * 10)
                    f.write(f'{{"latency_ns": {latency_ns}, "warmup": {warmup}}}\n')

        output_dir.mkdir(parents=True, exist_ok=True)

        # Act - Run full analysis pipeline
        result = self.analyzer.run_full_analysis(
            str(results_dir),
            str(output_dir),
            plots=['all'],
            format='png'
        )

        # Assert - Verify all outputs created
        assert result is True

        # Check summary table
        summary_file = output_dir / "SUMMARY.md"
        assert summary_file.exists()
        content = summary_file.read_text()
        assert 'goertzel' in content
        assert 'bandpass_fir' in content

        # Check plots
        assert (output_dir / "latency_comparison.png").exists()
        assert (output_dir / "deadline_misses.png").exists()
        assert (output_dir / "cdf_overlay.png").exists()
        assert (output_dir / "throughput_comparison.png").exists()

        # Verify plots are valid (non-empty)
        for plot_name in ["latency_comparison.png", "cdf_overlay.png",
                          "throughput_comparison.png", "deadline_misses.png"]:
            plot_path = output_dir / plot_name
            assert plot_path.stat().st_size > 1000  # Real plots should be >1KB

    def test_full_analysis_with_custom_plots(self):
        """Test analysis with custom plot selection."""
        # Create minimal test data
        results_dir = self.temp_dir / "results/custom-plots"
        kernel_dir = results_dir / "kernel-data/test_kernel"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        ndjson_file = kernel_dir / "telemetry.ndjson"
        with open(ndjson_file, 'w') as f:
            for i in range(50):
                f.write(f'{{"latency_ns": {1000 + i*10}, "warmup": 0}}\n')

        output_dir = self.temp_dir / "analysis-custom"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Act - Request only latency and CDF plots
        result = self.analyzer.run_full_analysis(
            str(results_dir),
            str(output_dir),
            plots=['latency', 'cdf'],
            format='png'
        )

        # Assert
        assert result is True
        assert (output_dir / "latency_comparison.png").exists()
        assert (output_dir / "cdf_overlay.png").exists()
        # These should not exist
        assert not (output_dir / "throughput_comparison.png").exists()
        assert not (output_dir / "deadline_misses.png").exists()

    def test_error_handling_missing_directory(self):
        """Test that analyzer handles missing directories gracefully."""
        # Act - Try to load from nonexistent directory
        result = self.analyzer.load_telemetry("/nonexistent/path/to/results")

        # Assert - Should return None, not crash
        assert result is None

    def test_error_handling_empty_directory(self):
        """Test that analyzer handles empty directories gracefully."""
        # Create empty results directory
        results_dir = self.temp_dir / "results/empty"
        results_dir.mkdir(parents=True, exist_ok=True)

        # Act
        result = self.analyzer.load_telemetry(str(results_dir))

        # Assert
        assert result is None


# Test discovery for pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
