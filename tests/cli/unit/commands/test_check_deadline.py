"""Unit tests for check-deadline command."""
import pytest
import json
import argparse
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

from cortex.commands.check_deadline import setup_parser, execute


class TestSetupParser:
    def test_registers_expected_arguments(self):
        parser = argparse.ArgumentParser()
        setup_parser(parser)
        # Should parse without error with defaults
        args = parser.parse_args([])
        assert args.threshold == 1.0
        assert args.format == 'table'
        assert args.telemetry_format == 'ndjson'
        assert args.run_name is None

    def test_custom_args(self):
        parser = argparse.ArgumentParser()
        setup_parser(parser)
        args = parser.parse_args(['--run-name', 'test-run', '--threshold', '5.0',
                                  '--format', 'json'])
        assert args.run_name == 'test-run'
        assert args.threshold == 5.0
        assert args.format == 'json'


class TestExecute:
    def _make_args(self, **kwargs):
        defaults = {
            'run_name': 'test-run',
            'threshold': 1.0,
            'format': 'table',
            'telemetry_format': 'ndjson',
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch('cortex.commands.check_deadline.TelemetryAnalyzer')
    @patch('cortex.commands.check_deadline.RealFileSystemService')
    @patch('cortex.commands.check_deadline.ConsoleLogger')
    @patch('cortex.commands.check_deadline.get_run_directory')
    def test_pass_when_below_threshold(self, mock_get_run, mock_logger, mock_fs, mock_analyzer_cls):
        mock_get_run.return_value = MagicMock(exists=lambda: True)

        analyzer = mock_analyzer_cls.return_value
        # Telemetry DataFrame
        df = pd.DataFrame({
            'plugin': ['goertzel'] * 100,
            'latency_us': np.random.uniform(50, 200, 100),
            'warmup': [0] * 100,
            'deadline_missed': [0] * 100,
        })
        analyzer.load_telemetry.return_value = df

        # Stats with miss_rate = 0
        stats = pd.DataFrame({
            'latency_us_mean': [100.0],
            'miss_rate': [0.0],
            'total_samples': [100],
            'deadline_misses': [0],
        }, index=['goertzel'])
        analyzer.calculate_statistics.return_value = stats

        args = self._make_args()
        result = execute(args)
        assert result == 0

    @patch('cortex.commands.check_deadline.TelemetryAnalyzer')
    @patch('cortex.commands.check_deadline.RealFileSystemService')
    @patch('cortex.commands.check_deadline.ConsoleLogger')
    @patch('cortex.commands.check_deadline.get_run_directory')
    def test_fail_when_above_threshold(self, mock_get_run, mock_logger, mock_fs, mock_analyzer_cls):
        mock_get_run.return_value = MagicMock(exists=lambda: True)

        analyzer = mock_analyzer_cls.return_value
        df = pd.DataFrame({
            'plugin': ['goertzel'] * 100,
            'latency_us': [100.0] * 100,
            'warmup': [0] * 100,
            'deadline_missed': [1] * 5 + [0] * 95,
        })
        analyzer.load_telemetry.return_value = df

        stats = pd.DataFrame({
            'latency_us_mean': [100.0],
            'miss_rate': [5.0],
            'total_samples': [100],
            'deadline_misses': [5],
        }, index=['goertzel'])
        analyzer.calculate_statistics.return_value = stats

        args = self._make_args(threshold=1.0)
        result = execute(args)
        assert result == 1

    @patch('cortex.commands.check_deadline.TelemetryAnalyzer')
    @patch('cortex.commands.check_deadline.RealFileSystemService')
    @patch('cortex.commands.check_deadline.ConsoleLogger')
    @patch('cortex.commands.check_deadline.get_run_directory')
    def test_json_output(self, mock_get_run, mock_logger, mock_fs, mock_analyzer_cls, capsys):
        mock_get_run.return_value = MagicMock(exists=lambda: True)

        analyzer = mock_analyzer_cls.return_value
        df = pd.DataFrame({
            'plugin': ['goertzel'] * 10,
            'latency_us': [100.0] * 10,
            'warmup': [0] * 10,
            'deadline_missed': [0] * 10,
        })
        analyzer.load_telemetry.return_value = df

        stats = pd.DataFrame({
            'latency_us_mean': [100.0],
            'miss_rate': [0.0],
            'total_samples': [10],
            'deadline_misses': [0],
        }, index=['goertzel'])
        analyzer.calculate_statistics.return_value = stats

        args = self._make_args(format='json')
        result = execute(args)
        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output['overall'] == 'PASS'
        assert len(output['kernels']) == 1
        assert output['kernels'][0]['kernel'] == 'goertzel'

    @patch('cortex.commands.check_deadline.TelemetryAnalyzer')
    @patch('cortex.commands.check_deadline.RealFileSystemService')
    @patch('cortex.commands.check_deadline.ConsoleLogger')
    @patch('cortex.commands.check_deadline.get_run_directory')
    def test_no_deadline_data(self, mock_get_run, mock_logger, mock_fs, mock_analyzer_cls):
        mock_get_run.return_value = MagicMock(exists=lambda: True)

        analyzer = mock_analyzer_cls.return_value
        df = pd.DataFrame({
            'plugin': ['goertzel'] * 10,
            'latency_us': [100.0] * 10,
            'warmup': [0] * 10,
        })
        analyzer.load_telemetry.return_value = df

        # Stats without miss_rate column
        stats = pd.DataFrame({
            'latency_us_mean': [100.0],
        }, index=['goertzel'])
        analyzer.calculate_statistics.return_value = stats

        args = self._make_args()
        result = execute(args)
        assert result == 1

    @patch('cortex.commands.check_deadline.get_most_recent_run')
    def test_no_runs_found(self, mock_recent):
        mock_recent.return_value = None
        args = self._make_args(run_name=None)
        result = execute(args)
        assert result == 1
