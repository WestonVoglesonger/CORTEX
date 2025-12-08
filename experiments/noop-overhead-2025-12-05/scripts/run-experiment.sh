#!/usr/bin/env bash
#
# No-Op Harness Overhead Measurement Experiment (macOS)
# ======================================================
# Automates the complete experiment: idle + medium profiles, data collection, analysis
#
# This experiment measures CORTEX harness dispatch overhead using an identity (no-op)
# kernel under two load profiles:
#   - Idle:   No background load (reveals DVFS penalty)
#   - Medium: 4 CPUs @ 50% via stress-ng (locks CPU frequency)
#
# Expected results:
#   - Both profiles show minimum ~1 µs (true harness overhead)
#   - Idle median ~3 µs (DVFS penalty)
#   - Medium median ~2 µs (CPU at high frequency)
#
# Usage:
#   ./scripts/run-experiment.sh
#
# Duration: ~21 minutes (10 min idle + 10 min medium + analysis)
#
# Requirements:
#   - CORTEX built and installed (pip install -e .)
#   - noop@f32 kernel built (cd primitives/kernels/v1/noop@f32 && make)
#   - stress-ng installed (brew install stress-ng)
#   - Dataset: primitives/datasets/v1/physionet-motor-imagery/converted/S001R03.float32

set -euo pipefail

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(cd "$EXPERIMENT_DIR/../.." && pwd)"

# Configurations
CONFIG_IDLE="$EXPERIMENT_DIR/config-idle.yaml"
CONFIG_MEDIUM="$EXPERIMENT_DIR/config-medium.yaml"

# Output directories
RUN_IDLE="$EXPERIMENT_DIR/run-001-idle"
RUN_MEDIUM="$EXPERIMENT_DIR/run-002-medium"
FIGURES_DIR="$EXPERIMENT_DIR/figures"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# Preflight Checks
# ============================================================================

check_dependencies() {
    log_step "Checking dependencies..."

    # Check cortex CLI
    if ! command -v cortex &>/dev/null; then
        log_error "cortex command not found. Install CORTEX first: pip install -e ."
        exit 1
    fi

    # Check stress-ng (for medium load)
    if ! command -v stress-ng &>/dev/null; then
        log_error "stress-ng not found. Install it: brew install stress-ng"
        exit 1
    fi

    # Check configs exist
    if [[ ! -f "$CONFIG_IDLE" ]]; then
        log_error "Config not found: $CONFIG_IDLE"
        exit 1
    fi
    if [[ ! -f "$CONFIG_MEDIUM" ]]; then
        log_error "Config not found: $CONFIG_MEDIUM"
        exit 1
    fi

    # Check noop kernel exists
    if [[ ! -f "$PROJECT_ROOT/primitives/kernels/v1/noop@f32/libnoop.dylib" ]]; then
        log_error "noop kernel not built. Build it: cd primitives/kernels/v1/noop@f32 && make"
        exit 1
    fi

    log_info "All dependencies satisfied"
}

# ============================================================================
# Data Management
# ============================================================================

backup_old_data() {
    log_step "Backing up old data..."

    # Backup old idle data if exists
    if [[ -d "$EXPERIMENT_DIR/noop-idle" ]]; then
        local backup="$EXPERIMENT_DIR/noop-idle.old.$(date +%Y%m%d-%H%M%S)"
        mv "$EXPERIMENT_DIR/noop-idle" "$backup"
        log_info "Backed up noop-idle/ → $(basename $backup)/"
    fi

    # Backup old medium data if exists
    if [[ -d "$EXPERIMENT_DIR/noop-medium" ]]; then
        local backup="$EXPERIMENT_DIR/noop-medium.old.$(date +%Y%m%d-%H%M%S)"
        mv "$EXPERIMENT_DIR/noop-medium" "$backup"
        log_info "Backed up noop-medium/ → $(basename $backup)/"
    fi

    # Clean existing run directories
    if [[ -d "$RUN_IDLE" ]]; then
        rm -rf "$RUN_IDLE"
        log_info "Cleaned run-001-idle/"
    fi
    if [[ -d "$RUN_MEDIUM" ]]; then
        rm -rf "$RUN_MEDIUM"
        log_info "Cleaned run-002-medium/"
    fi
}

find_latest_results() {
    # Find most recent results directory
    local latest=$(ls -td "$PROJECT_ROOT"/results/run-* 2>/dev/null | head -1)
    if [[ -z "$latest" ]]; then
        log_error "No results directory found in $PROJECT_ROOT/results/"
        exit 1
    fi
    echo "$latest"
}

copy_results() {
    local src="$1"
    local dest="$2"

    log_info "Copying results: $(basename $src) → $(basename $dest)/"

    # Create destination
    mkdir -p "$dest"

    # Copy entire results directory structure
    cp -r "$src"/* "$dest/"

    # Save path to original results
    echo "$src" > "$dest/cortex-results-path.txt"

    log_info "Results copied successfully"
}

# ============================================================================
# Experiment Execution
# ============================================================================

run_idle_profile() {
    log_step "Running IDLE profile..."
    log_info "Duration: ~600 seconds (10 minutes)"
    log_info "Load: None (reveals DVFS penalty)"

    cd "$PROJECT_ROOT"

    # Run cortex run
    log_info "Executing: cortex run --config $CONFIG_IDLE"
    cortex run --config "$CONFIG_IDLE"

    # Find and copy results
    local results=$(find_latest_results)
    copy_results "$results" "$RUN_IDLE"

    log_info "Idle profile complete"
}

run_medium_profile() {
    log_step "Running MEDIUM profile..."
    log_info "Duration: ~600 seconds (10 minutes)"
    log_info "Load: 4 CPUs @ 50% (stress-ng)"

    cd "$PROJECT_ROOT"

    # Run cortex run (config-medium.yaml already has load_profile: "medium")
    log_info "Executing: cortex run --config $CONFIG_MEDIUM"
    cortex run --config "$CONFIG_MEDIUM"

    # Find and copy results
    local results=$(find_latest_results)
    copy_results "$results" "$RUN_MEDIUM"

    log_info "Medium profile complete"
}

# ============================================================================
# Analysis
# ============================================================================

generate_figures() {
    log_step "Generating publication figures..."

    # Create figures directory
    mkdir -p "$FIGURES_DIR"

    # Run figure generation script
    cd "$EXPERIMENT_DIR"
    if [[ -f "$SCRIPT_DIR/create_all_figures.sh" ]]; then
        bash "$SCRIPT_DIR/create_all_figures.sh"
        log_info "Figures generated in figures/"
    else
        log_warn "create_all_figures.sh not found, skipping figure generation"
    fi
}

print_summary() {
    log_step "Experiment complete!"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  No-Op Harness Overhead Measurement - Results"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "Results directories:"
    echo "  - run-001-idle/    Idle profile data"
    echo "  - run-002-medium/  Medium load profile data"
    echo "  - figures/         Publication-quality plots"
    echo ""
    echo "Quick stats extraction:"
    echo "  cd $EXPERIMENT_DIR"
    echo "  python3 scripts/calculate_overhead_stats.py"
    echo ""
    echo "Next steps:"
    echo "  1. Review figures/ for visualizations"
    echo "  2. Check run-00X-*/analysis/SUMMARY.md for statistics"
    echo "  3. Update README.md with new data if needed"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    log_info "Starting noop-overhead experiment (macOS)"
    log_info "Experiment directory: $EXPERIMENT_DIR"
    echo ""

    # Preflight
    check_dependencies
    backup_old_data
    echo ""

    # Execute experiment
    run_idle_profile
    echo ""
    run_medium_profile
    echo ""

    # Analysis
    generate_figures
    echo ""

    # Summary
    print_summary
}

# Trap Ctrl+C to clean up
trap 'log_error "Interrupted by user"; exit 130' INT

# Execute
main "$@"
