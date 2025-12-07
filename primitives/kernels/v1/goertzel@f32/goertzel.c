/*
 * Goertzel Bandpower Plugin for CORTEX
 *
 * Implements the Goertzel algorithm for computing bandpower in specified
 * frequency bands (alpha: 8-13 Hz, beta: 13-30 Hz). Operates per window
 * (stateless) and outputs power spectral density estimates.
 */

#include "cortex_plugin.h"
#include "accessor.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <stdio.h>
#include <alloca.h>

#define CORTEX_ABI_VERSION 2u
#define CORTEX_DTYPE_FLOAT32_MASK (1u << 0)

/* Default frequency bands (configurable via kernel_params) */
#define DEFAULT_ALPHA_LOW_HZ 8.0
#define DEFAULT_ALPHA_HIGH_HZ 13.0
#define DEFAULT_BETA_LOW_HZ 13.0
#define DEFAULT_BETA_HIGH_HZ 30.0

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

/* Initialize plugin instance */
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};
    
    if (!config) {
        return result;  /* {NULL, 0, 0} */
    }

    /* Validate ABI version */
    if (config->abi_version != CORTEX_ABI_VERSION) {
        return result;
    }

    if (config->struct_size < sizeof(cortex_plugin_config_t)) {
        return result;
    }

    /* Validate dtype */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        return result;
    }

    /* Allocate state structure */
    goertzel_state_t *state = (goertzel_state_t *)calloc(1, sizeof(goertzel_state_t));
    if (!state) {
        return result;
    }

    /* Store config values */
    state->channels = config->channels;
    state->window_length = config->window_length_samples;
    state->sample_rate_hz = config->sample_rate_hz;

    /* Parse kernel parameters for frequency bands */
    const char *params_str = (const char *)config->kernel_params;
    double alpha_low = cortex_param_float(params_str, "alpha_low", DEFAULT_ALPHA_LOW_HZ);
    double alpha_high = cortex_param_float(params_str, "alpha_high", DEFAULT_ALPHA_HIGH_HZ);
    double beta_low = cortex_param_float(params_str, "beta_low", DEFAULT_BETA_LOW_HZ);
    double beta_high = cortex_param_float(params_str, "beta_high", DEFAULT_BETA_HIGH_HZ);

    /* Validate frequency ranges */
    if (alpha_low <= 0.0 || alpha_high <= alpha_low) {
        fprintf(stderr, "[goertzel] error: invalid alpha band: low=%.1f, high=%.1f\n",
                alpha_low, alpha_high);
        free(state);
        return result;
    }
    if (beta_low <= 0.0 || beta_high <= beta_low) {
        fprintf(stderr, "[goertzel] error: invalid beta band: low=%.1f, high=%.1f\n",
                beta_low, beta_high);
        free(state);
        return result;
    }

    /* Compute bin indices from Hz frequency bands: k = round(f * N / Fs) */
    state->alpha_start_bin = (uint32_t)round(alpha_low * (double)state->window_length / (double)state->sample_rate_hz);
    state->alpha_end_bin = (uint32_t)round(alpha_high * (double)state->window_length / (double)state->sample_rate_hz);
    state->beta_start_bin = (uint32_t)round(beta_low * (double)state->window_length / (double)state->sample_rate_hz);
    state->beta_end_bin = (uint32_t)round(beta_high * (double)state->window_length / (double)state->sample_rate_hz);

    /* Validate bin ranges */
    if (state->alpha_start_bin >= state->alpha_end_bin) {
        fprintf(stderr, "[goertzel] error: invalid alpha band bins: start=%u >= end=%u\n",
                state->alpha_start_bin, state->alpha_end_bin);
        free(state);
        return result;
    }
    if (state->beta_start_bin >= state->beta_end_bin) {
        fprintf(stderr, "[goertzel] error: invalid beta band bins: start=%u >= end=%u\n",
                state->beta_start_bin, state->beta_end_bin);
        free(state);
        return result;
    }
    if (state->alpha_end_bin > state->window_length / 2) {
        fprintf(stderr, "[goertzel] error: alpha_end_bin=%u exceeds Nyquist (N/2=%u)\n",
                state->alpha_end_bin, state->window_length / 2);
        free(state);
        return result;
    }
    if (state->beta_end_bin > state->window_length / 2) {
        fprintf(stderr, "[goertzel] error: beta_end_bin=%u exceeds Nyquist (N/2=%u)\n",
                state->beta_end_bin, state->window_length / 2);
        free(state);
        return result;
    }

    /* Compute total bins: all bins from alpha_start to beta_end (inclusive) */
    state->total_bins = state->beta_end_bin - state->alpha_start_bin + 1;

    /* Allocate coefficients array */
    state->coeffs = (double *)calloc(state->total_bins, sizeof(double));
    if (!state->coeffs) {
        free(state);
        return result;
    }

    /* Pre-compute cosine coefficients for all bins */
    for (uint32_t k = state->alpha_start_bin; k <= state->beta_end_bin; k++) {
        double omega = 2.0 * M_PI * (double)k / (double)state->window_length;
        uint32_t bin_idx = k - state->alpha_start_bin;
        state->coeffs[bin_idx] = 2.0 * cos(omega);
    }

    /* Set output dimensions */
    result.handle = state;
    result.output_window_length_samples = 2;  /* Fixed: 2 bands */
    result.output_channels = config->channels;  /* Matches input */

    return result;
}

/* Process one window of data */
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) {
        return;
    }

    goertzel_state_t *s = (goertzel_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    /* Allocate scratch space for recurrence state (on stack using alloca) */
    /* Size: total_bins * channels for each array (s0, s1, s2, Pk) */
    /* Note: alloca() allocates on stack, automatically freed on return */
    /* This avoids heap allocation in process() per ABI requirement */
    const size_t scratch_size = s->total_bins * s->channels * sizeof(double);
    double *s0 = (double *)alloca(scratch_size);
    double *s1 = (double *)alloca(scratch_size);
    double *s2 = (double *)alloca(scratch_size);
    double *Pk = (double *)alloca(scratch_size);
    
    /* Initialize to zero */
    memset(s0, 0, scratch_size);
    memset(s1, 0, scratch_size);
    memset(s2, 0, scratch_size);
    memset(Pk, 0, scratch_size);

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

