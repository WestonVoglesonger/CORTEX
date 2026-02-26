/*
 * FFT Magnitude-Squared Kernel for CORTEX
 *
 * Computes one-sided magnitude-squared spectrum |X[k]|^2 for k=0..N/2.
 * No windowing applied (raw FFT). Chain a windowing kernel before this
 * if needed.
 *
 * ABI Compatibility: v2 (non-trainable, backward compatible with v3 harness)
 * Data Type: float32
 * Input shape: (W, C)
 * Output shape: (W/2+1, C)
 */

#include "cortex_plugin.h"
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
    kiss_fft_cpx *fft_in;
    kiss_fft_cpx *fft_out;
} fft_f32_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) {
        fprintf(stderr, "[fft@f32] cortex_init: config is NULL\n");
        return result;
    }
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[fft@f32] ABI mismatch: expected %u, got %u\n",
                CORTEX_ABI_VERSION, config->abi_version);
        return result;
    }
    if (config->struct_size < sizeof(cortex_plugin_config_t)) {
        fprintf(stderr, "[fft@f32] struct_size too small: %u < %zu\n",
                config->struct_size, sizeof(cortex_plugin_config_t));
        return result;
    }
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        fprintf(stderr, "[fft@f32] unsupported dtype: %u (expected FLOAT32=%u)\n",
                config->dtype, CORTEX_DTYPE_FLOAT32);
        return result;
    }
    if (config->channels == 0) {
        fprintf(stderr, "[fft@f32] channels must be > 0\n");
        return result;
    }

    uint32_t n_fft = config->window_length_samples;

    /* Validate n_fft is a kiss_fft "fast size" (factors into {2,3,5}) */
    if ((int)n_fft != kiss_fft_next_fast_size((int)n_fft)) {
        fprintf(stderr, "[fft@f32] n_fft=%u is not a kiss_fft fast size "
                "(smallest fast size >= %u is %d)\n",
                n_fft, n_fft, kiss_fft_next_fast_size((int)n_fft));
        return result;
    }

    /* Check allocation size overflow */
    if (n_fft > SIZE_MAX / sizeof(kiss_fft_cpx)) {
        fprintf(stderr, "[fft@f32] n_fft=%u causes allocation overflow\n", n_fft);
        return result;
    }

    fft_f32_state_t *st = (fft_f32_state_t *)calloc(1, sizeof(fft_f32_state_t));
    if (!st) {
        fprintf(stderr, "[fft@f32] calloc failed for state\n");
        return result;
    }

    st->n_fft = n_fft;
    st->channels = config->channels;
    st->output_bins = n_fft / 2 + 1;

    st->fft_cfg = kiss_fft_alloc((int)n_fft, 0, NULL, NULL);
    st->fft_in = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * n_fft);
    st->fft_out = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * n_fft);

    if (!st->fft_cfg || !st->fft_in || !st->fft_out) {
        fprintf(stderr, "[fft@f32] allocation failed: cfg=%p in=%p out=%p\n",
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

    fft_f32_state_t *st = (fft_f32_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    const uint32_t N = st->n_fft;
    const uint32_t C = st->channels;
    const uint32_t bins = st->output_bins;

    for (uint32_t c = 0; c < C; c++) {
        /* Extract channel c from interleaved input into fft_in */
        for (uint32_t i = 0; i < N; i++) {
            st->fft_in[i].r = in[i * C + c];
            st->fft_in[i].i = 0.0f;
        }

        kiss_fft(st->fft_cfg, st->fft_in, st->fft_out);

        /* Magnitude-squared of one-sided spectrum */
        for (uint32_t k = 0; k < bins; k++) {
            float re = st->fft_out[k].r;
            float im = st->fft_out[k].i;
            out[k * C + c] = re * re + im * im;
        }
    }
}

void cortex_teardown(void *handle) {
    fft_f32_state_t *st = (fft_f32_state_t *)handle;
    if (st) {
        free(st->fft_in);
        free(st->fft_out);
        if (st->fft_cfg) kiss_fft_free(st->fft_cfg);
        free(st);
    }
}
