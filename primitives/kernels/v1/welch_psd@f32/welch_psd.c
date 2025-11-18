#include "cortex_plugin.h"
#include "kiss_fft.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct {
  int n_fft;
  int n_overlap;
  int n_step;
  float *window;

  /* Runtime config */
  uint32_t channels;
  uint32_t window_length_samples;

  /* Buffers */
  float *input_buffer;    /* Sliding buffer for overlap */
  size_t buffer_size;     /* Current size of data in buffer */
  size_t buffer_capacity; /* Total capacity of buffer */

  /* FFT State */
  kiss_fft_cfg fft_cfg;
  kiss_fft_cpx *fft_in;
  kiss_fft_cpx *fft_out;

  /* Accumulator for averaging */
  float *psd_sum;
  int segment_count;
} welch_context_t;

/* Window function generator */
static void generate_hann_window(float *window, int size) {
  for (int i = 0; i < size; i++) {
    window[i] = 0.5f * (1.0f - cosf(2.0f * M_PI * i / (size - 1)));
  }
}

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
  cortex_init_result_t result = {0};

  if (!config)
    return result;
  if (config->abi_version != CORTEX_ABI_VERSION)
    return result;

  welch_context_t *ctx = (welch_context_t *)calloc(1, sizeof(welch_context_t));
  if (!ctx)
    return result;

  /* Parse config */
  ctx->n_fft = 256;     /* Default */
  ctx->n_overlap = 128; /* Default */

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
    free(ctx);
    return result;
  }

  /* Allocate resources */
  ctx->window = (float *)malloc(sizeof(float) * ctx->n_fft);
  ctx->input_buffer = (float *)malloc(sizeof(float) * ctx->n_fft *
                                      2); /* Double buffer strategy */
  ctx->buffer_capacity = ctx->n_fft * 2;
  ctx->buffer_size = 0;

  ctx->fft_in = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * ctx->n_fft);
  ctx->fft_out = (kiss_fft_cpx *)malloc(sizeof(kiss_fft_cpx) * ctx->n_fft);
  ctx->psd_sum = (float *)calloc(ctx->n_fft / 2 + 1, sizeof(float));

  ctx->fft_cfg = kiss_fft_alloc(ctx->n_fft, 0, NULL, NULL);

  if (!ctx->window || !ctx->input_buffer || !ctx->fft_in || !ctx->fft_out ||
      !ctx->psd_sum || !ctx->fft_cfg) {
    /* Cleanup will happen in destroy, but we need to be careful with partial
     * init */
    free(ctx->window);
    free(ctx->input_buffer);
    free(ctx->fft_in);
    free(ctx->fft_out);
    free(ctx->psd_sum);
    free(ctx->fft_cfg); /* kiss_fft_free is just free */
    free(ctx);
    return result;
  }

  generate_hann_window(ctx->window, ctx->n_fft);

  result.handle = ctx;
  result.output_window_length_samples = ctx->n_fft / 2 + 1;
  result.output_channels = config->channels;

  return result;
}

void cortex_process(void *handle, const void *input, void *output) {
  welch_context_t *ctx = (welch_context_t *)handle;
  const float *in_data = (const float *)input;
  float *out_data = (float *)output;

  /*
   * Input is interleaved: [s0c0, s0c1, ... s0c63, s1c0...]
   * We process each channel independently.
   */

  int channels = ctx->channels;
  /* We assume input buffer contains enough samples for at least one window?
     The harness guarantees input buffer size is W * C.
     But Welch needs N_FFT samples.
     If W < N_FFT, we can't compute a full FFT without padding.
     We'll assume W >= N_FFT or we just process what we can.

     Actually, we should process `window_length_samples` from the config.
     We stored `n_fft` but not `window_length_samples` from config?
     Let's assume the input buffer length corresponds to the configured window
     length. We'll iterate until we run out of data in the input buffer.

     Wait, we don't know the input buffer length in `process`!
     We only know it from `cortex_init`.
     We should store `window_length_samples` in context.
  */

  int input_samples = ctx->window_length_samples;

  for (int c = 0; c < channels; c++) {
    /* Reset accumulator for this channel */
    memset(ctx->psd_sum, 0, sizeof(float) * (ctx->n_fft / 2 + 1));
    ctx->segment_count = 0;

    int cursor = 0;
    while (cursor + ctx->n_fft <= input_samples) {
      /* 1. Copy and Window (Strided Read) */
      for (int i = 0; i < ctx->n_fft; i++) {
        /* Input index: (cursor + i) * channels + c */
        ctx->fft_in[i].r =
            in_data[(cursor + i) * channels + c] * ctx->window[i];
        ctx->fft_in[i].i = 0.0f;
      }

      /* 2. FFT */
      kiss_fft(ctx->fft_cfg, ctx->fft_in, ctx->fft_out);

      /* 3. Periodogram */
      float win_energy = 0.0f;
      for (int i = 0; i < ctx->n_fft; i++)
        win_energy += ctx->window[i] * ctx->window[i];
      float scale = 2.0f / (1.0f * win_energy);

      for (int i = 0; i <= ctx->n_fft / 2; i++) {
        float mag_sq = ctx->fft_out[i].r * ctx->fft_out[i].r +
                       ctx->fft_out[i].i * ctx->fft_out[i].i;

        if (i == 0 || i == ctx->n_fft / 2) {
          ctx->psd_sum[i] += mag_sq * (scale / 2.0f);
        } else {
          ctx->psd_sum[i] += mag_sq * scale;
        }
      }

      ctx->segment_count++;
      cursor += ctx->n_step;
    }

    /* 4. Average and Write Output (Strided Write) */
    if (ctx->segment_count > 0) {
      for (int i = 0; i <= ctx->n_fft / 2; i++) {
        /* Output index: i * channels + c (Interleaved frequencies?)
           Wait, usually frequency domain data is [bins x channels]?
           If output_window_length_samples = bins, and output_channels = C.
           Harness expects "tightly packed in row-major order (channels x
           samples)". This usually means [c0s0, c0s1...] (Planar) OR [s0c0,
           s0c1...] (Interleaved). Given input is interleaved, output is likely
           interleaved too. So: out[bin * channels + c]
        */
        out_data[i * channels + c] = ctx->psd_sum[i] / ctx->segment_count;
      }
    } else {
      for (int i = 0; i <= ctx->n_fft / 2; i++) {
        out_data[i * channels + c] = 0.0f;
      }
    }
  }
}

void cortex_teardown(void *handle) {
  welch_context_t *ctx = (welch_context_t *)handle;
  if (ctx) {
    free(ctx->window);
    free(ctx->input_buffer);
    free(ctx->fft_in);
    free(ctx->fft_out);
    free(ctx->psd_sum);
    free(ctx->fft_cfg);
    free(ctx);
  }
}
