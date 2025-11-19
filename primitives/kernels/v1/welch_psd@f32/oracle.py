import numpy as np
from scipy.signal import welch
import argparse
import sys
import os

def compute(input_data, config):
    """
    Reference implementation of Welch's method using SciPy.
    
    Args:
        input_data (list/array): Input signal
        config (dict): Kernel configuration
            - n_fft: Length of FFT
            - n_overlap: Overlap length
            - window: Window function name
            
    Returns:
        list: Power Spectral Density estimate
    """
    n_fft = config.get('n_fft', 256)
    n_overlap = config.get('n_overlap', 128)
    window = config.get('window', 'hann')
    # Sampling rate: hardcoded to match CORTEX v1 EEG dataset (160 Hz)
    # Future versions should accept this as a parameter from the harness
    fs = 160.0
    
    # SciPy's welch function does exactly what we need
    # scaling='density' is the default, which is what we want for PSD
    # detrend=False matches standard DSP implementations unless specified
    # scipy.welch handles short inputs by zero-padding to nfft

    freqs, psd = welch(input_data, 
                       fs=fs, 
                       window=window, 
                       nperseg=n_fft, 
                       noverlap=n_overlap,
                       nfft=n_fft,
                       detrend=False,
                       scaling='density')
                       
    return psd.astype(np.float32)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Welch PSD Oracle')
    parser.add_argument('--test', type=str, help='Input binary file path')
    parser.add_argument('--output', type=str, help='Output binary file path')
    parser.add_argument('--state', type=str, help='State file path (unused for Welch)')
    
    args = parser.parse_args()
    
    if args.test and args.output:
        # Harness mode
        try:
            # Read input (assuming float32)
            # The harness writes raw floats to the file
            input_data = np.fromfile(args.test, dtype=np.float32)
            
            # Configuration (hardcoded to match C implementation defaults for now)
            # In a real scenario, this might come from a config file or args
            config = {'n_fft': 256, 'n_overlap': 128, 'window': 'hann'}
            
            # Infer dimensions from input size
            # The harness passes a flattened buffer [W * C].
            # Default window size is 160 samples for EEG @ 160 Hz
            WINDOW_SIZE = 160

            # Try to infer channels
            if len(input_data) % WINDOW_SIZE == 0:
                channels = len(input_data) // WINDOW_SIZE
            elif len(input_data) % 256 == 0:
                # Fallback: try alternate window size
                WINDOW_SIZE = 256
                channels = len(input_data) // WINDOW_SIZE
            else:
                # Cannot infer dimensions - fail with clear error
                raise ValueError(
                    f"Cannot infer window size and channel count from input size {len(input_data)}. "
                    f"Expected size to be divisible by 160 or 256. "
                    f"Got remainder: {len(input_data) % 160} (160), {len(input_data) % 256} (256)"
                )

            if channels == 0:
                raise ValueError(f"Invalid channel count: got {channels} from input size {len(input_data)}")

            # Reshape to [samples, channels]
            # Input is interleaved: [s0c0, s0c1, ... s0c63, s1c0...]
            # So we reshape to (-1, channels)
            input_reshaped = input_data.reshape(-1, channels)
            
            # Welch needs to be applied per channel.
            # Scipy welch can handle axis. axis=-1 is default (last axis).
            # If we pass (samples, channels), we want axis=0.
            
            psd_list = []
            for c in range(channels):
                channel_data = input_reshaped[:, c]
                psd = compute(channel_data, config)
                psd_list.append(psd)
                
                # Stack results: [frequencies, channels] -> flatten
                # C implementation output order: interleaved [f0c0, f0c1...]
                # This matches the harness expectation.
                
            # Stack results: [frequencies, channels] -> flatten
            psd_matrix = np.array(psd_list).T # [frequencies, channels]
            output_data = psd_matrix.flatten().astype(np.float32)
            
            output_data.tofile(args.output)
                
        except Exception as e:
            print(f"Oracle error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Simple test mode
        # Generate synthetic signal: 10 Hz sine wave + noise
        fs = 160
        t = np.arange(1000) / fs
        x = np.sin(2 * np.pi * 10 * t) + 0.5 * np.random.randn(len(t))
        
        config = {'n_fft': 256, 'n_overlap': 128, 'window': 'hann'}
        psd = compute(x, config)
        
        print(f"Input length: {len(x)}")
        print(f"PSD length: {len(psd)}")
        print(f"First 5 values: {psd[:5]}")
