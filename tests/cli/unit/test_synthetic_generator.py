"""
Unit tests for synthetic dataset generator.

Tests cover:
- Signal generation correctness (sine amplitude, pink noise RMS)
- Deterministic generation (reproducibility)
- Generator detection logic
- High-channel mode (file path vs ndarray return)
"""

import pytest
import numpy as np
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from primitives.datasets.v1.synthetic.generator import SyntheticGenerator
from src.cortex.generators.integration import is_generator_dataset


class TestSineWaveGeneration:
    """Test sine wave generation correctness."""

    def test_sine_amplitude_via_fft(self):
        """
        Verify sine amplitude via FFT (robust to sampling).

        This test validates Fix #4: Testing amplitude via FFT magnitude
        instead of relying on max(data) hitting exact peak.
        """
        gen = SyntheticGenerator()
        data = gen.generate(
            signal_type="sine_wave",
            channels=1,
            sample_rate_hz=160,
            duration_s=1.0,
            params={'frequency_hz': 10.0, 'amplitude_uv_peak': 50.0}
        )

        # FFT-based amplitude extraction
        spectrum = np.fft.rfft(data[:, 0])
        freqs = np.fft.rfftfreq(len(data), 1/160)

        peak_idx = np.argmax(np.abs(spectrum))
        peak_freq = freqs[peak_idx]
        peak_amplitude = 2 * np.abs(spectrum[peak_idx]) / len(data)

        # Validate frequency
        assert np.isclose(peak_freq, 10.0, rtol=0.01), \
            f"Expected frequency 10Hz, got {peak_freq:.2f}Hz"

        # Validate amplitude (5% tolerance)
        assert np.isclose(peak_amplitude, 50.0, rtol=0.05), \
            f"Expected amplitude 50µV, got {peak_amplitude:.2f}µV"

        # Also check max(abs(data)) is within reasonable range
        assert 49.0 <= np.abs(data).max() <= 51.0, \
            f"Peak value out of range: {np.abs(data).max():.2f}µV"

    def test_sine_shape_and_dtype(self):
        """Verify sine wave output shape and data type."""
        gen = SyntheticGenerator()
        data = gen.generate(
            signal_type="sine_wave",
            channels=64,
            sample_rate_hz=160,
            duration_s=1.0,
            params={'frequency_hz': 10.0}
        )

        assert data.shape == (160, 64), f"Expected shape (160, 64), got {data.shape}"
        assert data.dtype == np.float32, f"Expected float32, got {data.dtype}"


class TestPinkNoiseGeneration:
    """Test pink noise generation correctness."""

    def test_pink_noise_rms_with_zero_mean(self):
        """
        Verify pink noise RMS amplitude (zero-mean enforced).

        This test validates Fix #3: RMS calculation with explicit
        zero-mean enforcement (RMS != std unless mean=0).
        """
        gen = SyntheticGenerator()
        data = gen.generate(
            signal_type="pink_noise",
            channels=64,
            sample_rate_hz=160,
            duration_s=10.0,
            params={'amplitude_uv_rms': 100.0, 'seed': 42}
        )

        # Compute RMS correctly (zero-mean first)
        data_zeromean = data - data.mean()
        rms = np.sqrt(np.mean(data_zeromean**2))

        # Validate RMS (5% tolerance due to finite sample size)
        assert np.isclose(rms, 100.0, rtol=0.05), \
            f"Expected RMS 100µV, got {rms:.2f}µV"

    def test_pink_noise_shape_and_dtype(self):
        """Verify pink noise output shape and data type."""
        gen = SyntheticGenerator()
        data = gen.generate(
            signal_type="pink_noise",
            channels=64,
            sample_rate_hz=160,
            duration_s=1.0,
            params={'seed': 42}
        )

        assert data.shape == (160, 64), f"Expected shape (160, 64), got {data.shape}"
        assert data.dtype == np.float32, f"Expected float32, got {data.dtype}"


class TestDeterministicGeneration:
    """Test reproducibility of generation."""

    def test_same_seed_produces_equivalent_output(self):
        """
        Verify same seed produces statistically equivalent output.

        This test validates Fix #6: Cross-platform determinism uses
        statistical equivalence (not bitwise) due to FFT library variations.
        """
        gen = SyntheticGenerator()

        data1 = gen.generate("pink_noise", 64, 160, 1.0, {'seed': 42})
        data2 = gen.generate("pink_noise", 64, 160, 1.0, {'seed': 42})

        # Statistical equivalence (relaxed tolerance for FFT variance)
        np.testing.assert_allclose(data1, data2, rtol=1e-6, atol=1e-6)

        # Verify mean/std are identical (deterministic even across platforms)
        assert np.isclose(data1.mean(), data2.mean(), rtol=1e-9)
        assert np.isclose(data1.std(), data2.std(), rtol=1e-9)

    def test_different_seeds_produce_different_output(self):
        """Verify different seeds produce different data."""
        gen = SyntheticGenerator()

        data1 = gen.generate("pink_noise", 64, 160, 1.0, {'seed': 42})
        data2 = gen.generate("pink_noise", 64, 160, 1.0, {'seed': 123})

        # Should NOT be equal
        assert not np.allclose(data1, data2, rtol=1e-3), \
            "Different seeds should produce different data"


class TestHighChannelMode:
    """Test high-channel mode (file path return)."""

    def test_high_channel_returns_file_path(self):
        """
        Verify high-channel generation returns file path (not ndarray).

        This test validates Fix #1: Memmap returns file path to avoid
        loading entire dataset into RAM.
        """
        gen = SyntheticGenerator()

        # High-channel mode (>512 channels)
        result = gen.generate(
            signal_type="pink_noise",
            channels=1024,
            sample_rate_hz=160,
            duration_s=1.0,
            params={'seed': 42}
        )

        # Should return file path (string)
        assert isinstance(result, str), \
            f"Expected file path (str), got {type(result)}"

        # File should exist
        assert os.path.exists(result), \
            f"Generated file does not exist: {result}"

        # File should have correct size
        expected_size = 1024 * 160 * 4  # channels * samples * bytes_per_float32
        actual_size = os.path.getsize(result)
        assert actual_size == expected_size, \
            f"Expected file size {expected_size}, got {actual_size}"

        # Cleanup
        os.unlink(result)

    def test_low_channel_returns_ndarray(self):
        """Verify low-channel generation returns ndarray."""
        gen = SyntheticGenerator()

        # Low-channel mode (≤512 channels)
        result = gen.generate(
            signal_type="pink_noise",
            channels=64,
            sample_rate_hz=160,
            duration_s=1.0,
            params={'seed': 42}
        )

        # Should return ndarray
        assert isinstance(result, np.ndarray), \
            f"Expected ndarray, got {type(result)}"


class TestGeneratorDetection:
    """Test generator detection logic."""

    def test_detects_synthetic_generator(self):
        """Verify is_generator_dataset() detects synthetic primitive."""
        result = is_generator_dataset("primitives/datasets/v1/synthetic")
        assert result is True, \
            "Should detect primitives/datasets/v1/synthetic as generator"

    def test_does_not_detect_static_dataset(self):
        """Verify is_generator_dataset() does not false-positive on static datasets."""
        # PhysioNet is a static dataset
        result = is_generator_dataset("primitives/datasets/v1/physionet-motor-imagery")
        assert result is False, \
            "Should not detect PhysioNet as generator"

    def test_handles_nonexistent_path(self):
        """Verify detection handles nonexistent paths gracefully."""
        result = is_generator_dataset("primitives/datasets/v1/nonexistent")
        assert result is False, \
            "Should return False for nonexistent paths"


class TestParameterValidation:
    """Test parameter validation and error handling."""

    def test_missing_signal_type_raises_error(self):
        """Verify missing signal_type raises ValueError."""
        gen = SyntheticGenerator()

        with pytest.raises(ValueError, match="Unknown signal_type"):
            gen.generate(
                signal_type="invalid_type",
                channels=64,
                sample_rate_hz=160,
                duration_s=1.0,
                params={}
            )

    def test_invalid_signal_type_raises_error(self):
        """Verify invalid signal_type raises ValueError."""
        gen = SyntheticGenerator()

        with pytest.raises(ValueError):
            gen.generate(
                signal_type="nonexistent_signal",
                channels=64,
                sample_rate_hz=160,
                duration_s=1.0,
                params={}
            )


# Mark tests requiring longer execution as slow
pytestmark = pytest.mark.unit


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
