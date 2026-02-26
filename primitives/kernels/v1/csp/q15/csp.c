/*
 * CSP (Common Spatial Pattern) Kernel — Q15 data type
 *
 * Spatial filtering for motor imagery classification using Q15 input/output.
 * Reuses float32 calibration state (same .cortex_state files).
 * Filters converted to Q15 during cortex_init().
 *
 * Process: y[t,k] = sum_c(x[t,c] * W[k,c]) for each timestep t and component k.
 * Accumulation in int64_t to prevent overflow:
 *   64 channels × max(Q15*Q15) = 64 × (32767²) = 64 × 1,073,676,289 ≈ 68.7 billion
 *   — exceeds int32_t range, requires int64_t.
 *
 * ABI Version: 3 (trainable, offline calibration)
 * Data Type: Q15 (signed Q1.15 fixed-point, int16_t)
 */

#include "cortex_plugin.h"
#include "cortex_q15.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CORTEX_ABI_VERSION 3u

typedef struct {
    uint32_t W, C;
    uint32_t n_components;
    int16_t *W_filters_q15;  /* CSP spatial filters quantized to Q15 [n_components × C], column-major */
} csp_q15_state_t;

/* ============================================================================
 * Calibration: Delegate to f32 implementation.
 * CSP@q15 shares the same calibration as CSP@f32 — calibration always
 * happens in float32 (offline training). The .cortex_state file format
 * is identical. Q15 conversion happens at init time, not calibration time.
 * ============================================================================ */

cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *training_data,
    uint32_t num_windows
) {
    (void)config;
    (void)training_data;
    (void)num_windows;
    fprintf(stderr, "[csp@q15] ERROR: Calibrate on the f32 variant, then load state here.\n");
    return (cortex_calibration_result_t){NULL, 0, 0};
}

/* ============================================================================
 * Init: Load float32 calibration state, quantize filters to Q15
 * ============================================================================ */

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (!config) return (cortex_init_result_t){NULL, 0, 0, 0};

    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[csp@q15] ERROR: ABI mismatch (got %u, want %u)\n",
                config->abi_version, CORTEX_ABI_VERSION);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    if (config->dtype != CORTEX_DTYPE_Q15) {
        fprintf(stderr, "[csp@q15] ERROR: Expected Q15 dtype\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    if (!config->calibration_state) {
        fprintf(stderr, "[csp@q15] ERROR: Calibration state required\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    csp_q15_state_t *state = malloc(sizeof(csp_q15_state_t));
    if (!state) return (cortex_init_result_t){NULL, 0, 0, 0};

    /* Deserialize float32 calibration state (same format as f32 variant) */
    const uint8_t *bytes = (const uint8_t *)config->calibration_state;
    uint32_t C, n_components;
    memcpy(&C, bytes, 4); bytes += 4;
    memcpy(&n_components, bytes, 4); bytes += 4;

    if (C != config->channels) {
        fprintf(stderr, "[csp@q15] ERROR: Channel mismatch (state=%u, config=%u)\n",
                C, config->channels);
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    state->W = config->window_length_samples;
    state->C = C;
    state->n_components = n_components;

    /* Allocate Q15 filter array */
    state->W_filters_q15 = malloc(C * n_components * sizeof(int16_t));
    if (!state->W_filters_q15) {
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* Convert float32 filters to Q15 */
    const float *f32_filters = (const float *)bytes;
    for (uint32_t i = 0; i < C * n_components; i++) {
        state->W_filters_q15[i] = cortex_float_to_q15(f32_filters[i]);
    }

    fprintf(stderr, "[csp@q15] Loaded: C=%u, n_components=%u (filters quantized to Q15)\n",
            C, n_components);

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = state->W,
        .output_channels = n_components,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
}

/* ============================================================================
 * Process: Apply Q15 spatial filters. y = x @ W (all Q15 arithmetic).
 * ============================================================================ */

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    csp_q15_state_t *state = (csp_q15_state_t *)handle;
    const int16_t *x = (const int16_t *)input;
    int16_t *y = (int16_t *)output;

    const uint32_t W = state->W;
    const uint32_t C = state->C;
    const uint32_t K = state->n_components;

    /* y[t,k] = sum_c(x[t,c] * W_filters[k + c * K]) for column-major W */
    for (uint32_t t = 0; t < W; t++) {
        for (uint32_t k = 0; k < K; k++) {
            int64_t acc = 0;
            for (uint32_t c = 0; c < C; c++) {
                /* Column-major: filter element (k, c) at index k + c * K */
                acc += (int64_t)x[t * C + c] * (int64_t)state->W_filters_q15[k + c * K];
            }
            /* Round-to-nearest: add 0.5 in Q30, shift >>15 to get Q15 */
            acc += (1 << 14);
            int32_t result = (int32_t)(acc >> 15);

            /* Saturate to Q15 */
            if (result > 32767) result = 32767;
            else if (result < -32768) result = -32768;

            y[t * K + k] = (int16_t)result;
        }
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    csp_q15_state_t *state = (csp_q15_state_t *)handle;
    free(state->W_filters_q15);
    free(state);
}
