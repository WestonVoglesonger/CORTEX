#!/bin/bash
# Download EDF sessions from PhysioNet EEG Motor Movement/Imagery Dataset
# Usage: ./download_edf.sh [subject_id]
# Default subject: S001

set -e  # Exit on error

BASE_URL="https://physionet.org/files/eegmmidb/1.0.0"
SUBJECT="${1:-S001}"  # Default to S001, but parameterized for other subjects
OUTPUT_DIR="../datasets/eegmmidb/raw"

echo "Downloading EDF files for subject ${SUBJECT}..."
mkdir -p "$OUTPUT_DIR"

# Download selected sessions (motor tasks for clearer signals)
SESSIONS=("${SUBJECT}R03" "${SUBJECT}R07" "${SUBJECT}R11")

for session in "${SESSIONS[@]}"; do
    echo "Downloading ${session}.edf..."
    
    # Use -f flag to fail on HTTP errors, --show-error for cleaner output
    if curl -f --show-error -o "$OUTPUT_DIR/${session}.edf" \
            "${BASE_URL}/${SUBJECT}/${session}.edf"; then
        echo "  ✓ ${session}.edf downloaded successfully ($(du -h "$OUTPUT_DIR/${session}.edf" | cut -f1))"
    else
        echo "  ✗ Failed to download ${session}.edf"
        exit 1
    fi
    
    # Also download event file (optional, for future use)
    echo "Downloading ${session}.edf.event..."
    if curl -f --show-error -o "$OUTPUT_DIR/${session}.edf.event" \
            "${BASE_URL}/${SUBJECT}/${session}.edf.event"; then
        echo "  ✓ ${session}.edf.event downloaded successfully"
    else
        echo "  ✗ Failed to download ${session}.edf.event (non-fatal)"
    fi
done

echo ""
echo "Download complete! Files saved to $OUTPUT_DIR"
echo "Downloaded sessions:"
echo "  - ${SUBJECT}R03: Left/right fist motor task (first run)"
echo "  - ${SUBJECT}R07: Left/right fist motor task (repeat)"
echo "  - ${SUBJECT}R11: Both fists/both feet motor task (repeat)"
