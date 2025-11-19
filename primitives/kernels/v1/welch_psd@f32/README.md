# Welch Power Spectral Density (PSD) Kernel

This kernel estimates the Power Spectral Density (PSD) of an input signal using Welch's method. It splits the signal into overlapping segments, applies a window function, computes the FFT, and averages the periodograms.

## Signal Model

For a signal $x[n]$, Welch's method computes the PSD estimate $\hat{P}_{xx}(f)$:

$$ \hat{P}_{xx}(f) = \frac{1}{K} \sum_{k=0}^{K-1} P_{k}(f) $$

Where $P_k(f)$ is the modified periodogram of the $k$-th segment:

$$ P_k(f) = \frac{1}{L U} \left| \sum_{n=0}^{L-1} x_k[n] w[n] e^{-j 2\pi f n} \right|^2 $$

- $L$: Segment length (`n_fft`)
- $w[n]$: Window function (Hann)
- $U$: Normalization factor ($U = \sum w^2[n]$)
- $K$: Number of segments

## Configuration

- `n_fft`: Length of the FFT (default: 256).
- `n_overlap`: Number of points of overlap (default: 128).
- `window`: Window function name (default: "hann").

## Implementation Details

- Uses **KissFFT** (vendored) for the FFT computation.
- Implements a sliding buffer to handle overlap between processing windows efficiently.
- Output size is `n_fft / 2 + 1` (one-sided spectrum for real inputs).
