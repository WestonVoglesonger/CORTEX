#!/usr/bin/env python3
"""
Convert PhysioNet EEG EDF files to float32 binary format for CORTEX.

EDF+ files contain 65 signals: 64 EEG channels + 1 annotation channel.
We extract only the first 64 EEG channels, explicitly excluding the annotation.

Usage:
    python3 convert_edf_to_float32.py S001R03 S001R07 S001R11
    python3 convert_edf_to_float32.py --all  # Convert all in raw/
"""

import pyedflib
import numpy as np
import json
import os
import sys
from pathlib import Path

def extract_channel_info(edf_path):
    """Extract channel labels and sample rate from EDF header."""
    f = pyedflib.EdfReader(edf_path)
    
    # Verify file has expected structure
    n_signals = f.signals_in_file
    if n_signals < 64:
        f.close()
        raise ValueError(f"Expected at least 64 EEG channels, got {n_signals}")
    
    # Get first 64 channels (EEG only, excluding annotation at signal 64)
    channel_labels = f.getSignalLabels()[:64]
    sample_rate = f.getSampleFrequency(0)
    
    f.close()
    return channel_labels, sample_rate, n_signals

def convert_edf_to_float32(edf_path, output_path):
    """
    Convert EDF file to interleaved float32 binary.
    
    Format: [sample0_ch0, sample0_ch1, ..., sample0_ch63, sample1_ch0, ...]
    
    Important: EDF+ has 65 signals (64 EEG + 1 annotation). We read only
    the first 64 channels, explicitly excluding the annotation channel.
    """
    print(f"Converting {edf_path}...")
    
    # Open EDF file
    f = pyedflib.EdfReader(edf_path)
    
    # Verify signal count
    n_signals_in_file = f.signals_in_file
    if n_signals_in_file != 65:
        print(f"  Warning: Expected 65 signals (64 EEG + 1 annotation), got {n_signals_in_file}")
    
    # Read metadata - explicitly only first 64 channels (EEG)
    n_channels = 64  # Fixed: always read exactly 64 EEG channels
    
    # Verify sample counts are consistent across all EEG channels
    n_samples_per_channel = f.getNSamples()[:n_channels]
    if not all(n == n_samples_per_channel[0] for n in n_samples_per_channel):
        print(f"  Warning: Channels have different sample counts: {set(n_samples_per_channel)}")
        n_samples = min(n_samples_per_channel)  # Use minimum to avoid array mismatch
        print(f"  Using minimum sample count: {n_samples}")
    else:
        n_samples = n_samples_per_channel[0]
    
    sample_rate = f.getSampleFrequency(0)
    
    # Read all EEG channels (0-63)
    # Note: pyedflib.readSignal() automatically converts from digital units (int16)
    # to physical units (µV) using scaling factors from the EDF header
    data = np.zeros((n_channels, n_samples), dtype=np.float32)
    for i in range(n_channels):
        data[i, :] = f.readSignal(i)  # Returns physical units (µV)
    
    # Save channel labels before closing file
    channel_labels = f.getSignalLabels()[:64]
    
    f.close()
    
    # Transpose to interleaved format: [samples, channels]
    data_interleaved = data.T  # Shape: (n_samples, n_channels)
    
    # Write as float32 binary
    data_interleaved.astype(np.float32).tofile(output_path)
    
    # Generate metadata
    metadata = {
        "source": os.path.basename(edf_path),
        "sample_rate_hz": int(sample_rate),
        "channels": n_channels,
        "samples_per_channel": int(n_samples),
        "duration_seconds": float(n_samples / sample_rate),
        "dtype": "float32",
        "format": "interleaved [samples, channels]",
        "units": "microvolts (µV)",
        "notes": "Converted from EDF+ (64 EEG channels, annotation channel excluded)"
    }
    
    metadata_path = output_path.replace('.float32', '_metadata.json')
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"  -> {output_path} ({n_samples} samples, {n_channels} channels, {metadata['duration_seconds']:.1f}s)")
    print(f"  -> {metadata_path}")
    
    return metadata, channel_labels

def main():
    # Paths (relative to datasets/tools/ where script is run)
    raw_dir = Path("../eegmmidb/raw")
    output_dir = Path("../eegmmidb/converted")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get sessions to convert
    if len(sys.argv) < 2:
        print("Usage: python3 convert_edf_to_float32.py S001R03 S001R07 S001R11")
        print("       python3 convert_edf_to_float32.py --all")
        sys.exit(1)
    
    if sys.argv[1] == "--all":
        sessions = [f.stem for f in raw_dir.glob("*.edf")]
    else:
        sessions = sys.argv[1:]
    
    if not sessions:
        print("Error: No sessions specified or found")
        sys.exit(1)
    
    # Convert each session and track channel labels
    all_metadata = []
    all_channel_labels = []
    
    for session in sessions:
        edf_path = raw_dir / f"{session}.edf"
        output_path = output_dir / f"{session}.float32"
        
        if not edf_path.exists():
            print(f"Warning: {edf_path} not found, skipping...")
            continue
        
        try:
            metadata, channel_labels = convert_edf_to_float32(str(edf_path), str(output_path))
            all_metadata.append(metadata)
            all_channel_labels.append((session, channel_labels))
        except Exception as e:
            print(f"Error converting {session}: {e}")
            continue
    
    if not all_channel_labels:
        print("Error: No files were successfully converted")
        sys.exit(1)
    
    # Verify all files have consistent channel order
    first_session, first_labels = all_channel_labels[0]
    for session, labels in all_channel_labels[1:]:
        if labels != first_labels:
            print(f"Warning: {session} has different channel order than {first_session}!")
    
    # Extract channel order from first file (should be same for all)
    channel_labels, sample_rate, n_signals = extract_channel_info(str(raw_dir / f"{all_channel_labels[0][0]}.edf"))
    
    channel_order = {
        "source": "PhysioNet EEG Motor Movement/Imagery Dataset",
        "dataset_url": "https://physionet.org/content/eegmmidb/1.0.0/",
        "format": "EDF signal order 0-63 (annotation channel excluded)",
        "sample_rate_hz": int(sample_rate),
        "total_signals_in_edf": n_signals,
        "eeg_channels": 64,
        "channels": channel_labels,
        "notes": "Channel order is identical across all sessions in dataset. Signal 64 (annotation) is excluded."
    }
    
    channel_order_path = output_dir.parent / "channel_order.json"
    with open(channel_order_path, 'w') as f:
        json.dump(channel_order, f, indent=2)
    
    print(f"\nChannel order saved to {channel_order_path}")
    print(f"Conversion complete! Converted {len(all_metadata)} files.")
    print(f"Output directory: {output_dir}")

if __name__ == "__main__":
    main()
