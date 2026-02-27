"""Tests for run command device resolution."""
import argparse
import pytest
from unittest.mock import patch, MagicMock, Mock

from cortex.commands.run import (
    resolve_device_arg,
)


class TestResolveDeviceArg:
    """Tests for resolve_device_arg() — resolves device/deployment string."""

    def test_cli_wins_over_config(self):
        """CLI --device rpi4 wins over config device: m1."""
        args = argparse.Namespace(device='rpi4')
        config = {'device': 'm1'}

        result = resolve_device_arg(args, config)

        assert result == 'rpi4'

    def test_config_used_when_no_cli(self):
        """Config device: rpi4 used when no CLI flag."""
        args = argparse.Namespace(device=None)
        config = {'device': 'rpi4'}

        result = resolve_device_arg(args, config)

        assert result == 'rpi4'

    def test_none_when_both_absent(self):
        """Returns None when both CLI and config absent (auto-detect)."""
        args = argparse.Namespace(device=None)
        config = {}

        result = resolve_device_arg(args, config)

        assert result is None

    def test_none_when_no_config(self):
        """Returns None when config is None and no CLI flag."""
        args = argparse.Namespace(device=None)

        result = resolve_device_arg(args, None)

        assert result is None

    def test_cli_empty_string_ignored(self):
        """Empty string CLI --device treated as absent."""
        args = argparse.Namespace(device='')
        config = {'device': 'm1'}

        result = resolve_device_arg(args, config)

        assert result == 'm1'

    def test_deployment_string_passed_through(self):
        """Deployment strings like ssh://pi@rpi are valid --device values."""
        args = argparse.Namespace(device='ssh://pi@rpi')
        result = resolve_device_arg(args, None)
        assert result == 'ssh://pi@rpi'

    def test_tcp_transport_passed_through(self):
        """TCP transport URIs are valid --device values."""
        args = argparse.Namespace(device='tcp://192.168.1.100:9000')
        result = resolve_device_arg(args, None)
        assert result == 'tcp://192.168.1.100:9000'


class TestRunParser:
    """Tests for run command parser."""

    def test_device_flag_exists(self):
        """Parser accepts --device flag."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop', '--device', 'rpi4'])
        assert args.device == 'rpi4'

    def test_device_accepts_deployment_strings(self):
        """--device accepts deployment strings (ssh, tcp)."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop', '--device', 'nvidia@192.168.1.123'])
        assert args.device == 'nvidia@192.168.1.123'

    def test_device_defaults_to_none(self):
        """--device defaults to None when not specified."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop'])
        assert args.device is None

    def test_no_deploy_flag(self):
        """--deploy flag no longer exists (merged into --device)."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        with pytest.raises(SystemExit):
            parser.parse_args(['--kernel', 'noop', '--deploy', 'ssh://pi@rpi'])

    def test_no_load_profile_flag(self):
        """--load-profile flag removed (use config instead)."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop'])
        assert not hasattr(args, 'load_profile')

    def test_no_duration_flag(self):
        """--duration flag removed (use config instead)."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop'])
        assert not hasattr(args, 'duration')

    def test_no_repeats_flag(self):
        """--repeats flag removed (use config instead)."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop'])
        assert not hasattr(args, 'repeats')

    def test_no_warmup_flag(self):
        """--warmup flag removed (use config instead)."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop'])
        assert not hasattr(args, 'warmup')


class TestRunExecuteDevice:
    """Tests for execute() with unified device flag."""

    def _make_args(self, **kwargs):
        """Create a Namespace with defaults for execute()."""
        defaults = dict(
            kernel='noop', all=False, config=None,
            run_name='test-run', state=None, verbose=False,
            device=None, dtype='f32',
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch('cortex.commands.run.HarnessRunner')
    @patch('cortex.commands.run.generate_run_name', return_value='test-run')
    @patch('cortex.commands.run.resolve_device', return_value={'device': {'name': 'Apple M1'}})
    @patch('cortex.commands.run.validate_capabilities', side_effect=lambda x: x)
    def test_device_spec_resolves_local(self, mock_validate, mock_resolve, mock_gen_name, mock_runner_cls):
        """--device m1 = local execution, resolve_device called."""
        from cortex.commands.run import execute

        mock_runner = MagicMock()
        mock_runner.run_single_kernel.return_value = 'results/test-run'
        mock_runner_cls.return_value = mock_runner

        args = self._make_args(device='m1')
        result = execute(args)

        assert result == 0
        mock_resolve.assert_called_once_with('m1')
        mock_validate.assert_called_once()
        mock_runner.run_single_kernel.assert_called_once()

    @patch('cortex.commands.run.HarnessRunner')
    @patch('cortex.commands.run.generate_run_name', return_value='test-run')
    @patch('cortex.commands.run.resolve_device', return_value={'device': {'name': 'Apple M1'}})
    @patch('cortex.commands.run.validate_capabilities', side_effect=lambda x: x)
    def test_device_spec_passed_to_runner(self, mock_validate, mock_resolve, mock_gen_name, mock_runner_cls):
        """device_spec from resolve_device() is forwarded to runner."""
        from cortex.commands.run import execute

        mock_runner = MagicMock()
        mock_runner.run_single_kernel.return_value = 'results/test-run'
        mock_runner_cls.return_value = mock_runner

        device_spec = {'device': {'name': 'Apple M1'}}

        args = self._make_args(device='m1')
        result = execute(args)

        assert result == 0
        call_kwargs = mock_runner.run_single_kernel.call_args
        assert call_kwargs.kwargs.get('device_spec') == device_spec

    @patch('cortex.commands.run.generate_run_name', return_value='test-run')
    @patch('cortex.commands.run.resolve_device', return_value=None)
    def test_invalid_device_name_errors(self, mock_resolve, mock_gen_name):
        """--device with unrecognized name (not a URI) errors instead of silent fallback."""
        from cortex.commands.run import execute

        args = self._make_args(device='m1')  # 'm1' not found by resolve_device
        result = execute(args)

        assert result == 1

    @patch('cortex.commands.run.HarnessRunner')
    @patch('cortex.commands.run.generate_run_name', return_value='test-run')
    @patch('cortex.commands.run.resolve_device', return_value=None)
    @patch('cortex.commands.run.DeployerFactory')
    def test_deployment_uri_triggers_deployer(self, mock_factory, mock_resolve, mock_gen_name, mock_runner_cls):
        """--device with URI (contains ://) triggers deployment, not device resolution."""
        from cortex.commands.run import execute

        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = MagicMock(transport_uri='tcp://192.168.1.100:9000')
        mock_deployer.cleanup.return_value = MagicMock(success=True)
        mock_factory.from_device_string.return_value = mock_deployer

        mock_runner = MagicMock()
        mock_runner.run_single_kernel.return_value = 'results/test-run'
        mock_runner_cls.return_value = mock_runner

        args = self._make_args(device='ssh://pi@rpi')
        result = execute(args)

        assert result == 0
        mock_factory.from_device_string.assert_called_once_with('ssh://pi@rpi')
