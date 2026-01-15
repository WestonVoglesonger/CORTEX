#!/usr/bin/env bash
#
# Linux Governor Validation Experiment
# =====================================
# Automates the full experiment: governor setup, benchmarking, frequency logging, analysis
#
# This experiment validates the DVFS/Idle Paradox discovered on macOS by using
# Linux's direct governor control. Expected results:
#   - powersave:   ~2x higher latency (matches macOS idle)
#   - performance: baseline latency (matches macOS medium-load)
#   - schedutil:   intermediate latency (Linux default)
#
# Usage:
#   sudo ./run-experiment.sh [OPTIONS]
#
# Options:
#   --skip-powersave     Skip the powersave governor run
#   --skip-performance   Skip the performance governor run
#   --skip-schedutil     Skip the schedutil governor run
#   --analysis-only      Only run analysis (skip benchmarks)
#   --dry-run            Print commands without executing
#
# Requirements:
#   - Root access (for governor manipulation)
#   - CORTEX built and ready (run `make all` first)
#   - Dataset available at primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32

set -euo pipefail

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$EXPERIMENT_DIR/../.." && pwd)"

# Configuration
POLICIES="/sys/devices/system/cpu/cpufreq/policy*"
FREQ_LOG_INTERVAL=1  # seconds between frequency readings
CONFIG_FILE="$EXPERIMENT_DIR/cortex-config.yaml"

# Governors to test (in order)
declare -a GOVERNORS=("powersave" "performance" "schedutil")
declare -A RUN_NAMES=(
    ["powersave"]="run-001-powersave"
    ["performance"]="run-002-performance"
    ["schedutil"]="run-003-schedutil"
)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

# Global state
FREQ_LOG_PID=""
ORIGINAL_GOVERNOR=""
INHIBIT_PID=""
DRY_RUN=false
ANALYSIS_ONLY=false
SKIP_POWERSAVE=false
SKIP_PERFORMANCE=false
SKIP_SCHEDUTIL=false

# ============================================================================
# Helper Functions
# ============================================================================

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (for governor control)"
        echo "Usage: sudo $0"
        exit 1
    fi
}

# ============================================================================
# Sleep Inhibition (Platform-Specific)
# ============================================================================
# macOS: caffeinate (no auth required)
# Linux: systemd-inhibit (requires polkit auth - we prompt user first)

start_sleep_inhibition() {
    local system
    system=$(uname -s)

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would start sleep inhibition"
        return 0
    fi

    if [[ "$system" == "Darwin" ]]; then
        # macOS: caffeinate doesn't require authentication
        if command -v caffeinate &>/dev/null; then
            caffeinate -dims -w $$ &
            INHIBIT_PID=$!
            log_info "Sleep prevention active (caffeinate, PID: $INHIBIT_PID)"
        else
            log_warn "caffeinate not found - system may sleep during benchmarks"
        fi
    elif [[ "$system" == "Linux" ]]; then
        # Linux: Script runs as root, so systemd-inhibit works without polkit auth
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
                log_warn "Sleep inhibition failed - ensure system won't sleep during benchmarks"
                INHIBIT_PID=""
            fi
        else
            log_warn "systemd-inhibit not found - ensure system won't sleep during benchmarks"
        fi
    else
        log_warn "Unknown platform - no sleep prevention available"
    fi

    return 0
}

stop_sleep_inhibition() {
    if [[ -n "${INHIBIT_PID:-}" ]]; then
        log_info "Stopping sleep inhibition (PID: $INHIBIT_PID)"
        kill "$INHIBIT_PID" 2>/dev/null || true
        wait "$INHIBIT_PID" 2>/dev/null || true
        INHIBIT_PID=""
    fi
}

get_current_governor() {
    cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor
}

get_available_governors() {
    cat /sys/devices/system/cpu/cpufreq/policy0/scaling_available_governors
}

set_governor() {
    local governor="$1"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would set governor to: $governor"
        return 0
    fi

    log_info "Setting governor to: $governor"
    for policy in $POLICIES; do
        echo "$governor" > "$policy/scaling_governor"
    done

    # Verify
    local actual
    actual=$(get_current_governor)
    if [[ "$actual" != "$governor" ]]; then
        log_error "Failed to set governor. Expected: $governor, Got: $actual"
        exit 1
    fi
    log_info "Governor set successfully: $actual"
}

restore_governor() {
    if [[ -n "${ORIGINAL_GOVERNOR:-}" ]]; then
        log_info "Restoring original governor: $ORIGINAL_GOVERNOR"
        set_governor "$ORIGINAL_GOVERNOR"
    fi
}

start_frequency_logging() {
    local log_file="$1"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would start frequency logging to: $log_file"
        return 0
    fi

    log_info "Starting frequency logging to: $log_file"
    echo "timestamp_ns,policy0_freq_khz,policy4_freq_khz,governor" > "$log_file"

    (
        while true; do
            ts=$(date +%s%N)
            freq0=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq 2>/dev/null || echo "0")
            freq4=$(cat /sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq 2>/dev/null || echo "0")
            gov=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null || echo "unknown")
            echo "$ts,$freq0,$freq4,$gov" >> "$log_file"
            sleep "$FREQ_LOG_INTERVAL"
        done
    ) &
    FREQ_LOG_PID=$!
    log_info "Frequency logger started (PID: $FREQ_LOG_PID)"
}

stop_frequency_logging() {
    if [[ -n "${FREQ_LOG_PID:-}" ]]; then
        log_info "Stopping frequency logger (PID: $FREQ_LOG_PID)"
        kill "$FREQ_LOG_PID" 2>/dev/null || true
        wait "$FREQ_LOG_PID" 2>/dev/null || true
        FREQ_LOG_PID=""
    fi
}

cleanup() {
    log_info "Cleaning up..."
    stop_frequency_logging
    stop_sleep_inhibition
    restore_governor
}

should_skip_governor() {
    local governor="$1"
    case "$governor" in
        powersave)   [[ "$SKIP_POWERSAVE" == "true" ]] ;;
        performance) [[ "$SKIP_PERFORMANCE" == "true" ]] ;;
        schedutil)   [[ "$SKIP_SCHEDUTIL" == "true" ]] ;;
        *)           return 1 ;;
    esac
}

# ============================================================================
# Benchmark Functions
# ============================================================================

run_benchmark() {
    local governor="$1"
    local run_name="${RUN_NAMES[$governor]}"
    local run_dir="$EXPERIMENT_DIR/$run_name"

    log_step "=========================================="
    log_step "Running benchmark: $run_name"
    log_step "Governor: $governor"
    log_step "=========================================="

    # Create run directory
    mkdir -p "$run_dir/kernel-data"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would run benchmark for $governor"
        return 0
    fi

    # Set governor
    set_governor "$governor"

    # Wait for system to stabilize
    log_info "Waiting 5 seconds for governor to stabilize..."
    sleep 5

    # Start frequency logging
    start_frequency_logging "$run_dir/frequency-log.csv"

    # Run CORTEX benchmark
    log_info "Starting CORTEX benchmark..."
    cd "$PROJECT_ROOT"

    # Generate a unique run name for CORTEX
    local cortex_run_name="governor-$governor-$(date +%Y%m%d-%H%M%S)"

    # Run as the original user (not root) for proper permissions
    # Preserve PATH to find cortex in user's .local/bin
    local real_user="${SUDO_USER:-$USER}"
    local user_home="${SUDO_USER:+$(eval echo ~$SUDO_USER)}"
    user_home="${user_home:-$HOME}"
    local user_path="$user_home/.local/bin:/usr/local/bin:/usr/bin:/bin"

    # Run with config file - harness now creates per-plugin output directories
    if ! sudo -u "$real_user" env PATH="$user_path:$PATH" SUDO_USER="$real_user" \
        cortex run --config "$CONFIG_FILE" --run-name "$cortex_run_name"; then
        log_error "Benchmark failed for $run_name"
        stop_frequency_logging
        return 1
    fi

    # Stop frequency logging
    stop_frequency_logging

    # Copy results to experiment directory
    local cortex_results_dir="$PROJECT_ROOT/results/$cortex_run_name"
    if [[ -d "$cortex_results_dir" ]]; then
        log_info "Copying telemetry to experiment directory..."

        # Copy kernel-data
        if [[ -d "$cortex_results_dir/kernel-data" ]]; then
            cp -r "$cortex_results_dir/kernel-data/"* "$run_dir/kernel-data/" 2>/dev/null || true
        fi

        # Also copy any analysis files
        if [[ -d "$cortex_results_dir/analysis" ]]; then
            cp -r "$cortex_results_dir/analysis" "$run_dir/" 2>/dev/null || true
        fi

        # Record the original results path
        echo "$cortex_results_dir" > "$run_dir/cortex-results-path.txt"
    else
        log_warn "Results directory not found: $cortex_results_dir"
    fi

    log_info "Benchmark complete: $run_name"
    return 0
}

# ============================================================================
# Analysis Functions
# ============================================================================

run_per_run_analysis() {
    local run_name="$1"
    local run_dir="$EXPERIMENT_DIR/$run_name"

    if [[ ! -d "$run_dir/kernel-data" ]]; then
        log_warn "No kernel-data found for $run_name, skipping analysis"
        return 0
    fi

    log_info "Running per-run analysis for: $run_name"

    # Create analysis directory
    mkdir -p "$run_dir/analysis"

    # Generate summary using cortex analyze (if available)
    cd "$PROJECT_ROOT"
    local real_user="${SUDO_USER:-$USER}"

    # Check if cortex analyze supports --input flag, otherwise skip
    # For now, we'll rely on the cross-run analysis scripts
    log_info "Per-run analysis will be generated by cross-run scripts"
}

run_cross_run_analysis() {
    log_step "=========================================="
    log_step "Running cross-run analysis"
    log_step "=========================================="

    cd "$SCRIPT_DIR"

    # Run analysis as original user to access their Python environment
    local real_user="${SUDO_USER:-$USER}"
    local user_home="${SUDO_USER:+$(eval echo ~$SUDO_USER)}"
    user_home="${user_home:-$HOME}"
    local user_path="$user_home/.local/bin:/usr/local/bin:/usr/bin:/bin"

    # Statistical significance analysis
    log_info "Running statistical significance analysis..."
    if [[ -f "calculate_statistical_significance.py" ]]; then
        sudo -u "$real_user" env PATH="$user_path" python3 calculate_statistical_significance.py || log_warn "Statistical analysis failed"
    else
        log_warn "calculate_statistical_significance.py not found"
    fi

    # Governor comparison figure
    log_info "Generating governor comparison figure..."
    if [[ -f "generate_governor_comparison.py" ]]; then
        sudo -u "$real_user" env PATH="$user_path" python3 generate_governor_comparison.py || log_warn "Governor comparison failed"
    else
        log_warn "generate_governor_comparison.py not found"
    fi

    # macOS comparison
    log_info "Generating macOS comparison..."
    if [[ -f "compare_to_macos.py" ]]; then
        sudo -u "$real_user" env PATH="$user_path" python3 compare_to_macos.py || log_warn "macOS comparison failed"
    else
        log_warn "compare_to_macos.py not found"
    fi
}

# ============================================================================
# Main
# ============================================================================

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-powersave)   SKIP_POWERSAVE=true ;;
            --skip-performance) SKIP_PERFORMANCE=true ;;
            --skip-schedutil)   SKIP_SCHEDUTIL=true ;;
            --analysis-only)    ANALYSIS_ONLY=true ;;
            --dry-run)          DRY_RUN=true ;;
            --help|-h)
                echo "Usage: sudo $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --skip-powersave     Skip the powersave governor run"
                echo "  --skip-performance   Skip the performance governor run"
                echo "  --skip-schedutil     Skip the schedutil governor run"
                echo "  --analysis-only      Only run analysis (skip benchmarks)"
                echo "  --dry-run            Print commands without executing"
                echo "  --help, -h           Show this help message"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
        shift
    done
}

main() {
    parse_args "$@"

    # Check root unless dry-run or analysis-only
    if [[ "$DRY_RUN" != "true" && "$ANALYSIS_ONLY" != "true" ]]; then
        check_root
    fi

    # Print experiment overview
    echo ""
    log_step "============================================"
    log_step "Linux Governor Validation Experiment"
    log_step "============================================"
    log_info "Experiment directory: $EXPERIMENT_DIR"
    log_info "Project root: $PROJECT_ROOT"
    log_info "Config file: $CONFIG_FILE"
    echo ""

    # Check available governors
    log_info "Available governors: $(get_available_governors)"
    ORIGINAL_GOVERNOR=$(get_current_governor)
    log_info "Current governor: $ORIGINAL_GOVERNOR"
    echo ""

    # Set up cleanup trap
    trap cleanup EXIT

    if [[ "$ANALYSIS_ONLY" != "true" ]]; then
        # Verify config file exists
        if [[ ! -f "$CONFIG_FILE" ]]; then
            log_error "Config file not found: $CONFIG_FILE"
            exit 1
        fi

        # Start sleep inhibition BEFORE benchmarks
        # This prompts for authentication early so we don't fail mid-experiment
        log_step "Setting up sleep prevention..."
        if ! start_sleep_inhibition; then
            log_error "Failed to set up sleep prevention"
            log_info "Options:"
            log_info "  1. Try again and enter password when prompted"
            log_info "  2. Manually disable sleep: systemctl mask sleep.target suspend.target"
            log_info "  3. Run with --analysis-only to skip benchmarks"
            exit 1
        fi
        echo ""

        # Run benchmarks for each governor
        for governor in "${GOVERNORS[@]}"; do
            if should_skip_governor "$governor"; then
                log_info "Skipping $governor (--skip-$governor flag set)"
                continue
            fi

            if ! run_benchmark "$governor"; then
                log_error "Benchmark failed for $governor, continuing with next..."
            fi

            # Brief pause between runs
            if [[ "$DRY_RUN" != "true" ]]; then
                log_info "Pausing 10 seconds before next run..."
                sleep 10
            fi
        done
    else
        log_info "Analysis-only mode: skipping benchmarks"
    fi

    # Run analysis
    run_cross_run_analysis

    echo ""
    log_step "============================================"
    log_step "Experiment complete!"
    log_step "============================================"
    log_info "Results directory: $EXPERIMENT_DIR"
    log_info ""
    log_info "Run directories:"
    for governor in "${GOVERNORS[@]}"; do
        local run_name="${RUN_NAMES[$governor]}"
        if [[ -d "$EXPERIMENT_DIR/$run_name" ]]; then
            log_info "  - $run_name/"
        fi
    done
    log_info ""
    log_info "Figures: $EXPERIMENT_DIR/figures/"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Review results in technical-report/COMPREHENSIVE_VALIDATION_REPORT.md"
    log_info "  2. Compare figures/macos_linux_comparison.png with macOS results"
    log_info "  3. Update documentation with findings"
}

main "$@"
