/*
 * Goertzel Bandpower Plugin — Q15 data type
 *
 * Computes alpha (8-13 Hz) and beta (13-30 Hz) bandpower using the
 * Goertzel algorithm with mixed-precision arithmetic.
 *
 * Mixed-precision design:
 *   - Input/output: Q15 (int16_t)
 *   - Goertzel coefficient: Q14 (range [-2, +2)), because 2*cos(omega) can reach 2.0
 *   - Recurrence state: Q15 in int32_t (prevents overflow during accumulation)
 *   - Power computation: int64_t (products of Q15 state values)
 *
 * Output: 2 bands × C channels, power values scaled and saturated to Q15.
 *
 * ABI Version: 2
 * Data Type: Q15 (signed Q1.15 fixed-point, int16_t)
 */

#include "cortex_plugin.h"
#include "cortex_q15.h"
#include "cortex_params.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>

#undef CORTEX_ABI_VERSION
#define CORTEX_ABI_VERSION 2u

#define DEFAULT_ALPHA_LOW_HZ 8.0
#define DEFAULT_ALPHA_HIGH_HZ 13.0
#define DEFAULT_BETA_LOW_HZ 13.0
#define DEFAULT_BETA_HIGH_HZ 30.0
#define NUM_BANDS 2

typedef struct {
    uint32_t channels;
    uint32_t window_length;
    uint32_t sample_rate_hz;
    uint32_t alpha_start_bin;
    uint32_t alpha_end_bin;
    uint32_t beta_start_bin;
    uint32_t beta_end_bin;
    uint32_t total_bins;
    int16_t *coeffs_q14;  /* Pre-computed 2*cos(2*pi*k/N) in Q14 format */
} goertzel_q15_state_t;

/* Q14 helpers — coefficient range [-2, +2) */
static inline int16_t double_to_q14(double x) {
    double scaled = x * 16384.0;
    int32_t rounded = (int32_t)round(scaled);
    if (rounded > 16383) rounded = 16383;
    else if (rounded < -16384) rounded = -16384;
    return (int16_t)rounded;
}

/* Q14 coefficient × Q15 state → Q29, then >>14 → Q15 (with rounding) */
static inline int32_t q14_mul_q15(int16_t coeff_q14, int32_t state_q15) {
    int64_t product = (int64_t)coeff_q14 * (int64_t)state_q15;
    /* Round-to-nearest: add 0.5 in Q29, shift >>14 to get Q15 */
    return (int32_t)((product + (1 << 13)) >> 14);
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_Q15) return result;

    goertzel_q15_state_t *state = calloc(1, sizeof(goertzel_q15_state_t));
    if (!state) return result;

    state->channels = config->channels;
    state->window_length = config->window_length_samples;
    state->sample_rate_hz = config->sample_rate_hz;

    /* Parse frequency band parameters */
    const char *params_str = (const char *)config->kernel_params;
    double alpha_low = cortex_param_float(params_str, "alpha_low", DEFAULT_ALPHA_LOW_HZ);
    double alpha_high = cortex_param_float(params_str, "alpha_high", DEFAULT_ALPHA_HIGH_HZ);
    double beta_low = cortex_param_float(params_str, "beta_low", DEFAULT_BETA_LOW_HZ);
    double beta_high = cortex_param_float(params_str, "beta_high", DEFAULT_BETA_HIGH_HZ);

    /* Compute bin indices */
    state->alpha_start_bin = (uint32_t)round(alpha_low * (double)state->window_length / (double)state->sample_rate_hz);
    state->alpha_end_bin = (uint32_t)round(alpha_high * (double)state->window_length / (double)state->sample_rate_hz);
    state->beta_start_bin = (uint32_t)round(beta_low * (double)state->window_length / (double)state->sample_rate_hz);
    state->beta_end_bin = (uint32_t)round(beta_high * (double)state->window_length / (double)state->sample_rate_hz);

    /* Validate bin ranges */
    if (state->alpha_start_bin >= state->alpha_end_bin ||
        state->beta_start_bin >= state->beta_end_bin ||
        state->beta_end_bin > state->window_length / 2) {
        fprintf(stderr, "[goertzel@q15] Invalid bin ranges\n");
        free(state);
        return result;
    }

    state->total_bins = state->beta_end_bin - state->alpha_start_bin + 1;

    /* Allocate and compute Q14 coefficients */
    state->coeffs_q14 = calloc(state->total_bins, sizeof(int16_t));
    if (!state->coeffs_q14) {
        free(state);
        return result;
    }

    for (uint32_t k = state->alpha_start_bin; k <= state->beta_end_bin; k++) {
        double omega = 2.0 * M_PI * (double)k / (double)state->window_length;
        double coeff = 2.0 * cos(omega);
        uint32_t bin_idx = k - state->alpha_start_bin;
        state->coeffs_q14[bin_idx] = double_to_q14(coeff);
    }

    result.handle = state;
    result.output_window_length_samples = 2;  /* 2 bands */
    result.output_channels = config->channels;

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    goertzel_q15_state_t *s = (goertzel_q15_state_t *)handle;
    const int16_t *in = (const int16_t *)input;
    int16_t *out = (int16_t *)output;

    const uint32_t C = s->channels;
    const uint32_t total = s->total_bins;

    /*
     * Scratch arrays for Goertzel recurrence state.
     * s1[bin][ch] and s2[bin][ch] hold Q15 values in int32_t to prevent
     * intermediate overflow from the recurrence: s0 = x + coeff*s1 - s2
     */
    const size_t scratch_count = total * C;
    int32_t *s1 = (int32_t *)alloca(scratch_count * sizeof(int32_t));
    int32_t *s2 = (int32_t *)alloca(scratch_count * sizeof(int32_t));
    memset(s1, 0, scratch_count * sizeof(int32_t));
    memset(s2, 0, scratch_count * sizeof(int32_t));

    /* Goertzel recurrence: s0 = x[n] + coeff*s1 - s2 */
    for (uint32_t n = 0; n < s->window_length; n++) {
        for (uint32_t b = 0; b < total; b++) {
            int16_t coeff = s->coeffs_q14[b];
            for (uint32_t ch = 0; ch < C; ch++) {
                uint32_t idx = b * C + ch;
                int32_t x_val = (int32_t)in[n * C + ch];

                /* coeff_q14 × s1_q15 → Q15 result (via q14_mul_q15) */
                int32_t cs1 = q14_mul_q15(coeff, s1[idx]);
                int32_t s0 = x_val + cs1 - s2[idx];

                /* Saturate to prevent unbounded growth */
                if (s0 > 32767) s0 = 32767;
                else if (s0 < -32768) s0 = -32768;

                s2[idx] = s1[idx];
                s1[idx] = s0;
            }
        }
    }

    /* Compute power: P_k = s1² + s2² - coeff*s1*s2 */
    /* Accumulate band power in int64_t, then scale to Q15 */

    /* Alpha band power */
    for (uint32_t ch = 0; ch < C; ch++) {
        int64_t alpha_power = 0;
        for (uint32_t k = s->alpha_start_bin; k <= s->alpha_end_bin; k++) {
            uint32_t b = k - s->alpha_start_bin;
            uint32_t idx = b * C + ch;

            int64_t s1v = (int64_t)s1[idx];
            int64_t s2v = (int64_t)s2[idx];
            int64_t coeff_v = (int64_t)s->coeffs_q14[b];

            /* P_k in Q30 (Q15 × Q15) */
            int64_t pk = s1v * s1v + s2v * s2v;
            /* coeff_q14 × (s1*s2 in Q30) → Q44, shift >>14 → Q30 */
            int64_t cross = (coeff_v * s1v * s2v + (1 << 13)) >> 14;
            pk -= cross;

            alpha_power += pk;
        }
        /* Scale: divide by window_length² to normalize, shift >>15 for Q15 */
        /* Simplification: just shift to fit in Q15 range */
        /* Power is in Q30 accumulated over bins. Divide by W to average, >>15 for Q15. */
        int64_t scaled = alpha_power / (int64_t)s->window_length;
        scaled = (scaled + (1 << 14)) >> 15;
        if (scaled > 32767) scaled = 32767;
        else if (scaled < -32768) scaled = -32768;
        out[0 * C + ch] = (int16_t)scaled;
    }

    /* Beta band power */
    for (uint32_t ch = 0; ch < C; ch++) {
        int64_t beta_power = 0;
        for (uint32_t k = s->beta_start_bin; k <= s->beta_end_bin; k++) {
            uint32_t b = k - s->alpha_start_bin;
            uint32_t idx = b * C + ch;

            int64_t s1v = (int64_t)s1[idx];
            int64_t s2v = (int64_t)s2[idx];
            int64_t coeff_v = (int64_t)s->coeffs_q14[b];

            int64_t pk = s1v * s1v + s2v * s2v;
            int64_t cross = (coeff_v * s1v * s2v + (1 << 13)) >> 14;
            pk -= cross;

            beta_power += pk;
        }
        int64_t scaled = beta_power / (int64_t)s->window_length;
        scaled = (scaled + (1 << 14)) >> 15;
        if (scaled > 32767) scaled = 32767;
        else if (scaled < -32768) scaled = -32768;
        out[1 * C + ch] = (int16_t)scaled;
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    goertzel_q15_state_t *s = (goertzel_q15_state_t *)handle;
    free(s->coeffs_q14);
    free(s);
}
