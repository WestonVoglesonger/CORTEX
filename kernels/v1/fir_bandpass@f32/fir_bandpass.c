/*
 * FIR Bandpass Filter Plugin for CORTEX
 *
 * Implements a linear-phase FIR bandpass filter (8-30 Hz) for isolating
 * EEG frequency bands. Uses Hamming window design with persistent tail
 * across windows.
 */

#include "cortex_plugin.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <float.h>
#include <stdio.h>

#define CORTEX_ABI_VERSION 2u
#define CORTEX_DTYPE_FLOAT32_MASK (1u << 0)

/* Fixed FIR parameters (per specification) */
#define FIR_NUMTAPS 129
#define FIR_PASSBAND_LOW_HZ 8.0
#define FIR_PASSBAND_HIGH_HZ 30.0
#define FIR_SAMPLE_RATE_HZ 160.0  /* Coefficients computed for this Fs */

/* Pre-computed FIR coefficients for 129-tap bandpass (8-30 Hz @ 160 Hz, Hamming) */
/* Generated from: firwin(129, [8, 30], pass_zero=False, fs=160, window='hamming') */
/* Stored as double precision to match Python's lfilter internal precision */
/* Python's lfilter uses double precision coefficients internally for better accuracy */
static const double FIR_COEFFICIENTS[FIR_NUMTAPS] = {
    -0.000377718726899,
    -0.000703998700034,
    -0.000545563422518,
    0.000032606383802,
    0.000470439164752,
    0.000349344958976,
    -0.000065238795652,
    -0.000068437117914,
    0.000620621087778,
    0.001379959353925,
    0.001310431043817,
    0.000371727035481,
    -0.000396751915317,
    -0.000078259766658,
    0.000828636139379,
    0.000794038687397,
    -0.000835457057047,
    -0.002707040323798,
    -0.002842410714671,
    -0.001159294661945,
    0.000100526723529,
    -0.000956115079643,
    -0.003165561011930,
    -0.003280197142819,
    0.000000000000000,
    0.003867314780552,
    0.004400779631432,
    0.001567747695035,
    -0.000194494099361,
    0.002647875368915,
    0.007668821781311,
    0.008632995737849,
    0.003151480654045,
    -0.003545242604802,
    -0.004381643417694,
    0.000490306089756,
    0.002945642384166,
    -0.003269888109943,
    -0.013647832598837,
    -0.016992437645121,
    -0.009015319800308,
    0.001168904109157,
    0.001304228896737,
    -0.008126158022196,
    -0.012638524701376,
    -0.001002776667471,
    0.019012668071157,
    0.027494205869502,
    0.016341417509203,
    0.001420228327650,
    0.004958281870284,
    0.026489082048680,
    0.038780890974700,
    0.018671640507027,
    -0.021246290820280,
    -0.041602483930685,
    -0.022526890747688,
    0.005073347418054,
    -0.012662302322717,
    -0.086651535408733,
    -0.153605350149278,
    -0.125582854516061,
    0.018913763402479,
    0.195249309732459,
    0.274495194121136,
    0.195249309732459,
    0.018913763402479,
    -0.125582854516061,
    -0.153605350149278,
    -0.086651535408733,
    -0.012662302322717,
    0.005073347418054,
    -0.022526890747688,
    -0.041602483930685,
    -0.021246290820280,
    0.018671640507027,
    0.038780890974700,
    0.026489082048680,
    0.004958281870284,
    0.001420228327650,
    0.016341417509203,
    0.027494205869502,
    0.019012668071157,
    -0.001002776667471,
    -0.012638524701376,
    -0.008126158022196,
    0.001304228896737,
    0.001168904109157,
    -0.009015319800308,
    -0.016992437645121,
    -0.013647832598837,
    -0.003269888109943,
    0.002945642384166,
    0.000490306089756,
    -0.004381643417694,
    -0.003545242604802,
    0.003151480654045,
    0.008632995737849,
    0.007668821781311,
    0.002647875368915,
    -0.000194494099361,
    0.001567747695035,
    0.004400779631432,
    0.003867314780552,
    0.000000000000000,
    -0.003280197142819,
    -0.003165561011930,
    -0.000956115079643,
    0.000100526723529,
    -0.001159294661945,
    -0.002842410714671,
    -0.002707040323798,
    -0.000835457057047,
    0.000794038687397,
    0.000828636139379,
    -0.000078259766658,
    -0.000396751915317,
    0.000371727035481,
    0.001310431043817,
    0.001379959353925,
    0.000620621087778,
    -0.000068437117914,
    -0.000065238795652,
    0.000349344958976,
    0.000470439164752,
    0.000032606383802,
    -0.000545563422518,
    -0.000703998700034,
    -0.000377718726899
};

/* State structure for FIR bandpass filter */
typedef struct {
    uint32_t channels;
    uint32_t window_length;
    uint32_t hop_samples;  /* Store hop size for tail buffer alignment */
    float *tail;  /* [(FIR_NUMTAPS-1) × channels] tail buffer */
} fir_bandpass_state_t;

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

    /* Validate sample rate matches coefficient design (optional warning) */
    if (config->sample_rate_hz != (uint32_t)FIR_SAMPLE_RATE_HZ) {
        /* Coefficients designed for 160 Hz - warn but allow */
        fprintf(stderr, "[fir_bandpass] warning: coefficients designed for %.0f Hz, "
                "config has %u Hz\n", FIR_SAMPLE_RATE_HZ, config->sample_rate_hz);
    }

    /* Allocate state structure */
    fir_bandpass_state_t *state = (fir_bandpass_state_t *)calloc(1, sizeof(fir_bandpass_state_t));
    if (!state) {
        return result;
    }

    /* Store config values */
    state->channels = config->channels;  /* Use from config */
    state->window_length = config->window_length_samples;  /* Use from config */
    state->hop_samples = config->hop_samples;  /* Use from config for tail alignment */

    /* Allocate tail buffer: (FIR_NUMTAPS-1) × channels */
    const size_t tail_elements = (FIR_NUMTAPS - 1) * config->channels;
    state->tail = (float *)calloc(tail_elements, sizeof(float));
    if (!state->tail) {
        free(state);
        return result;
    }
    /* Tail is zero-initialized by calloc */

    /* NO COEFFICIENT COMPUTATION - use pre-computed static array */

    /* Set output dimensions (matches input) */
    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

/* Process one window of data */
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) {
        return;
    }

    fir_bandpass_state_t *s = (fir_bandpass_state_t *)handle;
    const float *in = (const float *)input;
    float *out = (float *)output;

    
    const size_t tail_len = FIR_NUMTAPS - 1;
    
    /* Process each channel independently */
    for (uint32_t ch = 0; ch < s->channels; ch++) {
        /* Process each sample in the window */
        for (uint32_t t = 0; t < s->window_length; t++) {
            double sum = 0.0;

            /* Convolution: y[n] = sum(k=0 to numtaps-1) b[k] * x[n-k] */
            for (uint32_t k = 0; k < FIR_NUMTAPS; k++) {
                float x_val;

                /* Get x[n-k]: use tail for history, current window for recent */
                if (k <= t) {
                    /* Use current window: x[t-k] */
                    const float x_raw = in[(t - k) * s->channels + ch];
                    x_val = (x_raw == x_raw) ? x_raw : 0.0f;  /* NaN handling */
                } else {
                    /* Use tail buffer: need sample from before current window */
                    /* For k > t, we need x[t-k] where (t-k) < 0 */
                    /* Tail buffer index: tail_len - (k - t) */
                    const size_t tail_idx = tail_len - (k - t);
                    if (tail_idx < tail_len) {
                        const float tail_raw = s->tail[tail_idx * s->channels + ch];
                        x_val = (tail_raw == tail_raw) ? tail_raw : 0.0f;  /* NaN handling */
                    } else {
                        /* Should not happen, but handle gracefully */
                        x_val = 0.0f;
                    }
                }

                /* Use pre-computed coefficient (already double precision)
                 * Accumulate in double precision for better accuracy */
                sum += FIR_COEFFICIENTS[k] * (double)x_val;
            }

            /* Convert final result to float - ensure consistent rounding */
            out[t * s->channels + ch] = (float)sum;
        }
    }

    /* Update tail buffer once per window (after all channels processed) */
    /* The tail should contain the last (FIR_NUMTAPS-1) samples BEFORE the start
     * of the next window. Since windows overlap by (window_length - hop_samples),
     * we need to:
     * 1. Shift existing tail left by hop_samples (discard oldest hop_samples)
     * 2. Append the first hop_samples of current window to the right
     * This ensures the tail contains the correct samples BEFORE the next window starts.
     */


    /* Update tail buffer in-place (no heap allocation, per ABI requirement) */
    /* Always maintain the most recent tail_len samples before the current window */
    if (s->hop_samples < tail_len) {
        /* Overlapping case: shift existing tail left by hop_samples and append new samples */
        const size_t shift_amount = s->hop_samples;
        const size_t keep_amount = tail_len - shift_amount;

        /* Shift kept samples to the beginning of the tail buffer */
        /* Move tail[shift_amount:tail_len] -> tail[0:keep_amount] */
        memmove(s->tail, &s->tail[shift_amount * s->channels],
                keep_amount * s->channels * sizeof(float));

        /* Append new samples to the end: window[0:min(hop_samples, window_length)] -> tail[keep_amount:keep_amount+available] */
        /* Clamp to window_length to prevent out-of-bounds reads */
        const size_t samples_to_copy = (s->hop_samples < s->window_length) ? s->hop_samples : s->window_length;
        for (size_t sample = 0; sample < samples_to_copy; sample++) {
            for (uint32_t ch = 0; ch < s->channels; ch++) {
                const uint32_t src_idx = sample * s->channels + ch;
                const float tail_input = in[src_idx];
                /* Sanitize NaNs when writing to tail buffer */
                s->tail[(keep_amount + sample) * s->channels + ch] =
                    (tail_input == tail_input) ? tail_input : 0.0f;  /* NaN handling */
            }
        }
        /* If samples_to_copy < hop_samples, remaining tail positions stay zero (from calloc init) */
    } else {
        /* hop_samples >= tail_len: replace entire tail with samples from current window */
        if (s->window_length >= tail_len) {
            if (s->hop_samples < s->window_length) {
                /* Overlapping windows with large hop: tail should end at hop_samples */
                /* Copy window[hop_samples - tail_len:hop_samples] -> tail[0:tail_len] */
                /* This ensures tail contains samples immediately preceding the next window start */
                const size_t src_start_sample = s->hop_samples - tail_len;
                for (size_t sample = 0; sample < tail_len; sample++) {
                    for (uint32_t ch = 0; ch < s->channels; ch++) {
                        const uint32_t src_idx = (src_start_sample + sample) * s->channels + ch;
                        const float tail_input = in[src_idx];
                        /* Sanitize NaNs when writing to tail buffer */
                        s->tail[sample * s->channels + ch] =
                            (tail_input == tail_input) ? tail_input : 0.0f;  /* NaN handling */
                    }
                }
            } else {
                /* hop_samples >= window_length: windows don't overlap */
                /* Copy window[window_length - tail_len:window_length] -> tail[0:tail_len] */
                const size_t src_start_sample = s->window_length - tail_len;
                for (size_t sample = 0; sample < tail_len; sample++) {
                    for (uint32_t ch = 0; ch < s->channels; ch++) {
                        const uint32_t src_idx = (src_start_sample + sample) * s->channels + ch;
                        const float tail_input = in[src_idx];
                        /* Sanitize NaNs when writing to tail buffer */
                        s->tail[sample * s->channels + ch] =
                            (tail_input == tail_input) ? tail_input : 0.0f;  /* NaN handling */
                    }
                }
            }
        } else {
            /* Short window case: copy all available samples, pad remainder with zeros */
            /* Copy window[0:window_length] -> tail[0:window_length] */
            for (size_t sample = 0; sample < s->window_length; sample++) {
                for (uint32_t ch = 0; ch < s->channels; ch++) {
                    const uint32_t src_idx = sample * s->channels + ch;
                    const float tail_input = in[src_idx];
                    /* Sanitize NaNs when writing to tail buffer */
                    s->tail[sample * s->channels + ch] =
                        (tail_input == tail_input) ? tail_input : 0.0f;  /* NaN handling */
                }
            }
            /* Remaining tail[window_length:tail_len] is already zero from calloc init */
        }
    }

}

/* Teardown plugin instance */
void cortex_teardown(void *handle) {
    if (!handle) {
        return;
    }
    
    fir_bandpass_state_t *s = (fir_bandpass_state_t *)handle;
    free(s->tail);
    free(s);
}

