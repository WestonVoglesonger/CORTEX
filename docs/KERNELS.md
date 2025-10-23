# Kernel Specifications


## Spec Fields
 * Signal model and input/output domain: x\[*t, c*] defined over windows of length *W* with C channels, units (µV) and assumed sampling rate.
 * Exact equations (e.g., difference equations for IIR, impulse response for FIR) and design parameters (f<sub>0</sub>, *Q*, number of taps, window type, passband/stopband tolerances, group delay). Boundary conditions and initial state should be explicit.
 * Parameterization: fixed F<sub>s</sub>, *W, H, C* and kernel parameters.
* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: NaNs, missing channels, zero padding and persistent state
across windows.
* Oracle definition: provide a reference Python function using SciPy/MNE that implements the kernel exactly, along with numerical tolerances (absolute and relative) for correctness checks.
* Acceptance criteria: maximum absolute and relative error thresholds, plus group
delay considerations.

### Fixed Parameters (applied to all kernels)
* **Sampling Rate (F<sub>s</sub>**): 160Hz (frozen from dataset)

* **Window Length (W)** = 160 samples

* **Hop (H)** = 80 samples
  * Window 0 = samples 0-159
  * Window 1 = samples 80-239
  * Window 2 = samples 160-319

* **Number of Channels (C)** = 64
* **Units**: µV (internal libs may use V; we convert as needed but report µV)

### Shared edge-case policy
- **NaNs**: treated as missing; exclude from CAR mean; otherwise substitute 0 for filtering
- **Missing/bad channels**: excluded from CAR mean; filtered independently
- **Window boundaries**: IIR state **persists** across windows; FIR keeps last `numtaps−1` samples per channel
- **First window**: IIR/FIR states zero-initialized

### Shared Numerical Format and tolerances
-  **Reference type**: float32
- **Quantized types**:  
  - **Q15**: int16 with scale S=32768 (value ≈ q / S)  
  - **Q7**: int8 with scale S=128
- **Compare quantized→float32** by dequantizing then checking: `rtol = 1e-3`, `atol = 1e-3` (start here; tighten if stable)
- **Float32 reference checks**: `rtol = 1e-5`, `atol = 1e-6`      

------ 

## Common Average Reference (CAR)
* Signal model and input/output domain: 
    * Input `x[t,c]` with shape `[W×C]` in µV → Output `y[t,c]` `[W×C]` in µV.
 * Exact equations: Let `G` be the set of good channels (default all 64):

$$\bar{x}[t] = \frac{1}{|G|}\sum_{c\in G} x[t,c], \qquad
y[t,c] = x[t,c] - \bar{x}[t]$$



* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling:  At time t, exclude channels where `x[t,c]` is NaN from the mean and divisor. If all are NaN at t, output zeros.
* Oracle definition: 
```python
import numpy as np
def car_ref(x):  # x: (W,C) float32 in µV
    m = np.nanmean(x, axis=1, keepdims=True)
    return (x - m).astype(np.float32)
```
* Acceptance criteria: 
    * Float32 vs oracle within rtol=1e-5, atol=1e-6
    * Mean across channels ≈ 0 at each t (|mean| < 1e-4 µV)    

## Notch IIR (biquad) at 50/60 Hz
* Signal model and input/output domain: 
    * Input [W×C] µV → Output [W×C] µV, per-channel IIR with **persistent** state across windows.
 * Exact equations: 
    * Second-order notch with target $f0$ and quality factor $Q$: 

    $$H(Z) = \frac{1-2cos(w_0)z^{-1}+z^{-2}}{1-2rcos(w_0)z^{-1}+r^{2}z^{-2}}, \qquad w_0 = \frac{2 \pi f_0}{F_s}$$
    * Difference equation per channel: 
   
    $$y[n]=b0​x[n]+b1​x[n−1]+b2​x[n−2]−a1​y[n−1]−a2​y[n−2]$$
    * Design (b,a) via a standard notch designer (e.g., SciPy iirnotch).

* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: Treat NaNs as 0 for filtering; reject configs where f0 ≈ 0
* Oracle definition: 
```python
from scipy.signal import iirnotch, lfilter

def notch_ref(x, fs=160.0, f0=60.0, Q=30.0, zi=None):
    b, a = iirnotch(f0, Q, fs=fs)
    if zi is None:
        y = lfilter(b, a, x, axis=0)
        return y.astype('float32'), None
    y, zf = lfilter(b, a, x, axis=0, zi=zi)
    return y.astype('float32'), zf
```
* Acceptance criteria: 
    * Samplewise match within rtol=1e-5, atol=1e-6 vs oracle (with identical state)


## Band-pass FIR (8–30 Hz)
* Signal model and input/output domain: Input [W×C] µV → Output [W×C] µV, linear-phase FIR with known delay and persistent tail across windows.
 * Exact equations:
    * Length-N FIR with taps b[k], k=0..N−1 (Hamming window design):
    
    $$y[n] =   \sum_{k=0}^{N-1} b[k] x[n−k]$$
    * Use `firwin(N=129, [8,30], pass_zero=False, fs=160, window='hamming')`.

    * Group delay = (N−1)/2 = 64 samples = 0.4 s @ 160 Hz.
* Parameterization: `numtaps = 129`, `passband = [8,30] Hz`, window = Hamming
* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: Zero-init tail on first window; NaNs treated as 0
* Oracle definition: 
```python
from scipy.signal import firwin, lfilter

def fir_bp_ref(x, fs=160.0, numtaps=129):
    b = firwin(numtaps, [8, 30], pass_zero=False, fs=fs, window='hamming')
    return lfilter(b, [1.0], x, axis=0).astype('float32'), b
```

* Acceptance criteria:
* Samplewise rtol=1e-5, atol=1e-6 vs oracle (with identical carried tail)
 

## Goertzel Bandpower (and optional Welch PSD)
* Signal model and input/output domain: Operate per window (stateless). Input [W×C] µV → Output [B×C] µV², where B = number of defined bands.
 * Exact equations:
    * For window length N = W = 160 and bin k(frequency = $$f_k = k*F_s/N = k$$ Hz at Fs=160):

    $$s[n] = x[n] + 2 cos (\frac{2 \pi k}{N})s[n-1]-s[n-2], \qquad P_k=s[N-1]^2 + s[N-2]^2 - 2cos(\frac{2 \pi k}{N})s[N-1]s[N-2]$$

    * Bandpower = sum of P_k over bins in the band
* Numerical format: Float32 reference; quantized compare after dequant.
* Edge-case handling: None special; operates on each window independently.
* Oracle definition: 
```python
import numpy as np

def goertzel_bandpower_ref(x, fs=160.0, bands={'alpha':(8,13), 'beta':(13,30)}):
    # x: (W,C) in µV, W must be 160
    N = x.shape[0]
    out = []
    for (lo, hi) in bands.values():
        ks = np.arange(lo, hi+1, dtype=float)
        omega = 2*np.pi*ks/N
        coeff = 2*np.cos(omega)[:,None]             # (bins,1)
        # run per bin via vectorized recurrence
        s0 = np.zeros((len(ks), x.shape[1])); s1 = s0.copy(); s2 = s0.copy()
        for n in range(N):
            s0 = x[n][None,:] + coeff*s1 - s2
            s2, s1 = s1, s0
        Pk = s1*s1 + s2*s2 - coeff*s1*s2           # (bins,C)
        out.append(Pk.sum(axis=0))                  # sum over bins -> (C,)
    return np.vstack(out).astype('float32')        # (B,C)
```

* Acceptance criteria: 
    * Match oracle within rtol=1e-5, atol=1e-6
    * Cross-check: FFT method (np.fft.rfft) bin-sum within same tolerance on a test window
