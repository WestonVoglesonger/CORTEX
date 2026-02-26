/*
 * FFT Magnitude-Squared Kernel for CORTEX (Q15)
 *
 * Computes one-sided magnitude-squared spectrum using kiss_fft in
 * FIXED_POINT=16 mode. kiss_fft_scalar becomes int16_t and butterfly
 * arithmetic uses C_FIXDIV per-stage scaling.
 *
 * ABI Compatibility: v2 (non-trainable, backward compatible with v3 harness)
 * Data Type: Q15
 * Input shape: (W, C)
 * Output shape: (W/2+1, C)
 *
 * Important: Both this file and kiss_fft.c MUST be compiled with
 * -DFIXED_POINT=16. Mismatched defines cause silent ABI breakage
 * (struct layout differs between float and int16_t).
 */

#include "cortex_plugin.h"
#include "cortex_q15.h"

/* FIXED_POINT=16 must be defined before including kiss_fft.h so that
 * kiss_fft_scalar resolves to int16_t in this translation unit. */
#ifndef FIXED_POINT
#error "fft@q15 must be compiled with -DFIXED_POINT=16"
#endif

#include "kiss_fft.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#undef CORTEX_ABI_VERSION
#define CORTEX_ABI_VERSION 2u

typedef struct {
    uint32_t n_fft;
    uint32_t channels;
    uint32_t output_bins;       /* n_fft / 2 + 1 */
    kiss_fft_cfg fft_cfg;
    kiss_fft_cpx *fft_in;      /* int16_t r/i with FIXED_POINT=16 */
    kiss_fft_cpx *fft_out;
} fft_q15_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) {
        fprintf(stderr, "[fft@q15] cortex_init: config is NULL\n");
        return result;
    }
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[fft@q15] ABI mismatch: expected %u, got %u\n",
                CORTEX_ABI_VERSION, config->abi_version);
        return result;
    }
    if (config->struct_size < sizeof(cortex_plugin_config_t)) {
        fprintf(stderr, "[fft@q15] struct_size too small: %u < %zu\n",
                config->struct_size, sizeof(cortex_plugin_config_t));
        return result;
    }
    if (config->dtype != CORTEX_DTYPE_Q15) {
        fprintf(stderr, "[fft@q15] unsupported dtype: %u (expected Q15=%u)\n",
                config->dtype, CORTEX_DTYPE_Q15);
        return result;
    }
    if (config->channels == 0) {
        fprintf(stderr, "[fft@q15] channels must be > 0\n");
        return result;
    }

    uint32_t n_fft = config->window_length_samples;

    /* Validate n_fft is a kiss_fft "fast size" (factors into {2,3,5}) */
    if ((int)n_fft != kiss_fft_next_fast_size((int)n_fft)) {
        fprintf(stderr, "[fft@q15] n_fft=%u is not a kiss_fft fast size "
                "(smallest fast size >= %u is %d)\n",
                n_fft, n_fft, kiss_fft_next_fast_size((int)n_fft));
        return result;
    }

    /* Check allocation size overflow */
    if (n_fft > SIZE_MAX / sizeof(kiss_fft_cpx)) {
        fprintf(stderr, "[fft@q15] n_fft=%u causes allocation overflow\n", n_fft);
        return result;
    }

    fft_q15_state_t *st = (fft_q15_state_t *)calloc(1, sizeof(fft_q15_state_t));
    if (!st) {
        fprintf(stderr, "[fft@q15] calloc failed for state\n");
        return result;
    }

    st->n_fft = n_fft;
    st->channels = config->channels;
    st->output_bins = n_fft / 2 + 1;

    st->fft_cfg = kiss_fft_alloc((int)n_fft, 0, NULL, NULL);
    st->fft_in = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * n_fft);
    st->fft_out = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * n_fft);

    if (!st->fft_cfg || !st->fft_in || !st->fft_out) {
        fprintf(stderr, "[fft@q15] allocation failed: cfg=%p in=%p out=%p\n",
                (void *)st->fft_cfg, (void *)st->fft_in, (void *)st->fft_out);
        cortex_teardown(st);
        return result;
    }

    result.handle = st;
    result.output_window_length_samples = st->output_bins;
    result.output_channels = config->channels;

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    fft_q15_state_t *st = (fft_q15_state_t *)handle;
    const int16_t *in = (const int16_t *)input;
    int16_t *out = (int16_t *)output;

    const uint32_t N = st->n_fft;
    const uint32_t C = st->channels;
    const uint32_t bins = st->output_bins;

    for (uint32_t c = 0; c < C; c++) {
        /* Extract channel c from interleaved Q15 input */
        for (uint32_t i = 0; i < N; i++) {
            st->fft_in[i].r = in[i * C + c];
            st->fft_in[i].i = 0;
        }

        kiss_fft(st->fft_cfg, st->fft_in, st->fft_out);

        /* Magnitude-squared: accumulate in int64 to avoid overflow.
         * Worst case: (-32768)^2 + (-32768)^2 = 2^31, exceeds INT32_MAX.
         * Result is in Q30 (Q15 * Q15). Shift >> 15 to get Q15. */
        for (uint32_t k = 0; k < bins; k++) {
            int64_t re = (int64_t)st->fft_out[k].r;
            int64_t im = (int64_t)st->fft_out[k].i;
            int64_t mag_sq = re * re + im * im;

            /* Q30 -> Q15 with rounding */
            int32_t result_val = (int32_t)((mag_sq + (1 << 14)) >> 15);

            /* Saturate to Q15 (mag-sq is non-negative, only upper bound matters) */
            if (result_val > 32767) result_val = 32767;

            out[k * C + c] = (int16_t)result_val;
        }
    }
}

void cortex_teardown(void *handle) {
    fft_q15_state_t *st = (fft_q15_state_t *)handle;
    if (st) {
        free(st->fft_in);
        free(st->fft_out);
        if (st->fft_cfg) kiss_fft_free(st->fft_cfg);
        free(st);
    }
}
