#!/usr/bin/env bash
#
# High-Channel Scalability Benchmark
#
# Tests synthetic dataset generation at 64, 256, 512, 1024, 2048 channels
# to validate memory safety and measure generation performance.
#
# Expected results:
# - Peak RAM <200MB regardless of channel count (chunked generation)
# - Generation time scales linearly with channel count
# - No OOM errors at 2048 channels
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
CONFIGS_DIR="$SCRIPT_DIR/configs"

# Channel counts to test
CHANNEL_COUNTS=(64 256 512 1024 2048)

# Test parameters (kept small for fast benchmarking)
DURATION_S=10.0
WARMUP=0
REPEATS=3
DEADLINE_MS=500000  # 500s (generous for benchmarking)

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "================================================================"
echo "  High-Channel Scalability Benchmark"
echo "================================================================"
echo ""
echo "Testing channel counts: ${CHANNEL_COUNTS[*]}"
echo "Duration: ${DURATION_S}s"
echo "Repeats: ${REPEATS}"
echo ""

# Create results directory
mkdir -p "$RESULTS_DIR"

# Function to create config for given channel count
create_config() {
    local channels=$1
    local config_path="$CONFIGS_DIR/scalability_${channels}ch.yaml"

    cat > "$config_path" <<EOF
# High-channel scalability test: ${channels} channels

dataset:
  path: "primitives/datasets/v1/synthetic"
  params:
    signal_type: "pink_noise"
    amplitude_uv_rms: 100.0
    duration_s: ${DURATION_S}
    seed: 42
  channels: ${channels}
  sample_rate_hz: 160
  format: "float32"

execution:
  window_samples: 160     # W = 160 samples (1.0s @ 160Hz)
  hop_samples: 80         # H = 80 samples (50% overlap)
  deadline_ms: ${DEADLINE_MS}
  warmup_iterations: ${WARMUP}
  total_iterations: ${REPEATS}

load_profile:
  type: "constant"
  cpu_percent: 0

kernels:
  - name: "noop"
    path: "primitives/kernels/v1/noop@f32"
EOF

    echo "$config_path"
}

# Function to extract generation time from cortex output
extract_generation_time() {
    local log_file=$1

    # Look for generation timing in log
    # Format: "[cortex] Generated file: /tmp/... (took X.XXs)"
    grep -E "Generated file:|File size:" "$log_file" || true
}

# Function to run benchmark for given channel count
run_benchmark() {
    local channels=$1
    local config_path=$2
    local result_file="$RESULTS_DIR/scalability_${channels}ch.log"

    echo -e "${YELLOW}=== Testing ${channels} channels ===${NC}"
    echo ""

    # Expected file size
    local samples=$(echo "$DURATION_S * 160" | bc)
    local expected_mb=$(echo "scale=2; $channels * $samples * 4 / 1048576" | bc)

    echo "  Expected dataset size: ${expected_mb} MB"
    echo "  Config: $config_path"
    echo ""

    # Run benchmark with timing
    local start_time=$(date +%s.%N)

    if CORTEX_NO_INHIBIT=1 cortex run --config "$config_path" > "$result_file" 2>&1; then
        local end_time=$(date +%s.%N)
        local total_time=$(echo "$end_time - $start_time" | bc)

        echo -e "  ${GREEN}✓ Success${NC}"
        echo "  Total time: ${total_time}s"
        echo ""

        # Extract generation details
        echo "  Generation details:"
        extract_generation_time "$result_file" | sed 's/^/    /'
        echo ""

        return 0
    else
        local end_time=$(date +%s.%N)
        local total_time=$(echo "$end_time - $start_time" | bc)

        echo -e "  ${RED}✗ Failed${NC}"
        echo "  Total time: ${total_time}s"
        echo ""
        echo "  Error log:"
        tail -20 "$result_file" | sed 's/^/    /'
        echo ""

        return 1
    fi
}

# Generate all configs
echo "=== Generating configs ==="
echo ""

mkdir -p "$CONFIGS_DIR"

for channels in "${CHANNEL_COUNTS[@]}"; do
    config_path=$(create_config "$channels")
    echo "  Created: $config_path"
done

echo ""
echo "=== Running benchmarks ==="
echo ""

# Run benchmarks
SUCCESS_COUNT=0
TOTAL_COUNT=${#CHANNEL_COUNTS[@]}

for channels in "${CHANNEL_COUNTS[@]}"; do
    config_path="$CONFIGS_DIR/scalability_${channels}ch.yaml"

    if run_benchmark "$channels" "$config_path"; then
        ((SUCCESS_COUNT++))
    fi
done

# Summary
echo "================================================================"
echo "  Benchmark Summary"
echo "================================================================"
echo ""
echo "Completed: ${SUCCESS_COUNT}/${TOTAL_COUNT} benchmarks"
echo ""

if [ "$SUCCESS_COUNT" -eq "$TOTAL_COUNT" ]; then
    echo -e "${GREEN}✓ All benchmarks passed${NC}"
    echo ""
    echo "Results saved to: $RESULTS_DIR"
    echo ""
    echo "Next steps:"
    echo "  1. Review logs in $RESULTS_DIR"
    echo "  2. Run analysis: python experiments/high-channel-scalability-2026-01-12/analyze_results.py"
    echo "  3. Generate plots: python experiments/high-channel-scalability-2026-01-12/plot_results.py"
    exit 0
else
    echo -e "${RED}✗ Some benchmarks failed${NC}"
    echo ""
    echo "Check logs in: $RESULTS_DIR"
    exit 1
fi
