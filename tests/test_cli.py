#!/usr/bin/env python3
"""
Basic smoke tests for CORTEX CLI commands
Run with: python3 tests/test_cli.py
"""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from cortex.utils.discovery import discover_kernels
from cortex.utils.analyzer import TelemetryAnalyzer

def test_discover_kernels():
    """Test kernel discovery from registry"""
    kernels = discover_kernels()
    assert len(kernels) > 0, "Should find at least one kernel"
    assert 'goertzel' in [k['name'] for k in kernels], "Should find goertzel kernel"
    print("✓ test_discover_kernels passed")

def test_extract_kernel_name():
    """Test kernel name extraction from paths"""
    from pathlib import Path

    # Test new kernel-data structure
    path1 = Path("results/run-2025-11-10-001/kernel-data/goertzel/telemetry.ndjson")
    assert TelemetryAnalyzer._extract_kernel_name(path1) == "goertzel"

    # Test another kernel
    path2 = Path("results/batch_123/kernel-data/bandpass_fir/telemetry.csv")
    assert TelemetryAnalyzer._extract_kernel_name(path2) == "bandpass_fir"

    print("✓ test_extract_kernel_name passed")

if __name__ == '__main__':
    print("Running CORTEX CLI smoke tests...")
    test_discover_kernels()
    test_extract_kernel_name()
    print("\nAll tests passed! ✓")
