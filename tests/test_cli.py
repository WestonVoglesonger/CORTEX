#!/usr/bin/env python3
"""
Basic smoke tests for CORTEX CLI commands
Run with: python3 tests/test_cli.py
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cortex_cli.core.config import discover_kernels, generate_config
from cortex_cli.core.analyzer import _extract_kernel_name

def test_discover_kernels():
    """Test kernel discovery from registry"""
    kernels = discover_kernels()
    assert len(kernels) > 0, "Should find at least one kernel"
    assert 'goertzel' in [k['name'] for k in kernels], "Should find goertzel kernel"
    print("✓ test_discover_kernels passed")

def test_generate_config():
    """Test YAML config generation"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.yaml"
        result = generate_config("goertzel", str(output_path))
        assert result, "Config generation should succeed"
        assert output_path.exists(), "Config file should be created"
        content = output_path.read_text()
        assert "goertzel" in content, "Config should contain kernel name"
        print("✓ test_generate_config passed")

def test_extract_kernel_name():
    """Test kernel name extraction from paths"""
    from pathlib import Path

    # Test filename pattern
    path1 = Path("results/1762315905289_goertzel_telemetry.ndjson")
    assert _extract_kernel_name(path1) == "goertzel"

    # Test directory pattern
    path2 = Path("results/batch_123/goertzel_run/telemetry.csv")
    assert _extract_kernel_name(path2) == "goertzel"

    print("✓ test_extract_kernel_name passed")

if __name__ == '__main__':
    print("Running CORTEX CLI smoke tests...")
    test_discover_kernels()
    test_generate_config()
    test_extract_kernel_name()
    print("\nAll tests passed! ✓")
