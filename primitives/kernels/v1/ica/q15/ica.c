/*
 * ICA (Independent Component Analysis) Kernel — Q15 data type
 *
 * Applies pre-trained ICA unmixing matrix to Q15 input.
 * Process: y[t,out_c] = sum_c((x[t,c] - mean[c]) * W[out_c,c])
 *
 * Calibration state is in float32 (same as f32 variant).
 * Mean and unmixing matrix quantized to Q15 during cortex_init().
 *
 * Accumulation in int64_t:
 *   64 channels × max(Q15×Q15) = 64 × (32767²) ≈ 68.7 billion — requires int64_t.
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
    int16_t *mean_q15;     /* Channel means quantized to Q15 [C] */
    int16_t *W_unmix_q15;  /* Unmixing matrix quantized to Q15 [C×C], row-major */
} ica_q15_state_t;

/* Calibration: delegate to f32 variant */
cortex_calibration_result_t cortex_calibrate(
    const cortex_plugin_config_t *config,
    const void *training_data,
    uint32_t num_windows
) {
    (void)config;
    (void)training_data;
    (void)num_windows;
    fprintf(stderr, "[ica@q15] ERROR: Calibrate on the f32 variant, then load state here.\n");
    return (cortex_calibration_result_t){NULL, 0, 0};
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    if (!config) return (cortex_init_result_t){NULL, 0, 0, 0};

    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[ica@q15] ERROR: ABI mismatch (got %u, want %u)\n",
                config->abi_version, CORTEX_ABI_VERSION);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    if (config->dtype != CORTEX_DTYPE_Q15) {
        fprintf(stderr, "[ica@q15] ERROR: Expected Q15 dtype\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    if (!config->calibration_state) {
        fprintf(stderr, "[ica@q15] ERROR: Calibration state required\n");
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* Deserialize float32 calibration state (same format as f32 variant) */
    const uint8_t *bytes = (const uint8_t *)config->calibration_state;
    uint32_t C;
    memcpy(&C, bytes, sizeof(uint32_t));

    if (C != config->channels) {
        fprintf(stderr, "[ica@q15] ERROR: Channel mismatch (state=%u, config=%u)\n",
                C, config->channels);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    ica_q15_state_t *state = calloc(1, sizeof(ica_q15_state_t));
    if (!state) return (cortex_init_result_t){NULL, 0, 0, 0};

    state->W = config->window_length_samples;
    state->C = C;

    /* Allocate Q15 arrays */
    state->mean_q15 = malloc(C * sizeof(int16_t));
    state->W_unmix_q15 = malloc(C * C * sizeof(int16_t));
    if (!state->mean_q15 || !state->W_unmix_q15) {
        free(state->mean_q15);
        free(state->W_unmix_q15);
        free(state);
        return (cortex_init_result_t){NULL, 0, 0, 0};
    }

    /* Read float32 mean and unmixing matrix, convert to Q15 */
    const float *f32_mean = (const float *)(bytes + sizeof(uint32_t));
    const float *f32_W = (const float *)(bytes + sizeof(uint32_t) + C * sizeof(float));

    for (uint32_t i = 0; i < C; i++) {
        state->mean_q15[i] = float_to_q15(f32_mean[i]);
    }
    for (uint32_t i = 0; i < C * C; i++) {
        state->W_unmix_q15[i] = float_to_q15(f32_W[i]);
    }

    fprintf(stderr, "[ica@q15] Loaded: C=%u (mean + unmixing matrix quantized to Q15)\n", C);

    return (cortex_init_result_t){
        .handle = state,
        .output_window_length_samples = state->W,
        .output_channels = C,
        .capabilities = CORTEX_CAP_OFFLINE_CALIB
    };
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    ica_q15_state_t *state = (ica_q15_state_t *)handle;
    const int16_t *x = (const int16_t *)input;
    int16_t *y = (int16_t *)output;

    const uint32_t W = state->W;
    const uint32_t C = state->C;

    /* y[t,out_c] = sum_c((x[t,c] - mean[c]) * W[out_c,c]) */
    for (uint32_t t = 0; t < W; t++) {
        for (uint32_t out_c = 0; out_c < C; out_c++) {
            int64_t acc = 0;
            for (uint32_t in_c = 0; in_c < C; in_c++) {
                /* Subtract mean with saturation */
                int16_t centered = q15_sat_sub(x[t * C + in_c], state->mean_q15[in_c]);
                /* Q15 × Q15 → Q30, accumulate in int64 */
                acc += (int64_t)centered * (int64_t)state->W_unmix_q15[out_c * C + in_c];
            }
            /* Round-to-nearest: add 0.5 in Q30, shift >>15 to get Q15 */
            acc += (1 << 14);
            int32_t result = (int32_t)(acc >> 15);

            /* Saturate to Q15 */
            if (result > 32767) result = 32767;
            else if (result < -32768) result = -32768;

            y[t * C + out_c] = (int16_t)result;
        }
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    ica_q15_state_t *state = (ica_q15_state_t *)handle;
    free(state->mean_q15);
    free(state->W_unmix_q15);
    free(state);
}
