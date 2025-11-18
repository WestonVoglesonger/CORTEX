# Welch Power Spectral Density (PSD) Kernel

This kernel implements Welch's method for estimating the power spectral density of a signal. It splits the data into overlapping segments, computes a modified periodogram for each segment, and averages the periodograms.

## Algorithm

1.  **Segmentation**: The input signal is divided into overlapping segments of length `n_fft`.
2.  **Windowing**: Each segment is multiplied by a window function (e.g., Hann).
3.  **FFT**: The Fast Fourier Transform is computed for each windowed segment.
4.  **Periodogram**: The squared magnitude of the FFT is computed and scaled.
5.  **Averaging**: The periodograms are averaged to produce the final PSD estimate.

## Configuration

- `n_fft`: Length of the FFT (default: 256).
- `n_overlap`: Number of points of overlap (default: 128).
- `window`: Window function name (default: "hann").

## Implementation Details

- Uses **KissFFT** (vendored) for the FFT computation.
- Implements a sliding buffer to handle overlap between processing windows efficiently.
- Output size is `n_fft / 2 + 1` (one-sided spectrum for real inputs).
