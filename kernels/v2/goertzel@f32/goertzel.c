/*
 * Goertzel Bandpower Plugin for CORTEX
 *
 * Implements the Goertzel algorithm for computing bandpower in specified
 * frequency bands (alpha: 8-13 Hz, beta: 13-30 Hz). Operates per window
 * (stateless) and outputs power spectral density estimates.
 */

#include "cortex_plugin.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <stdio.h>
#include <alloca.h>

#define CORTEX_ABI_VERSION 1u
#define CORTEX_DTYPE_FLOAT32_MASK (1u << 0)

/* Fixed bands for v1 (not configurable - kernel_params not passed yet) */
#define ALPHA_LOW_HZ 8
#define ALPHA_HIGH_HZ 13
#define BETA_LOW_HZ 13
#define BETA_HIGH_HZ 30

/* Frequency bin ranges (inclusive) */
#define ALPHA_START_BIN 8
#define ALPHA_END_BIN 13
#define BETA_START_BIN 13
#define BETA_END_BIN 30

/* Total bins to compute: k=8..30 inclusive = 23 bins */
#define TOTAL_BINS (BETA_END_BIN - ALPHA_START_BIN + 1)
#define NUM_BANDS 2  /* Alpha and beta for v1 */

/* State structure for Goertzel bandpower */
typedef struct {
    uint32_t channels;          /* From config (not hardcoded 64) */
    uint32_t window_length;     /* From config (should be 160) */
    uint32_t sample_rate_hz;    /* From config (should be 160) */
    double *coeffs;             /* Pre-computed 2*cos(2πk/N) for k=8..30 */
} goertzel_state_t;

/* Get plugin metadata */
cortex_plugin_info_t cortex_get_info(void) {
    cortex_plugin_info_t info = {0};
    
    info.name = "goertzel";
    info.description = "Goertzel algorithm for computing bandpower (alpha 8-13 Hz, beta 13-30 Hz) - v2 with cache aliasing fix";
    info.version = "2.0.0";
    info.supported_dtypes = CORTEX_DTYPE_FLOAT32_MASK;
    
    info.input_window_length_samples = 160;  /* Default from spec */
    info.input_channels = 64;                 /* Default from spec */
    info.output_window_length_samples = 2;    /* Fixed 2 bands for v1 */
    info.output_channels = 64;                /* Default - actual from config */
    
    /* State size: struct + coefficients array */
    info.state_bytes = sizeof(goertzel_state_t) + TOTAL_BINS * sizeof(double);
    info.workspace_bytes = 0;  /* No per-call workspace needed */
    
    return info;
}

/* Initialize plugin instance */
void *cortex_init(const cortex_plugin_config_t *config) {
    if (!config) {
        return NULL;
    }

    /* Validate ABI version */
    if (config->abi_version != CORTEX_ABI_VERSION) {
        return NULL;
    }

    if (config->struct_size < sizeof(cortex_plugin_config_t)) {
        return NULL;
    }

    /* Validate dtype */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        return NULL;
    }

    /* Warn if sample rate doesn't match expected value (but don't fail) */
    if (config->sample_rate_hz != 160) {
        fprintf(stderr, "[goertzel] warning: coefficients designed for 160 Hz, "
                "config has %u Hz\n", config->sample_rate_hz);
    }

    /* Warn if window length doesn't match expected value (but don't fail) */
    if (config->window_length_samples != 160) {
        fprintf(stderr, "[goertzel] warning: algorithm designed for 160 samples, "
                "config has %u samples\n", config->window_length_samples);
    }

    /* Allocate state structure */
    goertzel_state_t *state = (goertzel_state_t *)calloc(1, sizeof(goertzel_state_t));
    if (!state) {
        return NULL;
    }

    /* Store config values */
    state->channels = config->channels;  /* Use from config, not hardcoded */
    state->window_length = config->window_length_samples;
    state->sample_rate_hz = config->sample_rate_hz;

    /* Allocate coefficients array: 23 bins (k=8..30) */
    state->coeffs = (double *)calloc(TOTAL_BINS, sizeof(double));
    if (!state->coeffs) {
        free(state);
        return NULL;
    }

    /* Pre-compute cosine coefficients for all bins k=8..30 */
    for (uint32_t k = ALPHA_START_BIN; k <= BETA_END_BIN; k++) {
        double omega = 2.0 * M_PI * (double)k / (double)state->window_length;
        state->coeffs[k - ALPHA_START_BIN] = 2.0 * cos(omega);
    }

    return state;
}

/* Process one window of data */
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) {
        return;
    }

    goertzel_state_t *s = (goertzel_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    /* Allocate scratch space using struct-of-arrays layout to avoid cache aliasing */
    /* v2 fix: Single allocation with struct-of-arrays eliminates cache set conflicts */
    /* v1 issue: Separate alloca() calls with 11,776 byte separation caused all buffers */
    /* to alias to the same cache set (11,776 % 512 = 0), creating bimodal performance */
    
    /* Calculate size needed for each buffer */
    const size_t scratch_size = TOTAL_BINS * s->channels * sizeof(double);
    
    /* Add padding to break cache set alignment (512 bytes = 8 cache lines) */
    /* This ensures buffers don't alias to the same cache set */
    const size_t cache_set_size = 512;  /* Typical L1 cache has 512 sets */
    const size_t padding = cache_set_size;  /* Pad by one cache set to avoid aliasing */
    
    /* Single allocation for all four buffers with padding */
    const size_t total_size = 4 * scratch_size + 3 * padding;
    char *scratch_base = (char *)alloca(total_size);
    
    /* Initialize entire allocation to zero */
    memset(scratch_base, 0, total_size);
    
    /* Set up pointers with padding between buffers to avoid cache set conflicts */
    double *s0 = (double *)(scratch_base);
    double *s1 = (double *)(scratch_base + scratch_size + padding);
    double *s2 = (double *)(scratch_base + 2 * (scratch_size + padding));
    double *Pk = (double *)(scratch_base + 3 * (scratch_size + padding));

    /* Process all bins simultaneously */
    /* For each sample n in the window */
    for (uint32_t n = 0; n < s->window_length; n++) {
        /* For each bin k */
        for (uint32_t k = ALPHA_START_BIN; k <= BETA_END_BIN; k++) {
            uint32_t bin_idx = k - ALPHA_START_BIN;
            double coeff = s->coeffs[bin_idx];
            
            /* For each channel */
            for (uint32_t ch = 0; ch < s->channels; ch++) {
                /* Calculate linear index: bin_idx * channels + channel */
                uint32_t idx = bin_idx * s->channels + ch;
                
                /* Read input sample */
                const float x_raw = in[n * s->channels + ch];
                /* Handle NaN: treat as 0.0 */
                const float x_val = (x_raw == x_raw) ? x_raw : 0.0f;

                /* Run Goertzel recurrence: s[n] = x[n] + coeff*s[n-1] - s[n-2] */
                double s0_val = (double)x_val + coeff * s1[idx] - s2[idx];

                /* Update state: shift s1->s2, s0->s1 */
                s2[idx] = s1[idx];
                s1[idx] = s0_val;
            }
        }
    }

    /* Compute power for all bins (after all samples) */
    for (uint32_t k = ALPHA_START_BIN; k <= BETA_END_BIN; k++) {
        uint32_t bin_idx = k - ALPHA_START_BIN;
        double coeff = s->coeffs[bin_idx];
        
        for (uint32_t ch = 0; ch < s->channels; ch++) {
            uint32_t idx = bin_idx * s->channels + ch;
            /* Compute power: P_k = s[N-1]² + s[N-2]² - coeff*s[N-1]*s[N-2] */
            Pk[idx] = s1[idx] * s1[idx] +
                     s2[idx] * s2[idx] -
                     coeff * s1[idx] * s2[idx];
        }
    }

    /* Sum power over bins for each band */
    /* Band 0: Alpha (k=8..13) */
    for (uint32_t ch = 0; ch < s->channels; ch++) {
        double alpha_power = 0.0;
        for (uint32_t k = ALPHA_START_BIN; k <= ALPHA_END_BIN; k++) {
            uint32_t bin_idx = k - ALPHA_START_BIN;
            uint32_t idx = bin_idx * s->channels + ch;
            alpha_power += Pk[idx];
        }
        out[0 * s->channels + ch] = (float)alpha_power;
    }

    /* Band 1: Beta (k=13..30) */
    for (uint32_t ch = 0; ch < s->channels; ch++) {
        double beta_power = 0.0;
        for (uint32_t k = BETA_START_BIN; k <= BETA_END_BIN; k++) {
            uint32_t bin_idx = k - ALPHA_START_BIN;
            uint32_t idx = bin_idx * s->channels + ch;
            beta_power += Pk[idx];
        }
        out[1 * s->channels + ch] = (float)beta_power;
    }
    
    /* Scratch space (allocated via alloca) is automatically freed on return */
}

/* Teardown plugin instance */
void cortex_teardown(void *handle) {
    if (!handle) {
        return;
    }

    goertzel_state_t *s = (goertzel_state_t *)handle;
    free(s->coeffs);  /* Free coefficients array */
    free(s);          /* Free state struct */
}

