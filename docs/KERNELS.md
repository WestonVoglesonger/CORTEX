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
  * Window 1 = samples 0-80
  * Window 2 = samples 81-160

* **Number of Channels (C)** = 64
      

## Common Average Reference (CAR)
* Signal model and input/output domain:
 * Exact equations:
* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: 
* Oracle definition: 
* Acceptance criteria: 

## Notch IIR (biquad) at 50/60 Hz
* Signal model and input/output domain:
 * Exact equations:
* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: 
* Oracle definition: 
* Acceptance criteria: 

## Band-pass FIR (8–30 Hz)
* Signal model and input/output domain:
 * Exact equations:
* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: 
* Oracle definition: 
* Acceptance criteria: 

## Goertzel Bandpower (and optional Welch PSD)
* Signal model and input/output domain:
 * Exact equations:
* Numerical format: specify float32 as default and plan for quantized formats (Q15 and Q7), with tolerances for comparing quantized outputs to float32 references.
* Edge-case handling: 
* Oracle definition: 
* Acceptance criteria: 

