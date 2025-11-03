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

#define CORTEX_ABI_VERSION 1u
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
    float *tail;  /* [(FIR_NUMTAPS-1) × channels] tail buffer */
} fir_bandpass_state_t;

/* Get plugin metadata */
cortex_plugin_info_t cortex_get_info(void) {
    cortex_plugin_info_t info = {0};
    
    info.name = "fir_bandpass";
    info.description = "Linear-phase FIR bandpass filter (8-30 Hz, 129 taps)";
    info.version = "1.0.0";
    info.supported_dtypes = CORTEX_DTYPE_FLOAT32_MASK;
    
    info.input_window_length_samples = 160;  /* Default from spec */
    info.input_channels = 64;                 /* Default from dataset spec */
    info.output_window_length_samples = 160;
    info.output_channels = 64;
    
    /* State size: struct + tail buffer only (coefficients are static) */
    const size_t tail_size = (FIR_NUMTAPS - 1) * 64; /* Default channels */
    info.state_bytes = sizeof(fir_bandpass_state_t) + (tail_size * sizeof(float));
    info.workspace_bytes = 0;
    
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

    /* Validate sample rate matches coefficient design (optional warning) */
    if (config->sample_rate_hz != (uint32_t)FIR_SAMPLE_RATE_HZ) {
        /* Coefficients designed for 160 Hz - warn but allow */
        fprintf(stderr, "[fir_bandpass] warning: coefficients designed for %.0f Hz, "
                "config has %u Hz\n", FIR_SAMPLE_RATE_HZ, config->sample_rate_hz);
    }

    /* Allocate state structure */
    fir_bandpass_state_t *state = (fir_bandpass_state_t *)calloc(1, sizeof(fir_bandpass_state_t));
    if (!state) {
        return NULL;
    }

    /* Store config values */
    state->channels = config->channels;  /* Use from config */
    state->window_length = config->window_length_samples;  /* Use from config */

    /* Allocate tail buffer: (FIR_NUMTAPS-1) × channels */
    const size_t tail_elements = (FIR_NUMTAPS - 1) * config->channels;
    state->tail = (float *)calloc(tail_elements, sizeof(float));
    if (!state->tail) {
        free(state);
        return NULL;
    }
    /* Tail is zero-initialized by calloc */

    /* NO COEFFICIENT COMPUTATION - use pre-computed static array */

    return state;
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
        
        /* Update tail: copy last (FIR_NUMTAPS-1) samples from current window */
        /* Sanitize NaNs when writing to tail buffer to prevent propagation */
        for (uint32_t i = 0; i < tail_len; i++) {
            const uint32_t src_idx = (s->window_length - tail_len + i) * s->channels + ch;
            const float tail_input = in[src_idx];
            s->tail[i * s->channels + ch] = (tail_input == tail_input) ? tail_input : 0.0f;  /* NaN handling */
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

