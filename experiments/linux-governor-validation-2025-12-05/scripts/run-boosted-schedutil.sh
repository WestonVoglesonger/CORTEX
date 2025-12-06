#!/usr/bin/env bash
#
# Run additional schedutil + stress-ng test
# This tests whether background CPU load can "boost" schedutil governor
# to perform like the macOS medium condition.
#
# Usage: sudo ./scripts/run-boosted-schedutil.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$EXPERIMENT_DIR/../.." && pwd)"

CONFIG_FILE="$EXPERIMENT_DIR/cortex-config-boosted.yaml"
RUN_NAME="run-004-schedutil-boosted"
RUN_DIR="$EXPERIMENT_DIR/$RUN_NAME"
FREQ_LOG_INTERVAL=1

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# Global state
INHIBIT_PID=""

cleanup() {
    log_info "Cleaning up..."
    # Stop frequency logger if running
    if [[ -n "${FREQ_PID:-}" ]]; then
        kill "$FREQ_PID" 2>/dev/null || true
        wait "$FREQ_PID" 2>/dev/null || true
    fi
    # Stop sleep inhibition
    if [[ -n "${INHIBIT_PID:-}" ]]; then
        log_info "Stopping sleep inhibition (PID: $INHIBIT_PID)"
        kill "$INHIBIT_PID" 2>/dev/null || true
        wait "$INHIBIT_PID" 2>/dev/null || true
    fi
    # Restore governor
    if [[ -n "${ORIGINAL_GOVERNOR:-}" ]]; then
        log_info "Restoring original governor: $ORIGINAL_GOVERNOR"
        for policy in /sys/devices/system/cpu/cpufreq/policy*; do
            echo "$ORIGINAL_GOVERNOR" > "$policy/scaling_governor"
        done
    fi
}

# Check root
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root"
    echo "Usage: sudo $0"
    exit 1
fi

# Check config exists
if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "Config file not found: $CONFIG_FILE"
    exit 1
fi

# Set up cleanup trap
trap cleanup EXIT

# Start sleep inhibition (as root, no polkit needed)
log_info "Setting up sleep prevention..."
if command -v systemd-inhibit &>/dev/null; then
    systemd-inhibit --what=sleep:idle:handle-lid-switch \
        --who="CORTEX Benchmark" \
        --why="Running performance benchmarks" \
        sleep infinity &
    INHIBIT_PID=$!
    sleep 1
    if kill -0 "$INHIBIT_PID" 2>/dev/null; then
        log_info "Sleep prevention active (systemd-inhibit, PID: $INHIBIT_PID)"
    else
        log_info "Warning: Sleep inhibition failed"
        INHIBIT_PID=""
    fi
else
    log_info "Warning: systemd-inhibit not found"
fi

log_step "============================================"
log_step "Additional Run: schedutil + stress-ng boost"
log_step "============================================"
log_info "This tests if background load helps dynamic scaling"
log_info ""

# Save original governor
ORIGINAL_GOVERNOR=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)
log_info "Original governor: $ORIGINAL_GOVERNOR"

# Set schedutil
log_info "Setting governor to: schedutil"
for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    echo "schedutil" > "$policy/scaling_governor"
done
log_info "Governor set: $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)"

# Wait for stabilization
log_info "Waiting 5 seconds for governor to stabilize..."
sleep 5

# Create run directory
mkdir -p "$RUN_DIR/kernel-data"

# Start frequency logging
log_info "Starting frequency logging..."
FREQ_LOG="$RUN_DIR/frequency-log.csv"
echo "timestamp_ns,policy0_freq_khz,policy4_freq_khz,governor" > "$FREQ_LOG"
(
    while true; do
        ts=$(date +%s%N)
        freq0=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq 2>/dev/null || echo "0")
        freq4=$(cat /sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq 2>/dev/null || echo "0")
        gov=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null || echo "unknown")
        echo "$ts,$freq0,$freq4,$gov" >> "$FREQ_LOG"
        sleep "$FREQ_LOG_INTERVAL"
    done
) &
FREQ_PID=$!
log_info "Frequency logger started (PID: $FREQ_PID)"

# Run benchmark
log_info "Starting CORTEX benchmark with stress-ng boost..."
cd "$PROJECT_ROOT"

REAL_USER="${SUDO_USER:-$USER}"
USER_HOME="${SUDO_USER:+$(eval echo ~$SUDO_USER)}"
USER_HOME="${USER_HOME:-$HOME}"
USER_PATH="$USER_HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

CORTEX_RUN_NAME="governor-schedutil-boosted-$(date +%Y%m%d-%H%M%S)"

if ! sudo -u "$REAL_USER" env PATH="$USER_PATH:$PATH" SUDO_USER="$REAL_USER" \
    cortex run --config "$CONFIG_FILE" --run-name "$CORTEX_RUN_NAME"; then
    echo "Benchmark failed!"
    kill "$FREQ_PID" 2>/dev/null || true
    exit 1
fi

# Copy results (cleanup trap will stop freq logger and restore governor)
CORTEX_RESULTS="$PROJECT_ROOT/results/$CORTEX_RUN_NAME"
if [[ -d "$CORTEX_RESULTS/kernel-data" ]]; then
    log_info "Copying telemetry to experiment directory..."
    cp -r "$CORTEX_RESULTS/kernel-data/"* "$RUN_DIR/kernel-data/" 2>/dev/null || true
    echo "$CORTEX_RESULTS" > "$RUN_DIR/cortex-results-path.txt"
fi

log_step "============================================"
log_step "Run complete: $RUN_NAME"
log_step "============================================"
log_info "Results: $RUN_DIR"
log_info ""
log_info "Quick comparison (run this after):"
log_info "  python3 scripts/calculate_statistical_significance.py"
