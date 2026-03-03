"""Tests for device resolution and capability validation utilities."""
from unittest.mock import patch


class TestResolveDevice:
    """Tests for YAML-based device resolution."""

    def test_resolve_by_yaml_path(self):
        """Explicit path loads YAML directly."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("primitives/devices/m1-macos.yaml")
        assert spec is not None
        assert spec["device"]["name"] == "Apple M1 (macOS)"
        assert "frequency" in spec["device"]

    def test_resolve_by_short_name(self):
        """Short name maps to primitives/devices/{name}.yaml."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("m1-macos")
        assert spec is not None
        assert spec["device"]["name"] == "Apple M1 (macOS)"

    def test_resolve_none_returns_none(self):
        """No device arg returns None."""
        from cortex.utils.device import resolve_device
        assert resolve_device(None) is None
        assert resolve_device() is None

    def test_resolve_nonexistent_path_returns_none(self):
        """Non-existent YAML path returns None."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("nonexistent.yaml")
        assert spec is None

    def test_resolve_short_name_nonexistent_returns_none(self):
        """Short name with no matching YAML file returns None."""
        from cortex.utils.device import resolve_device
        spec = resolve_device("nonexistent_device")
        assert spec is None


class TestValidateCapabilities:
    """Tests for runtime capability validation."""

    def test_returns_copy_not_mutating_original(self):
        """validate_capabilities returns a copy, not mutating the original."""
        from cortex.utils.device import validate_capabilities
        spec = {"device": {"name": "Test",
                           "pmu": {"instruction_count": True, "l1d_misses": True,
                                   "memory_stall_hierarchy": False, "backend_stall": False},
                           "os_noise": {"tracer": None},
                           "frequency": {"model": "fixed", "max_hz": 3e9, "per_sample": False}}}
        with patch('cortex.utils.device._probe_pmu',
                   return_value={"pmu_available": False, "cpu_freq_hz": 0}):
            validated = validate_capabilities(spec)
        assert spec["device"]["name"] == "Test"
        assert validated["device"]["name"] == "Test"
