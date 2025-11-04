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

/* Fixed frequency bands for v1 (not configurable - kernel_params not passed yet) */
#define ALPHA_LOW_HZ 8
#define ALPHA_HIGH_HZ 13
#define BETA_LOW_HZ 13
#define BETA_HIGH_HZ 30

#define NUM_BANDS 2  /* Alpha and beta for v1 */

/* State structure for Goertzel bandpower */
typedef struct {
    uint32_t channels;          /* From config */
    uint32_t window_length;     /* From config */
    uint32_t sample_rate_hz;     /* From config */
    uint32_t alpha_start_bin;    /* Computed from ALPHA_LOW_HZ: round(ALPHA_LOW_HZ * N / Fs) */
    uint32_t alpha_end_bin;      /* Computed from ALPHA_HIGH_HZ: round(ALPHA_HIGH_HZ * N / Fs) */
    uint32_t beta_start_bin;     /* Computed from BETA_LOW_HZ: round(BETA_LOW_HZ * N / Fs) */
    uint32_t beta_end_bin;       /* Computed from BETA_HIGH_HZ: round(BETA_HIGH_HZ * N / Fs) */
    uint32_t total_bins;         /* Computed: beta_end_bin - alpha_start_bin + 1 */
    double *coeffs;              /* Pre-computed 2*cos(2πk/N) for all bins */
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
    /* Use conservative estimate: assume up to 50 bins (for Fs=500 Hz, N=160: 30 Hz → ~10 bins, but allow margin) */
    info.state_bytes = sizeof(goertzel_state_t) + 50 * sizeof(double);
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

    /* Allocate state structure */
    goertzel_state_t *state = (goertzel_state_t *)calloc(1, sizeof(goertzel_state_t));
    if (!state) {
        return NULL;
    }

    /* Store config values */
    state->channels = config->channels;
    state->window_length = config->window_length_samples;
    state->sample_rate_hz = config->sample_rate_hz;

    /* Compute bin indices from Hz frequency bands: k = round(f * N / Fs) */
    state->alpha_start_bin = (uint32_t)round((double)ALPHA_LOW_HZ * (double)state->window_length / (double)state->sample_rate_hz);
    state->alpha_end_bin = (uint32_t)round((double)ALPHA_HIGH_HZ * (double)state->window_length / (double)state->sample_rate_hz);
    state->beta_start_bin = (uint32_t)round((double)BETA_LOW_HZ * (double)state->window_length / (double)state->sample_rate_hz);
    state->beta_end_bin = (uint32_t)round((double)BETA_HIGH_HZ * (double)state->window_length / (double)state->sample_rate_hz);

    /* Validate bin ranges */
    if (state->alpha_start_bin >= state->alpha_end_bin) {
        fprintf(stderr, "[goertzel] error: invalid alpha band bins: start=%u >= end=%u\n",
                state->alpha_start_bin, state->alpha_end_bin);
        free(state);
        return NULL;
    }
    if (state->beta_start_bin >= state->beta_end_bin) {
        fprintf(stderr, "[goertzel] error: invalid beta band bins: start=%u >= end=%u\n",
                state->beta_start_bin, state->beta_end_bin);
        free(state);
        return NULL;
    }
    if (state->alpha_end_bin > state->window_length / 2) {
        fprintf(stderr, "[goertzel] error: alpha_end_bin=%u exceeds Nyquist (N/2=%u)\n",
                state->alpha_end_bin, state->window_length / 2);
        free(state);
        return NULL;
    }
    if (state->beta_end_bin > state->window_length / 2) {
        fprintf(stderr, "[goertzel] error: beta_end_bin=%u exceeds Nyquist (N/2=%u)\n",
                state->beta_end_bin, state->window_length / 2);
        free(state);
        return NULL;
    }

    /* Compute total bins: all bins from alpha_start to beta_end (inclusive) */
    state->total_bins = state->beta_end_bin - state->alpha_start_bin + 1;

    /* Allocate coefficients array */
    state->coeffs = (double *)calloc(state->total_bins, sizeof(double));
    if (!state->coeffs) {
        free(state);
        return NULL;
    }

    /* Pre-compute cosine coefficients for all bins */
    for (uint32_t k = state->alpha_start_bin; k <= state->beta_end_bin; k++) {
        double omega = 2.0 * M_PI * (double)k / (double)state->window_length;
        uint32_t bin_idx = k - state->alpha_start_bin;
        state->coeffs[bin_idx] = 2.0 * cos(omega);
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
    const size_t scratch_size = s->total_bins * s->channels * sizeof(double);
    
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
        /* For each bin k from alpha_start to beta_end */
        for (uint32_t k = s->alpha_start_bin; k <= s->beta_end_bin; k++) {
            uint32_t bin_idx = k - s->alpha_start_bin;
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
    for (uint32_t k = s->alpha_start_bin; k <= s->beta_end_bin; k++) {
        uint32_t bin_idx = k - s->alpha_start_bin;
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
    /* Band 0: Alpha (from alpha_start_bin to alpha_end_bin) */
    for (uint32_t ch = 0; ch < s->channels; ch++) {
        double alpha_power = 0.0;
        for (uint32_t k = s->alpha_start_bin; k <= s->alpha_end_bin; k++) {
            uint32_t bin_idx = k - s->alpha_start_bin;
            uint32_t idx = bin_idx * s->channels + ch;
            alpha_power += Pk[idx];
        }
        out[0 * s->channels + ch] = (float)alpha_power;
    }

    /* Band 1: Beta (from beta_start_bin to beta_end_bin) */
    for (uint32_t ch = 0; ch < s->channels; ch++) {
        double beta_power = 0.0;
        for (uint32_t k = s->beta_start_bin; k <= s->beta_end_bin; k++) {
            uint32_t bin_idx = k - s->alpha_start_bin;
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

