#!/usr/bin/env python3
"""
Universal synthetic signal generator for CORTEX.

Supports:
- sine_wave: Pure sinusoidal waveform (peak amplitude)
- pink_noise: 1/f noise with realistic EEG spectral properties (RMS amplitude)

Memory safety:
- High-channel datasets (>512ch): Chunked generation with memory-mapped output
- Low-channel datasets (≤512ch): Full in-memory generation
"""

import numpy as np
import tempfile
import os
from typing import Dict, Any, Union


class SyntheticGenerator:
    """
    Generate synthetic EEG-like signals.

    Returns:
        Union[np.ndarray, str]:
            - np.ndarray for low-channel datasets (≤512 channels)
            - str (file path) for high-channel datasets (>512 channels)
    """

    def generate(self,
                 signal_type: str,
                 channels: int,
                 sample_rate_hz: int,
                 duration_s: float,
                 params: Dict[str, Any]) -> Union[np.ndarray, str]:
        """
        Generate synthetic data.

        Args:
            signal_type: "sine_wave" or "pink_noise"
            channels: Number of channels (1-4096)
            sample_rate_hz: Sampling rate in Hz
            duration_s: Duration in seconds
            params: Generation parameters (amplitude, frequency, seed, etc.)

        Returns:
            np.ndarray (channels ≤ 512) or file path (channels > 512)

        Raises:
            ValueError: If signal_type unknown or parameters invalid
        """
        # Validate numeric parameters (lower and upper bounds)
        if not (1 <= channels <= 4096):
            raise ValueError(f"channels must be 1-4096 (got {channels})")
        if not (1 <= sample_rate_hz <= 50000):
            raise ValueError(f"sample_rate_hz must be 1-50000 Hz (got {sample_rate_hz})")
        if not (0.01 <= duration_s <= 3600):
            raise ValueError(f"duration_s must be 0.01-3600s (got {duration_s})")

        n_samples = int(duration_s * sample_rate_hz)

        # Validate minimum samples for FFT-based generation (prevents division by zero)
        if signal_type == "pink_noise" and n_samples < 16:
            raise ValueError(
                f"Pink noise requires at least 16 samples for FFT generation. "
                f"Got {n_samples} samples (duration_s={duration_s}, sample_rate_hz={sample_rate_hz}). "
                f"Increase duration_s to at least {16.0 / sample_rate_hz:.3f}s"
            )

        if signal_type == "sine_wave":
            # Sine is cheap - always return ndarray
            return self._generate_sine(n_samples, channels, sample_rate_hz, params)

        elif signal_type == "pink_noise":
            if channels > 512:
                # High-channel: use chunked generation (returns file path)
                return self._generate_pink_noise_chunked(
                    n_samples, channels, sample_rate_hz, params
                )
            else:
                # Low-channel: generate in memory (returns ndarray)
                return self._generate_pink_noise_simple(
                    n_samples, channels, sample_rate_hz, params
                )

        else:
            raise ValueError(f"Unknown signal_type: {signal_type}")

    def _generate_sine(self, n_samples: int, channels: int,
                      sample_rate_hz: int, params: Dict) -> np.ndarray:
        """
        Generate pure sinusoidal waveform with PEAK amplitude.

        Args:
            amplitude_uv_peak: Peak amplitude (signal ranges from -amp to +amp)

        Returns:
            np.ndarray: Shape (n_samples, channels), dtype=float32
        """
        freq = params.get('frequency_hz', 10.0)
        amp_peak = params.get('amplitude_uv_peak', 100.0)

        t = np.arange(n_samples) / sample_rate_hz
        signal = amp_peak * np.sin(2 * np.pi * freq * t)

        # Replicate to all channels (identical across channels)
        return np.tile(signal[:, None], (1, channels)).astype(np.float32)

    def _generate_pink_noise_simple(self, n_samples: int, channels: int,
                                    sample_rate_hz: int, params: Dict) -> np.ndarray:
        """
        Generate pink noise in memory (for low-channel datasets).

        Args:
            amplitude_uv_rms: RMS amplitude (standard deviation of zero-mean signal)

        Returns:
            np.ndarray: Shape (n_samples, channels), dtype=float32
        """
        amp_rms = params.get('amplitude_uv_rms', 100.0)
        rng = np.random.default_rng(params.get('seed', 42))

        # Generate all channels at once
        batch_data = self._generate_batch_vectorized(
            n_samples, channels, sample_rate_hz, rng, amp_rms
        )

        return batch_data.T.astype(np.float32)  # Shape: (n_samples, channels)

    def _generate_pink_noise_chunked(self, n_samples: int, channels: int,
                                     sample_rate_hz: int, params: Dict) -> str:
        """
        Generate pink noise in channel batches with memory-mapped output.

        Memory profile:
        - Batch size: 128 channels
        - Peak transient: ~60-80MB per batch (float64 FFT workspace)
        - Output: Disk-backed memmap (not loaded into RAM)

        Args:
            amplitude_uv_rms: RMS amplitude

        Returns:
            str: Path to generated .float32 file
        """
        BATCH_SIZE = 128
        amp_rms = params.get('amplitude_uv_rms', 100.0)
        rng = np.random.default_rng(params.get('seed', 42))

        # Create memory-mapped file (disk-backed array)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.float32')
        temp_file.close()  # Close file handle, keep path

        data_mmap = np.memmap(
            temp_file.name,
            dtype='float32',
            mode='w+',
            shape=(n_samples, channels)
        )

        print(f"[generator] Generating {channels}ch × {n_samples} samples...")
        print(f"[generator] Output: {temp_file.name}")
        print(f"[generator] File size: {(n_samples * channels * 4) / 1e6:.1f} MB")

        # Generate in batches
        for batch_start in range(0, channels, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, channels)
            batch_channels = batch_end - batch_start

            # Generate batch (vectorized)
            batch_data = self._generate_batch_vectorized(
                n_samples, batch_channels, sample_rate_hz, rng, amp_rms
            )

            # Write to memmap (flushes to disk incrementally)
            data_mmap[:, batch_start:batch_end] = batch_data.T.astype(np.float32)

            # Explicit cleanup
            del batch_data

            # Progress logging
            if batch_end % 256 == 0 or batch_end == channels:
                progress = (batch_end / channels) * 100
                print(f"[generator] {progress:.0f}% complete ({batch_end}/{channels} channels)")

        # Flush and close memmap
        data_mmap.flush()
        del data_mmap

        print(f"[generator] Generation complete")

        return temp_file.name  # Return file path, not data

    def _generate_batch_vectorized(self, n_samples: int, batch_channels: int,
                                   sample_rate_hz: int,
                                   rng: np.random.Generator,
                                   amp_rms: float) -> np.ndarray:
        """
        Vectorized pink noise generation for a channel batch.

        Performance: ~10× faster than per-channel loop.

        Algorithm:
        1. Generate complex white noise in frequency domain (all channels)
        2. Shape spectrum as 1/sqrt(f) for pink noise (-3dB/octave)
        3. Vectorized IRFFT across all channels
        4. Normalize to RMS per channel (zero-mean enforced)

        Args:
            n_samples: Number of time samples
            batch_channels: Number of channels in this batch
            sample_rate_hz: Sampling rate
            rng: NumPy random generator
            amp_rms: Target RMS amplitude

        Returns:
            np.ndarray: Shape (batch_channels, n_samples), dtype=float64
        """
        # Frequency array (correct sample rate usage)
        freqs = np.fft.rfftfreq(n_samples, d=1.0/sample_rate_hz)[1:]  # Skip DC
        n_freqs = len(freqs)

        # Vectorized complex white noise (all channels at once)
        real = rng.standard_normal((batch_channels, n_freqs))
        imag = rng.standard_normal((batch_channels, n_freqs))
        spectrum = (real + 1j * imag) / np.sqrt(freqs[None, :])

        # Pad DC bin (zero)
        full_spectrum = np.zeros((batch_channels, n_samples//2 + 1), dtype=complex)
        full_spectrum[:, 0] = 0.0  # Zero DC
        full_spectrum[:, 1:] = spectrum

        # Vectorized IRFFT (all channels simultaneously)
        batch_data = np.fft.irfft(full_spectrum, n=n_samples, axis=1)

        # Normalize to RMS per channel
        for c in range(batch_channels):
            signal = batch_data[c]

            # Enforce zero-mean (RMS != std dev unless mean=0)
            signal = signal - signal.mean()

            # True RMS
            rms_actual = np.sqrt(np.mean(signal**2))

            # Scale to target RMS
            batch_data[c] = signal / rms_actual * amp_rms

        return batch_data  # Shape: (batch_channels, n_samples)


# Module-level function for easy testing
def generate_dataset(signal_type: str, channels: int, sample_rate_hz: int,
                    duration_s: float, output_path: str = None, **kwargs):
    """
    Convenience function for generating datasets from command line.

    Example:
        python generator.py sine_wave 64 160 10.0 output.float32 --frequency_hz=10 --amplitude_uv_peak=50
    """
    gen = SyntheticGenerator()
    result = gen.generate(signal_type, channels, sample_rate_hz, duration_s, kwargs)

    if isinstance(result, str):
        # Generator returned file path (high-channel mode)
        if output_path:
            os.rename(result, output_path)
            print(f"Saved to: {output_path}")
        else:
            print(f"Generated: {result}")
    else:
        # Generator returned ndarray (low-channel mode)
        if output_path is None:
            output_path = f"synthetic_{signal_type}_{channels}ch.float32"
        result.tofile(output_path)
        print(f"Saved to: {output_path}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 5:
        print("Usage: python generator.py <signal_type> <channels> <sample_rate_hz> <duration_s> [output_path] [--param=value ...]")
        print("\nExample:")
        print("  python generator.py pink_noise 1024 160 60.0 output.float32 --amplitude_uv_rms=100 --seed=42")
        sys.exit(1)

    signal_type = sys.argv[1]
    channels = int(sys.argv[2])
    sample_rate_hz = int(sys.argv[3])
    duration_s = float(sys.argv[4])
    output_path = sys.argv[5] if len(sys.argv) > 5 and not sys.argv[5].startswith('--') else None

    # Parse kwargs
    kwargs = {}
    # Start after output_path if present (index 6), otherwise after duration_s (index 5)
    for arg in sys.argv[6 if output_path else 5:]:
        if arg.startswith('--'):
            key, value = arg[2:].split('=')
            # Try to parse as number, fall back to string
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
            kwargs[key] = value

    generate_dataset(signal_type, channels, sample_rate_hz, duration_s, output_path, **kwargs)
