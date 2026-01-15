#!/usr/bin/env bash
#
# Quick Governor Switching Utility
# =================================
# Set CPU frequency governor across all policy groups.
#
# Usage:
#   sudo ./set-governor.sh <governor>
#   sudo ./set-governor.sh             # Show current and available governors
#
# Examples:
#   sudo ./set-governor.sh performance   # Lock to max frequency
#   sudo ./set-governor.sh powersave     # Minimize frequency
#   sudo ./set-governor.sh schedutil     # Linux default (dynamic)

set -euo pipefail

GOVERNOR="${1:-}"
POLICIES="/sys/devices/system/cpu/cpufreq/policy*"

show_status() {
    echo "Available governors:"
    cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors
    echo ""
    echo "Current governors:"
    for policy in $POLICIES; do
        local name
        name=$(basename "$policy")
        echo "  $name: $(cat "$policy/scaling_governor")"
    done
    echo ""
    echo "Current frequencies:"
    for policy in $POLICIES; do
        local name freq_khz freq_mhz
        name=$(basename "$policy")
        freq_khz=$(cat "$policy/scaling_cur_freq")
        freq_mhz=$((freq_khz / 1000))
        echo "  $name: ${freq_mhz} MHz"
    done
}

if [[ -z "$GOVERNOR" ]]; then
    echo "Usage: sudo $0 <governor>"
    echo ""
    show_status
    exit 0
fi

if [[ $EUID -ne 0 ]]; then
    echo "Error: Must run as root"
    exit 1
fi

# Validate governor is available
available=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors)
if [[ ! " $available " =~ " $GOVERNOR " ]]; then
    echo "Error: Governor '$GOVERNOR' not available"
    echo "Available: $available"
    exit 1
fi

# Set governor on all policies
for policy in $POLICIES; do
    echo "$GOVERNOR" > "$policy/scaling_governor"
done

echo "Governor set to: $GOVERNOR"
echo ""
show_status
