"""Tests for run command device/deploy resolution (Phase 2)."""
import argparse
import pytest
from unittest.mock import patch, MagicMock, Mock

from cortex.commands.run import (
    resolve_device_arg,
    resolve_deploy_arg,
)


class TestResolveDeviceArg:
    """Tests for resolve_device_arg() — resolves device primitive name/path."""

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


class TestResolveDeployArg:
    """Tests for resolve_deploy_arg() — resolves deployment strategy."""

    def test_cli_wins_over_config(self):
        """CLI --deploy ssh://pi@rpi wins over config deploy: tcp://host:9000."""
        args = argparse.Namespace(deploy='ssh://pi@rpi')
        config = {'deploy': 'tcp://host:9000'}

        result = resolve_deploy_arg(args, config)

        assert result == 'ssh://pi@rpi'

    def test_config_used_when_no_cli(self):
        """Config deploy: ssh://pi@rpi used when no CLI flag."""
        args = argparse.Namespace(deploy=None)
        config = {'deploy': 'ssh://pi@rpi'}

        result = resolve_deploy_arg(args, config)

        assert result == 'ssh://pi@rpi'

    def test_none_when_both_absent(self):
        """Returns None when both CLI and config absent (local execution)."""
        args = argparse.Namespace(deploy=None)
        config = {}

        result = resolve_deploy_arg(args, config)

        assert result is None

    def test_none_when_no_config(self):
        """Returns None when config is None and no CLI flag."""
        args = argparse.Namespace(deploy=None)

        result = resolve_deploy_arg(args, None)

        assert result is None

    def test_cli_empty_string_ignored(self):
        """Empty string CLI --deploy treated as absent."""
        args = argparse.Namespace(deploy='')
        config = {'deploy': 'ssh://pi@rpi'}

        result = resolve_deploy_arg(args, config)

        assert result == 'ssh://pi@rpi'


class TestRunParser:
    """Tests for run command parser updates."""

    def test_deploy_flag_exists(self):
        """Parser accepts --deploy flag."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop', '--deploy', 'ssh://pi@rpi'])
        assert args.deploy == 'ssh://pi@rpi'

    def test_device_and_deploy_separate(self):
        """--device and --deploy are independent flags."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args([
            '--kernel', 'noop',
            '--device', 'rpi4',
            '--deploy', 'ssh://pi@rpi',
        ])
        assert args.device == 'rpi4'
        assert args.deploy == 'ssh://pi@rpi'

    def test_deploy_defaults_to_none(self):
        """--deploy defaults to None when not specified."""
        from cortex.commands.run import setup_parser

        parser = argparse.ArgumentParser()
        setup_parser(parser)

        args = parser.parse_args(['--kernel', 'noop'])
        assert args.deploy is None


class TestRunExecuteDeviceDeploy:
    """Tests for refactored execute() with device/deploy separation."""

    def _make_args(self, **kwargs):
        """Create a Namespace with defaults for execute()."""
        defaults = dict(
            kernel='noop', all=False, config=None,
            run_name='test-run', duration=None, repeats=None,
            warmup=None, state=None, verbose=False,
            device=None, deploy=None,
            dtype='f32', load_profile=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @patch('cortex.commands.run.HarnessRunner')
    @patch('cortex.commands.run.generate_run_name', return_value='test-run')
    @patch('cortex.commands.run.resolve_device', return_value={'device': {'name': 'Apple M1'}})
    @patch('cortex.commands.run.validate_capabilities', side_effect=lambda x: x)
    def test_device_only_resolves_local(self, mock_validate, mock_resolve, mock_gen_name, mock_runner_cls):
        """--device m1 with no --deploy = local execution, resolve_device called."""
        from cortex.commands.run import execute

        mock_runner = MagicMock()
        mock_runner.run_single_kernel.return_value = 'results/test-run'
        mock_runner_cls.return_value = mock_runner

        args = self._make_args(device='m1')
        result = execute(args)

        assert result == 0
        mock_resolve.assert_called_once_with('m1')
        mock_validate.assert_called_once()
        # No deployer should be created (local execution)
        mock_runner.run_single_kernel.assert_called_once()
        call_kwargs = mock_runner.run_single_kernel.call_args
        assert call_kwargs.kwargs.get('transport_uri') is None or 'transport_uri' not in call_kwargs.kwargs

    @patch('cortex.commands.run.HarnessRunner')
    @patch('cortex.commands.run.generate_run_name', return_value='test-run')
    @patch('cortex.commands.run.DeployerFactory')
    @patch('cortex.commands.run.resolve_device', return_value={'device': {'name': 'RPi4'}})
    @patch('cortex.commands.run.validate_capabilities', side_effect=lambda x: x)
    def test_device_plus_deploy_ssh(self, mock_validate, mock_resolve, mock_factory, mock_gen_name, mock_runner_cls):
        """--device rpi4 --deploy ssh://pi@rpi triggers deployer AND resolves device."""
        from cortex.commands.run import execute

        mock_deployer = MagicMock()
        mock_deployer.deploy.return_value = MagicMock(transport_uri='tcp://192.168.1.100:9000')
        mock_deployer.cleanup.return_value = MagicMock(success=True)
        mock_factory.from_device_string.return_value = mock_deployer

        mock_runner = MagicMock()
        mock_runner.run_single_kernel.return_value = 'results/test-run'
        mock_runner_cls.return_value = mock_runner

        args = self._make_args(device='rpi4', deploy='ssh://pi@rpi')
        result = execute(args)

        assert result == 0
        mock_resolve.assert_called_once_with('rpi4')
        mock_factory.from_device_string.assert_called_once_with('ssh://pi@rpi')

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
