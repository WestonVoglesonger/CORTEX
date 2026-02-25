"""Unit tests for compare command."""
import pytest
import argparse
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

from cortex.commands.compare import setup_parser, execute, _resolve_run_dir


class TestSetupParser:
    def test_registers_expected_arguments(self):
        parser = argparse.ArgumentParser()
        setup_parser(parser)
        args = parser.parse_args(['--baseline', 'run_a', '--candidate', 'run_b'])
        assert args.baseline == 'run_a'
        assert args.candidate == 'run_b'
        assert args.alpha == 0.05
        assert args.format == 'png'

    def test_custom_alpha(self):
        parser = argparse.ArgumentParser()
        setup_parser(parser)
        args = parser.parse_args(['--baseline', 'a', '--candidate', 'b', '--alpha', '0.01'])
        assert args.alpha == 0.01


class TestCompareRuns:
    """Test the compare_runs method on TelemetryAnalyzer directly."""

    def test_compare_runs_basic(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        df_a = pd.DataFrame({
            'plugin': ['goertzel'] * 50 + ['car'] * 50,
            'latency_us': list(np.random.normal(100, 10, 50)) + list(np.random.normal(200, 20, 50)),
            'warmup': [0] * 100,
        })
        df_b = pd.DataFrame({
            'plugin': ['goertzel'] * 50 + ['car'] * 50,
            'latency_us': list(np.random.normal(110, 10, 50)) + list(np.random.normal(190, 20, 50)),
            'warmup': [0] * 100,
        })

        result = analyzer.compare_runs(df_a, df_b, alpha=0.05)
        assert result is not None
        assert len(result) == 2
        assert 'kernel' in result.columns
        assert 'p_value' in result.columns
        assert 'cohens_d' in result.columns
        assert 'relative_change_pct' in result.columns
        assert set(result['kernel']) == {'car', 'goertzel'}

    def test_compare_runs_no_common_kernels(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        df_a = pd.DataFrame({
            'plugin': ['goertzel'] * 10,
            'latency_us': [100.0] * 10,
            'warmup': [0] * 10,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * 10,
            'latency_us': [200.0] * 10,
            'warmup': [0] * 10,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result is None

    def test_compare_runs_filters_warmup(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        # Warmup rows should be excluded
        df_a = pd.DataFrame({
            'plugin': ['goertzel'] * 20,
            'latency_us': [999.0] * 10 + [100.0] * 10,
            'warmup': [1] * 10 + [0] * 10,
        })
        df_b = pd.DataFrame({
            'plugin': ['goertzel'] * 20,
            'latency_us': [999.0] * 10 + [100.0] * 10,
            'warmup': [1] * 10 + [0] * 10,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result is not None
        assert len(result) == 1
        # Means should be ~100, not contaminated by warmup 999
        assert result.iloc[0]['baseline_mean'] == pytest.approx(100.0, abs=1)
        assert result.iloc[0]['baseline_n'] == 10

    def test_compare_runs_includes_percentiles(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 100
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(110, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        row = result.iloc[0]
        for col in ('baseline_p50', 'baseline_p95', 'baseline_p99',
                     'candidate_p50', 'candidate_p95', 'candidate_p99'):
            assert col in result.columns
            assert isinstance(row[col], float)
        # P50 should be near the mean
        assert row['baseline_p50'] == pytest.approx(100, abs=5)
        # P99 should be higher than P50
        assert row['baseline_p99'] > row['baseline_p50']

    def test_compare_runs_effect_size_large(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 100
        # Means 10 std apart → |d| >> 0.8
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(200, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result.iloc[0]['effect_size_label'] == 'large'

    def test_compare_runs_verdict_improved(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 100
        # Candidate is faster (lower latency) with large effect
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(200, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result.iloc[0]['verdict'] == 'IMPROVED'

    def test_compare_runs_verdict_regressed(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 100
        # Candidate is slower with large effect
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(200, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result.iloc[0]['verdict'] == 'REGRESSED'

    def test_compare_runs_verdict_negligible(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 5000
        # 1µs shift with std=10, n=5000 → d≈0.1 (significant but negligible)
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(101, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        row = result.iloc[0]
        assert row['significant'] is np.True_ or row['significant'] is True
        assert abs(row['cohens_d']) < 0.2
        assert row['verdict'] == 'NEGLIGIBLE'

    def test_compare_runs_verdict_noise(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 50
        # Same distribution → not significant
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result.iloc[0]['verdict'] == 'NOISE'

    def test_compare_runs_verdict_low_n(self):
        from cortex.utils.analyzer import TelemetryAnalyzer

        fs = Mock()
        logger = Mock()
        analyzer = TelemetryAnalyzer(filesystem=fs, logger=logger)

        np.random.seed(42)
        n = 10
        # Even with huge difference, n < 30 → LOW_N
        df_a = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(100, 10, n),
            'warmup': [0] * n,
        })
        df_b = pd.DataFrame({
            'plugin': ['car'] * n,
            'latency_us': np.random.normal(500, 10, n),
            'warmup': [0] * n,
        })

        result = analyzer.compare_runs(df_a, df_b)
        assert result.iloc[0]['verdict'] == 'LOW_N'


class TestExecute:
    def _make_args(self, **kwargs):
        defaults = {
            'baseline': 'run_a',
            'candidate': 'run_b',
            'output': '/tmp/test_compare_out',
            'alpha': 0.05,
            'format': 'png',
            'telemetry_format': 'ndjson',
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch('cortex.commands.compare._generate_markdown_report')
    @patch('cortex.commands.compare._generate_comparison_chart')
    @patch('cortex.commands.compare._generate_cdf_overlay')
    @patch('cortex.commands.compare.TelemetryAnalyzer')
    @patch('cortex.commands.compare.RealFileSystemService')
    @patch('cortex.commands.compare.ConsoleLogger')
    @patch('cortex.commands.compare._resolve_run_dir')
    def test_execute_success(self, mock_resolve, mock_logger, mock_fs,
                              mock_analyzer_cls, mock_cdf, mock_chart, mock_report):
        mock_resolve.side_effect = [MagicMock(), MagicMock()]

        analyzer = mock_analyzer_cls.return_value
        analyzer.system_info = {}

        np.random.seed(42)
        df = pd.DataFrame({
            'plugin': ['goertzel'] * 50,
            'latency_us': np.random.normal(100, 10, 50),
            'warmup': [0] * 50,
        })
        analyzer.load_telemetry.return_value = df

        comparison = pd.DataFrame([{
            'kernel': 'goertzel',
            'baseline_mean': 100.0,
            'baseline_std': 10.0,
            'baseline_n': 50,
            'candidate_mean': 105.0,
            'candidate_std': 10.0,
            'candidate_n': 50,
            'relative_change_pct': 5.0,
            'p_value': 0.02,
            'cohens_d': 0.5,
            'significant': True,
            'baseline_p50': 99.5,
            'baseline_p95': 116.0,
            'baseline_p99': 123.0,
            'candidate_p50': 104.5,
            'candidate_p95': 121.0,
            'candidate_p99': 128.0,
            'effect_size_label': 'medium',
            'verdict': 'REGRESSED',
        }])
        analyzer.compare_runs.return_value = comparison

        args = self._make_args()
        result = execute(args)
        assert result == 0

    @patch('cortex.commands.compare._resolve_run_dir')
    def test_execute_baseline_not_found(self, mock_resolve):
        mock_resolve.return_value = None

        args = self._make_args()
        result = execute(args)
        assert result == 1
