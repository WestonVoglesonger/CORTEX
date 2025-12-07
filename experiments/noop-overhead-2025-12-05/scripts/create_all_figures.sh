#!/usr/bin/env bash
#
# Generate All Figures for noop-overhead Experiment
# ==================================================
# Wrapper script to generate all publication-quality figures.
#
# Usage:
#   ./scripts/create_all_figures.sh
#
# Requirements:
#   - Python 3.8+
#   - matplotlib, numpy, pandas, scipy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPERIMENT_DIR="$(dirname "$SCRIPT_DIR")"
FIGURES_DIR="$EXPERIMENT_DIR/figures"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Create figures directory
mkdir -p "$FIGURES_DIR"

echo "═══════════════════════════════════════════════════════════════"
echo "  Generating Figures for noop-overhead Experiment"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Generate idle vs medium comparison
log_step "Generating idle vs medium comparison figure..."
python3 "$SCRIPT_DIR/generate_noop_comparison.py"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Figure Generation Complete"
echo "═══════════════════════════════════════════════════════════════"
echo ""
log_info "Figures saved to: $FIGURES_DIR/"
ls -lh "$FIGURES_DIR"

echo ""
log_info "To view statistical analysis, run:"
echo "  python3 scripts/calculate_overhead_stats.py"
