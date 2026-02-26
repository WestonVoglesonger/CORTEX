/*
 * No-op (identity function) kernel for Q15 data type.
 *
 * Measures harness dispatch overhead with Q15 (int16_t) buffers.
 * Output = input (memcpy of W*C*sizeof(int16_t) bytes).
 *
 * ABI Version: 2
 * Data Type: Q15 (signed Q1.15 fixed-point, int16_t)
 */

#include "cortex_plugin.h"
#include <string.h>
#include <stdlib.h>

#undef CORTEX_ABI_VERSION
#define CORTEX_ABI_VERSION 2u

typedef struct {
    uint32_t window_length;
    uint32_t channels;
} noop_q15_state_t;

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_Q15) return result;

    noop_q15_state_t *state = (noop_q15_state_t *)calloc(1, sizeof(noop_q15_state_t));
    if (!state) return result;

    state->window_length = config->window_length_samples;
    state->channels = config->channels;

    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    const noop_q15_state_t *state = (const noop_q15_state_t *)handle;
    const size_t total_bytes = (size_t)state->window_length * state->channels * sizeof(int16_t);

    memcpy(output, input, total_bytes);
}

void cortex_teardown(void *handle) {
    if (handle) {
        free(handle);
    }
}
