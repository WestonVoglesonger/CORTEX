/*
 * Common Average Reference (CAR) Plugin--subtracts the mean across channels at each time sample (excluding Nans)
 * outputs zero for a time t if all channels at that time are NaN
 * integrated with oracle.py (float32 I/O, double accumulation for mean)
 */

#include "cortex_plugin.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#undef CORTEX_ABI_VERSION
#define CORTEX_ABI_VERSION 2u

typedef struct {
    uint32_t channels;           /* C */
    uint32_t window_length;      /* W */
    uint32_t hop_samples;        /* not used by CAR, kept for symmetry/logging */
} car_state_t;

//Init:
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) return result;

    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;

    /* dtype: CAR@f32 only */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) return result;

        car_state_t *st = (car_state_t *)calloc(1, sizeof(car_state_t));
    if (!st) return result;

    st->channels      = config->channels;              /* e.g., 64 */
    st->window_length = config->window_length_samples; /* e.g., 160 */
    st->hop_samples   = config->hop_samples;           /* e.g., 80  */

    /* Output shape = input shape for CAR */
    result.handle = st;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels              = config->channels;

    return result;
}

//Process:
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    const car_state_t *st = (const car_state_t *)handle;
    const uint32_t W = st->window_length;
    const uint32_t C = st->channels;

    const float *in  = (const float *)input;
    float       *out = (float *)output;

    /* layout: time-major, interleaved channels: x[t*C + c] */
    for (uint32_t t = 0; t < W; ++t) {
        const float *row_in = in  + (size_t)t * C;
        float       *row_out= out + (size_t)t * C;

        /* 1) mean across channels at time t, excluding NaNs */
        double sum = 0.0;
        int count = 0;

        /* use (v==v) instead of isnan(v) to avoid extra headers; NaN != NaN */
        for (uint32_t c = 0; c < C; ++c) {
            float v = row_in[c];
            if (v == v) { sum += (double)v; ++count; }
        }

        if (count == 0) {
            /* all NaN → zeros for this time sample */
            memset(row_out, 0, (size_t)C * sizeof(float));
            continue;
        }

        float mean = (float)(sum / (double)count);

        /* 2) subtract mean; NaNs become 0 (policy from oracle) */
        /* in-place safe: we already computed mean before any writes */
        for (uint32_t c = 0; c < C; ++c) {
            float v = row_in[c];
            row_out[c] = (v == v) ? (v - mean) : 0.0f;
        }
    }
}

//teardown:
void cortex_teardown(void *handle) {
    if (!handle) return;
    car_state_t *st = (car_state_t *)handle;
    free(st);
}





