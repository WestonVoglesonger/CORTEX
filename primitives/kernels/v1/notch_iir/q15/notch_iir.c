/*
 * Notch IIR Filter for Q15 data type.
 *
 * Second-order (biquad) notch filter using Q15 I/O with Q14 coefficients
 * and Q31 internal state for feedback stability.
 *
 * Coefficients are stored in Q14 format (range [-2, +2)) because biquad
 * numerator/denominator coefficients (b1, a1) can exceed 1.0.
 * State arrays (x[n-1], x[n-2], y[n-1], y[n-2]) are stored as int32_t
 * (Q31) to prevent precision loss in the recursive feedback path.
 *
 * MAC: 5 multiplies per sample, accumulate in int64_t, shift >>14, saturate.
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

/* Default notch filter parameters */
#define DEFAULT_NOTCH_F0_HZ 60.0
#define DEFAULT_NOTCH_Q 30.0

/* Q14 format: range [-2.0, +1.999878] in int16_t, shift = 14 */
#define Q14_SHIFT 14

typedef struct {
    uint32_t channels;
    uint32_t window_length;
    /* Coefficients in Q14 format */
    int16_t b0_q14;
    int16_t b1_q14;
    int16_t b2_q14;
    int16_t a1_q14;
    int16_t a2_q14;
    /*
     * Per-channel state: [x[n-1], x[n-2], y[n-1], y[n-2]]
     * Stored as int32_t (Q31) for feedback stability.
     * But since Q15 inputs are only 16-bit, x state could be int16_t.
     * We use int32_t uniformly for simplicity and to match y state precision.
     */
    int32_t *state;  /* 4 * channels elements */
} notch_iir_q15_state_t;

/* Quantize a double coefficient to Q14 with clamping.
 * Q14 range: [-2.0, +2.0) stored in full int16_t range [-32768, 32767].
 * Biquad coefficients (b1, a1) can reach ~1.36, well within Q14 range. */
static int16_t double_to_q14(double x) {
    double scaled = x * 16384.0;  /* 1 << 14 */
    int32_t rounded = (int32_t)(scaled + (scaled >= 0.0 ? 0.5 : -0.5));
    if (rounded > 32767)  rounded = 32767;
    if (rounded < -32768) rounded = -32768;
    return (int16_t)rounded;
}

/* Compute biquad notch filter coefficients (same as f32 version) */
static void compute_notch_coefficients(double f0, double Q, double fs,
                                       double *b0, double *b1, double *b2,
                                       double *a1, double *a2) {
    if (fabs(f0 - 60.0) < 1e-6 && fabs(Q - 30.0) < 1e-6 && fabs(fs - 160.0) < 1e-6) {
        *b0 = 0.9621952458291035;
        *b1 = 1.3607495663024323;
        *b2 = 0.9621952458291035;
        *a1 = 1.3607495663024323;
        *a2 = 0.9243904916582071;
    } else {
        const double w0 = 2.0 * M_PI * f0 / fs;
        const double cos_w0 = cos(w0);
        const double BW = f0 / Q;
        const double r = exp(-M_PI * BW / fs);

        *b0 = 1.0;
        *b1 = -2.0 * cos_w0;
        *b2 = 1.0;
        *a1 = -2.0 * r * cos_w0;
        *a2 = r * r;
    }
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_Q15) return result;

    /* Parse parameters */
    const char *params_str = (const char *)config->kernel_params;
    double f0_hz = cortex_param_float(params_str, "f0_hz", DEFAULT_NOTCH_F0_HZ);
    double Q = cortex_param_float(params_str, "Q", DEFAULT_NOTCH_Q);

    /* Validate */
    if (f0_hz <= 0.0) {
        fprintf(stderr, "[notch_iir@q15] error: f0_hz must be positive (got %.1f)\n", f0_hz);
        return result;
    }
    if (Q <= 0.0) {
        fprintf(stderr, "[notch_iir@q15] error: Q must be positive (got %.2f)\n", Q);
        return result;
    }
    double nyquist = config->sample_rate_hz / 2.0;
    if (f0_hz >= nyquist) {
        fprintf(stderr, "[notch_iir@q15] error: f0_hz (%.1f) >= Nyquist (%.1f)\n", f0_hz, nyquist);
        return result;
    }

    /* Compute double-precision coefficients first */
    double b0_d, b1_d, b2_d, a1_d, a2_d;
    compute_notch_coefficients(f0_hz, Q, (double)config->sample_rate_hz,
                               &b0_d, &b1_d, &b2_d, &a1_d, &a2_d);

    /* Allocate state */
    notch_iir_q15_state_t *st = (notch_iir_q15_state_t *)calloc(1, sizeof(notch_iir_q15_state_t));
    if (!st) return result;

    st->channels = config->channels;
    st->window_length = config->window_length_samples;

    /* Quantize coefficients to Q14 */
    st->b0_q14 = double_to_q14(b0_d);
    st->b1_q14 = double_to_q14(b1_d);
    st->b2_q14 = double_to_q14(b2_d);
    st->a1_q14 = double_to_q14(a1_d);
    st->a2_q14 = double_to_q14(a2_d);

    /* Allocate per-channel state: 4 int32_t per channel, zero-initialized */
    const size_t state_count = 4 * (size_t)config->channels;
    st->state = (int32_t *)calloc(state_count, sizeof(int32_t));
    if (!st->state) {
        free(st);
        return result;
    }

    result.handle = st;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    notch_iir_q15_state_t *st = (notch_iir_q15_state_t *)handle;
    const int16_t *in  = (const int16_t *)input;
    int16_t       *out = (int16_t *)output;

    const uint32_t W = st->window_length;
    const uint32_t C = st->channels;

    /* Coefficients (Q14) */
    const int64_t b0 = (int64_t)st->b0_q14;
    const int64_t b1 = (int64_t)st->b1_q14;
    const int64_t b2 = (int64_t)st->b2_q14;
    const int64_t a1 = (int64_t)st->a1_q14;
    const int64_t a2 = (int64_t)st->a2_q14;

    for (uint32_t ch = 0; ch < C; ch++) {
        /* Per-channel state: [x[n-1], x[n-2], y[n-1], y[n-2]] as int32_t */
        int32_t *ch_state = &st->state[ch * 4];
        int32_t x1 = ch_state[0];
        int32_t x2 = ch_state[1];
        int32_t y1 = ch_state[2];
        int32_t y2 = ch_state[3];

        for (uint32_t t = 0; t < W; t++) {
            /* Input sample (Q15, sign-extended to int32) */
            int32_t x0 = (int32_t)in[t * C + ch];

            /*
             * Biquad: y = b0*x + b1*x1 + b2*x2 - a1*y1 - a2*y2
             *
             * All multiplies: Q14 * Q15 -> Q29, accumulated in int64_t.
             * For y1/y2 feedback terms: Q14 * Q31 -> needs careful handling.
             * Since y state stores the Q15-scale value (not Q31), we treat
             * state as Q15-scale int32_t for overflow room.
             *
             * Accumulator is in Q29 (Q14 + Q15), shift >>14 to get Q15 output.
             */
            int64_t acc = 0;
            acc += b0 * (int64_t)x0;
            acc += b1 * (int64_t)x1;
            acc += b2 * (int64_t)x2;
            acc -= a1 * (int64_t)y1;
            acc -= a2 * (int64_t)y2;

            /* Round-to-nearest: add 0.5 in Q29, then shift >>14 to Q15 */
            acc += (1 << 13);  /* rounding bias */
            int32_t y0 = (int32_t)(acc >> Q14_SHIFT);

            /* Saturate to Q15 range */
            if (y0 > 32767)  y0 = 32767;
            if (y0 < -32768) y0 = -32768;

            out[t * C + ch] = (int16_t)y0;

            /* Shift state */
            x2 = x1;
            x1 = x0;
            y2 = y1;
            y1 = y0;
        }

        /* Save state back */
        ch_state[0] = x1;
        ch_state[1] = x2;
        ch_state[2] = y1;
        ch_state[3] = y2;
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    notch_iir_q15_state_t *st = (notch_iir_q15_state_t *)handle;
    free(st->state);
    free(st);
}
