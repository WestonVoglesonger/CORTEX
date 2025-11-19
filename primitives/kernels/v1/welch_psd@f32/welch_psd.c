#include "cortex_plugin.h"
#include "kiss_fft.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define DEFAULT_N_FFT 256
#define DEFAULT_N_OVERLAP 128

typedef struct {
  int n_fft;
  int n_overlap;
  int n_step;
  float *window;

  /* Runtime config */
  uint32_t channels;
  uint32_t window_length_samples;

  /* Pre-computed scaling factor */
  float energy_scale;

  /* FFT State */
  kiss_fft_cfg fft_cfg;
  kiss_fft_cpx *fft_in;
  kiss_fft_cpx *fft_out;

  /* Accumulator for averaging */
  float *psd_sum;
  int segment_count;
} welch_psd_state_t;

/* Window function generator */
static void generate_hann_window(float *window, int size) {
  for (int i = 0; i < size; i++) {
    window[i] = 0.5f * (1.0f - cosf(2.0f * M_PI * i / size));
  }
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
  cortex_init_result_t result = {0};

  if (!config)
    return result;
  if (config->abi_version != CORTEX_ABI_VERSION)
    return result;
  if (config->struct_size < sizeof(cortex_plugin_config_t))
    return result;
  if (config->dtype != CORTEX_DTYPE_FLOAT32)
    return result;

  welch_psd_state_t *ctx =
      (welch_psd_state_t *)calloc(1, sizeof(welch_psd_state_t));
  if (!ctx)
    return result;

  /* Parse config */
  /* Adjust defaults if window length is smaller */
  if (config->window_length_samples > 0 &&
      config->window_length_samples < (uint32_t)DEFAULT_N_FFT) {
    ctx->n_fft = config->window_length_samples;
    ctx->n_overlap = ctx->n_fft / 2;
  } else {
    ctx->n_fft = DEFAULT_N_FFT;
    ctx->n_overlap = DEFAULT_N_OVERLAP;
  }

  /* Store runtime config */
  ctx->channels = config->channels;
  ctx->window_length_samples = config->window_length_samples;

  /* Simple config parsing (in a real implementation, use a JSON parser or
   * similar) */
  /* For now, we'll rely on defaults or simple string searching if needed,
     but the harness passes a raw string. We'll assume defaults for this MVP
     unless we parse the JSON string. */

  /* TODO: Parse config->config_json to override defaults */

  ctx->n_step = ctx->n_fft - ctx->n_overlap;
  if (ctx->n_step <= 0) {
    /* Invalid config: overlap must be less than FFT size */
    cortex_teardown(ctx);
    return result;
  }

  /* Allocate resources */
  ctx->window = (float *)malloc(sizeof(float) * ctx->n_fft);
  ctx->fft_in = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * ctx->n_fft);
  ctx->fft_out = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * ctx->n_fft);
  ctx->psd_sum = (float *)calloc(ctx->n_fft / 2 + 1, sizeof(float));
  ctx->fft_cfg = kiss_fft_alloc(ctx->n_fft, 0, NULL, NULL);

  if (!ctx->window || !ctx->fft_in || !ctx->fft_out || !ctx->psd_sum ||
      !ctx->fft_cfg) {
    /* Defensive cleanup - free(NULL) is safe */
    free(ctx->window);
    free(ctx->fft_in);
    free(ctx->fft_out);
    free(ctx->psd_sum);
    if (ctx->fft_cfg)
      kiss_fft_free(ctx->fft_cfg);
    free(ctx);
    return result;
  }

  generate_hann_window(ctx->window, ctx->n_fft);

  /* Pre-compute window energy scale factor */
  /* Standard Welch: Scale by 1 / (Fs * Sum(w^2)) */
  /* For one-sided PSD, we multiply non-DC/Nyquist terms by 2. */
  /* We'll store the base scale: 1.0 / Sum(w^2) (Assuming Fs=1.0 for relative)
   */
  /* Use double for energy calculation to preserve precision */
  double win_energy = 0.0;
  for (int i = 0; i < ctx->n_fft; i++) {
    win_energy += (double)ctx->window[i] * (double)ctx->window[i];
  }

  /* Scale by 1 / (Fs * Sum(w^2)) */
  double fs =
      (config->sample_rate_hz > 0) ? (double)config->sample_rate_hz : 1.0;
  ctx->energy_scale = (float)(1.0 / (fs * win_energy));

  result.handle = ctx;
  result.output_window_length_samples = ctx->n_fft / 2 + 1;
  result.output_channels = config->channels;

  return result;
}

void cortex_process(void *handle, const void *input, void *output) {
  if (!handle || !input || !output)
    return;

  welch_psd_state_t *ctx = (welch_psd_state_t *)handle;
  const float *in_data = (const float *)input;
  float *out_data = (float *)output;

  /*
   * Input is interleaved: [s0c0, s0c1, ... s0c63, s1c0...]
   * We process each channel independently.
   */

  int channels = ctx->channels;
  int input_samples = ctx->window_length_samples;

  /* Check bounds */
  if (input_samples < ctx->n_fft) {
    /* Input too short for FFT */
    memset(out_data, 0, sizeof(float) * (ctx->n_fft / 2 + 1) * channels);
    return;
  }

  for (int c = 0; c < channels; c++) {
    /* Reset accumulator for this channel */
    memset(ctx->psd_sum, 0, sizeof(float) * (ctx->n_fft / 2 + 1));
    ctx->segment_count = 0;

    int cursor = 0;
    while (cursor + ctx->n_fft <= input_samples) {
      /* 1. Copy and Window (Strided Read) */
      for (int i = 0; i < ctx->n_fft; i++) {
        /* Input index: (cursor + i) * channels + c */
        /* Use size_t to prevent overflow */
        size_t sample_idx = (size_t)cursor + i;
        size_t idx = sample_idx * channels + c;

        float sample = in_data[idx];

        /* Handle NaN */
        if (isnan(sample)) {
          sample = 0.0f;
        }

        ctx->fft_in[i].r = sample * ctx->window[i];
        ctx->fft_in[i].i = 0.0f;
      }

      /* 2. FFT */
      kiss_fft(ctx->fft_cfg, ctx->fft_in, ctx->fft_out);

      /* 3. Periodogram */
      /* One-sided PSD scaling:
         - DC (0) and Nyquist (N/2): Scale * |X|^2
         - Others: 2 * Scale * |X|^2
      */

      for (int i = 0; i <= ctx->n_fft / 2; i++) {
        float mag_sq = ctx->fft_out[i].r * ctx->fft_out[i].r +
                       ctx->fft_out[i].i * ctx->fft_out[i].i;

        if (i == 0 || i == ctx->n_fft / 2) {
          ctx->psd_sum[i] += mag_sq * ctx->energy_scale;
        } else {
          ctx->psd_sum[i] += mag_sq * ctx->energy_scale * 2.0f;
        }
      }

      ctx->segment_count++;
      cursor += ctx->n_step;
    }

    /* 4. Average and Write Output (Strided Write) */
    if (ctx->segment_count > 0) {
      for (int i = 0; i <= ctx->n_fft / 2; i++) {
        /* Output index: i * channels + c */
        size_t out_idx = (size_t)i * channels + c;
        out_data[out_idx] = ctx->psd_sum[i] / ctx->segment_count;
      }
    } else {
      for (int i = 0; i <= ctx->n_fft / 2; i++) {
        size_t out_idx = (size_t)i * channels + c;
        out_data[out_idx] = 0.0f;
      }
    }
  }
}

void cortex_teardown(void *handle) {
  welch_psd_state_t *ctx = (welch_psd_state_t *)handle;
  if (ctx) {
    free(ctx->window);
    free(ctx->fft_in);
    free(ctx->fft_out);
    free(ctx->psd_sum);
    if (ctx->fft_cfg)
      kiss_fft_free(ctx->fft_cfg);
    free(ctx);
  }
}
