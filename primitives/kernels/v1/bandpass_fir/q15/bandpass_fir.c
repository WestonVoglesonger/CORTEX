/*
 * FIR Bandpass Filter Plugin — Q15 data type
 *
 * 129-tap FIR bandpass filter (8-30 Hz @ 160 Hz) using Q15 I/O.
 * Coefficients quantized to Q15 at init time.
 * Tail buffer stores Q15 int16_t values.
 *
 * Accumulation in int64_t:
 *   129 taps × max(Q15×Q15) = 129 × (32767²) = 129 × 1,073,676,289 ≈ 138.5 billion
 *   — exceeds int32_t, requires int64_t.
 *
 * ABI Version: 2
 * Data Type: Q15 (signed Q1.15 fixed-point, int16_t)
 */

#include "cortex_plugin.h"
#include "cortex_q15.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#undef CORTEX_ABI_VERSION
#define CORTEX_ABI_VERSION 2u

#define FIR_NUMTAPS 129

/* Pre-computed FIR coefficients for 129-tap bandpass (8-30 Hz @ 160 Hz, Hamming) */
/* Same coefficients as f32 variant — quantized to Q15 at init time */
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

typedef struct {
    uint32_t channels;
    uint32_t window_length;
    uint32_t hop_samples;
    int16_t *tail;       /* [(FIR_NUMTAPS-1) × channels] Q15 tail buffer */
    int16_t coeff_q15[FIR_NUMTAPS];  /* Coefficients quantized to Q15 */
} bandpass_fir_q15_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_Q15) return result;

    bandpass_fir_q15_state_t *state = calloc(1, sizeof(bandpass_fir_q15_state_t));
    if (!state) return result;

    state->channels = config->channels;
    state->window_length = config->window_length_samples;
    state->hop_samples = config->hop_samples;

    /* Allocate Q15 tail buffer */
    const size_t tail_elements = (FIR_NUMTAPS - 1) * config->channels;
    state->tail = (int16_t *)calloc(tail_elements, sizeof(int16_t));
    if (!state->tail) {
        free(state);
        return result;
    }

    /* Quantize coefficients to Q15 at init time */
    for (int i = 0; i < FIR_NUMTAPS; i++) {
        state->coeff_q15[i] = cortex_float_to_q15((float)FIR_COEFFICIENTS[i]);
    }

    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    bandpass_fir_q15_state_t *s = (bandpass_fir_q15_state_t *)handle;
    const int16_t *in = (const int16_t *)input;
    int16_t *out = (int16_t *)output;

    const size_t tail_len = FIR_NUMTAPS - 1;

    /* Process each channel independently */
    for (uint32_t ch = 0; ch < s->channels; ch++) {
        for (uint32_t t = 0; t < s->window_length; t++) {
            int64_t acc = 0;

            /* Convolution: y[n] = sum(k=0..numtaps-1) b[k] * x[n-k] */
            for (uint32_t k = 0; k < FIR_NUMTAPS; k++) {
                int16_t x_val;

                if (k <= t) {
                    /* Use current window */
                    x_val = in[(t - k) * s->channels + ch];
                } else {
                    /* Use tail buffer */
                    size_t tail_idx = tail_len - (k - t);
                    if (tail_idx < tail_len) {
                        x_val = s->tail[tail_idx * s->channels + ch];
                    } else {
                        x_val = 0;
                    }
                }

                /* Q15 × Q15 → Q30, accumulate in int64 */
                acc += (int64_t)s->coeff_q15[k] * (int64_t)x_val;
            }

            /* Round-to-nearest: add 0.5 in Q30, shift >>15 to get Q15 */
            acc += (1 << 14);
            int32_t result = (int32_t)(acc >> 15);

            /* Saturate to Q15 */
            if (result > 32767) result = 32767;
            else if (result < -32768) result = -32768;

            out[t * s->channels + ch] = (int16_t)result;
        }
    }

    /* Update tail buffer (same logic as f32 variant, but with int16_t) */
    if (s->hop_samples < tail_len) {
        const size_t shift_amount = s->hop_samples;
        const size_t keep_amount = tail_len - shift_amount;

        memmove(s->tail, &s->tail[shift_amount * s->channels],
                keep_amount * s->channels * sizeof(int16_t));

        const size_t samples_to_copy = (s->hop_samples < s->window_length)
                                        ? s->hop_samples : s->window_length;
        for (size_t sample = 0; sample < samples_to_copy; sample++) {
            for (uint32_t ch = 0; ch < s->channels; ch++) {
                s->tail[(keep_amount + sample) * s->channels + ch] =
                    in[sample * s->channels + ch];
            }
        }
    } else {
        if (s->window_length >= tail_len) {
            size_t src_start;
            if (s->hop_samples < s->window_length) {
                src_start = s->hop_samples - tail_len;
            } else {
                src_start = s->window_length - tail_len;
            }
            for (size_t sample = 0; sample < tail_len; sample++) {
                for (uint32_t ch = 0; ch < s->channels; ch++) {
                    s->tail[sample * s->channels + ch] =
                        in[(src_start + sample) * s->channels + ch];
                }
            }
        } else {
            for (size_t sample = 0; sample < s->window_length; sample++) {
                for (uint32_t ch = 0; ch < s->channels; ch++) {
                    s->tail[sample * s->channels + ch] =
                        in[sample * s->channels + ch];
                }
            }
        }
    }
}

void cortex_teardown(void *handle) {
    if (!handle) return;
    bandpass_fir_q15_state_t *s = (bandpass_fir_q15_state_t *)handle;
    free(s->tail);
    free(s);
}
