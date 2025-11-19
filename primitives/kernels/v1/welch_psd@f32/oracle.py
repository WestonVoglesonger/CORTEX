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
    fs = 1.0  # Normalized frequency
    
    # SciPy's welch function does exactly what we need
    # scaling='density' is the default, which is what we want for PSD
    # detrend=False matches standard DSP implementations unless specified
    
    # If input is too short, pad or handle gracefully
    if len(input_data) < n_fft:
        # For now, return zeros or handle as error. 
        # But to match C implementation which might process partial or zero pad,
        # let's just let scipy handle it or return zeros.
        return np.zeros(n_fft // 2 + 1, dtype=np.float32)

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
            
            # Reshape if multi-channel?
            # The harness passes a flattened buffer [W * C].
            # Infer channels from input size
            # The harness typically sends one window of data.
            # We assume the window length is 160 (default) or try to deduce it.
            # Since we don't get arguments, we'll assume the standard window size of 160 for now,
            # but calculate channels based on that.
            WINDOW_SIZE = 160
            
            if len(input_data) % WINDOW_SIZE != 0:
                # Fallback: if not multiple of 160, maybe it's a different window size?
                # Try 256?
                if len(input_data) % 256 == 0:
                    WINDOW_SIZE = 256
                else:
                    # Default to treating as 1 channel if all else fails, or assume 64 channels?
                    # Let's stick to the review suggestion: infer from input.
                    # If we can't infer, we might have to assume 64 as a fallback.
                    pass

            channels = len(input_data) // WINDOW_SIZE
            if channels == 0:
                channels = 1 # Should not happen if len > 0
                
            # Update config based on window size (match C kernel logic)
            if WINDOW_SIZE < 256:
                config['n_fft'] = WINDOW_SIZE
                config['n_overlap'] = WINDOW_SIZE // 2
                
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
                # C implementation output order: likely interleaved [f0c0, f0c1...]?
                # Let's check C code.
                # C code: out_data[i] = ctx->psd_sum[i] / ctx->segment_count;
                # Wait, the C code I wrote only outputs ONE channel's worth of data?
                # Or does it handle multiple channels?
                # "result.output_channels = config->channels;"
                # But the process loop:
                # "ctx->fft_in[i].r = in_data[cursor + i] * ctx->window[i];"
                # This reads contiguous floats. If input is interleaved, this is WRONG.
                # The C code assumes single channel or planar?
                # Harness says: "Buffers are tightly packed in row‑major order (channels × samples)."
                # Wait, cortex_plugin.h says: "(channels × samples)".
                # Usually this means [c0s0, c0s1... c1s0...] (Planar) OR [s0c0, s0c1...] (Interleaved).
                # "row-major order (channels x samples)" usually means shape is (channels, samples).
                # So data[0] is ch0_s0, data[1] is ch0_s1...
                # Let's verify cortex_plugin.h comment again.
                # "Buffers are tightly packed in row‑major order (channels × samples)."
                # If it means a 2D array A[channels][samples], then it is Planar.
                # If test_kernel_accuracy.c says:
                # "float *data; /* [samples × channels] interleaved */"
                # Line 48 of test_kernel_accuracy.c.
                # So the harness uses INTERLEAVED.
                
                # My C code treats input as a single contiguous block of floats.
                # If interleaved, `in_data[cursor + i]` reads across channels!
                # This is a BUG in my C code. It treats the whole buffer as one signal.
                
                # For now, let's fix the Python oracle to match what the C code *should* do,
                # and then I must fix the C code.
                
                # If C code is buggy, validation will fail anyway.
                # Let's assume we want to fix both.
                
                # Python Oracle:
                # Input is interleaved [samples, channels].
                # We want to compute PSD for each channel.
                # Output should be [frequencies, channels] interleaved?
                # "output_window_length_samples x output_channels".
                # If interleaved, it should be [f0c0, f0c1, ... f0c63, f1c0...]
                
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
