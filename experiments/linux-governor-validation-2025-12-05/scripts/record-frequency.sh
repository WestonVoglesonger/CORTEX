#!/usr/bin/env bash
#
# CPU Frequency Recording Utility
# ================================
# Records CPU frequency readings over time for analysis.
#
# Usage:
#   ./record-frequency.sh <output-file> [duration-seconds]
#
# Examples:
#   ./record-frequency.sh freq.csv 120       # Record for 2 minutes
#   ./record-frequency.sh freq.csv           # Record until Ctrl+C
#
# Output format (CSV):
#   timestamp_ns,policy0_freq_khz,policy4_freq_khz,governor

set -euo pipefail

OUTPUT="${1:-frequency-log.csv}"
DURATION="${2:-}"
INTERVAL=1

# Detect available policies
declare -a POLICY_NAMES=()
declare -a POLICY_PATHS=()

for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    if [[ -d "$policy" ]]; then
        POLICY_NAMES+=("$(basename "$policy")_freq_khz")
        POLICY_PATHS+=("$policy/scaling_cur_freq")
    fi
done

# Generate header
header="timestamp_ns"
for name in "${POLICY_NAMES[@]}"; do
    header="$header,$name"
done
header="$header,governor"

echo "$header" > "$OUTPUT"
echo "Recording to: $OUTPUT"
echo "Interval: ${INTERVAL}s"
if [[ -n "$DURATION" ]]; then
    echo "Duration: ${DURATION}s"
else
    echo "Duration: until Ctrl+C"
fi
echo "Press Ctrl+C to stop..."
echo ""

# Recording loop
record_count=0
start_time=$(date +%s)

cleanup() {
    echo ""
    echo "Recording stopped. Total records: $record_count"
    echo "Output file: $OUTPUT"
}
trap cleanup EXIT

while true; do
    # Check duration limit
    if [[ -n "$DURATION" ]]; then
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))
        if [[ $elapsed -ge $DURATION ]]; then
            break
        fi
    fi

    # Read timestamp
    ts=$(date +%s%N)

    # Read frequencies
    freqs=""
    for path in "${POLICY_PATHS[@]}"; do
        freq=$(cat "$path" 2>/dev/null || echo "0")
        freqs="$freqs,$freq"
    done

    # Read governor
    gov=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)

    # Write record
    echo "${ts}${freqs},${gov}" >> "$OUTPUT"
    ((record_count++))

    # Progress indicator (every 10 records)
    if ((record_count % 10 == 0)); then
        echo -ne "\rRecords: $record_count"
    fi

    sleep $INTERVAL
done
