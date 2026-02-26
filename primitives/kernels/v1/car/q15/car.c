/*
 * Common Average Reference (CAR) for Q15 data type.
 *
 * Subtracts the channel mean at each time sample using Q15 integer arithmetic.
 * Accumulates in int32_t (64 channels * Q15 max = 2,097,088 — fits int32_t).
 * Mean computed via integer division (truncation, no rounding).
 *
 * No NaN handling needed — Q15 has no NaN representation.
 *
 * ABI Version: 2
 * Data Type: Q15 (signed Q1.15 fixed-point, int16_t)
 */

#include "cortex_plugin.h"
#include "cortex_q15.h"
#include <stdlib.h>
#include <string.h>

#undef CORTEX_ABI_VERSION
#define CORTEX_ABI_VERSION 2u

typedef struct {
    uint32_t channels;
    uint32_t window_length;
} car_q15_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_Q15) return result;
    if (config->channels == 0) return result;

    car_q15_state_t *st = (car_q15_state_t *)calloc(1, sizeof(car_q15_state_t));
    if (!st) return result;

    st->channels = config->channels;
    st->window_length = config->window_length_samples;

    result.handle = st;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    const car_q15_state_t *st = (const car_q15_state_t *)handle;
    const uint32_t W = st->window_length;
    const uint32_t C = st->channels;

    const int16_t *in  = (const int16_t *)input;
    int16_t       *out = (int16_t *)output;

    /* Layout: time-major, interleaved channels: x[t*C + c] */
    for (uint32_t t = 0; t < W; ++t) {
        const int16_t *row_in  = in  + (size_t)t * C;
        int16_t       *row_out = out + (size_t)t * C;

        /* 1) Compute channel mean in int32_t accumulator */
        int32_t sum = 0;
        for (uint32_t c = 0; c < C; ++c) {
            sum += (int32_t)row_in[c];
        }
        int16_t mean = (int16_t)(sum / (int32_t)C);

        /* 2) Subtract mean with saturation */
        for (uint32_t c = 0; c < C; ++c) {
            row_out[c] = q15_sat_sub(row_in[c], mean);
        }
    }
}

void cortex_teardown(void *handle) {
    if (handle) {
        free(handle);
    }
}
