/**
 * @file noop.c
 * @brief No-op (identity function) kernel for measuring harness dispatch overhead
 *
 * This kernel performs minimal computation (identity function: output = input)
 * to isolate and measure the overhead introduced by the CORTEX harness itself
 * (timing brackets, function call overhead, data copying if not in-place).
 *
 * Purpose: Empirical measurement of harness overhead for validation of
 * measurement methodology claims.
 */

#include "cortex_plugin.h"
#include <string.h>
#include <stdlib.h>

#define CORTEX_ABI_VERSION 2u

typedef struct {
    uint32_t window_length;
    uint32_t channels;
} noop_state_t;

/**
 * Initialize no-op kernel state
 */
cortex_init_result_t cortex_init(const cortex_plugin_config_t* config) {
    cortex_init_result_t result = {0};

    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) return result;
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;
    if (config->dtype != CORTEX_DTYPE_FLOAT32) return result;

    noop_state_t* state = (noop_state_t*)calloc(1, sizeof(noop_state_t));
    if (!state) return result;

    state->window_length = config->window_length_samples;
    state->channels = config->channels;

    // Output shape = input shape for identity function
    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;

    return result;
}

/**
 * Process window: Identity function (output = input)
 *
 * This is the minimal computational kernel - just copies input to output.
 * Any measured latency represents harness overhead + memory copy time.
 */
void cortex_process(void* handle, const void* input, void* output) {
    if (!handle || !input || !output) return;

    const noop_state_t* state = (const noop_state_t*)handle;
    const size_t total_samples = (size_t)state->window_length * state->channels;

    const float* in = (const float*)input;
    float* out = (float*)output;

    // Identity function: output = input
    // If allow_in_place=true, this may be skipped by harness
    // If allow_in_place=false, this measures copy overhead
    memcpy(out, in, total_samples * sizeof(float));
}

/**
 * Cleanup state
 */
void cortex_teardown(void* handle) {
    if (handle) {
        free(handle);
    }
}
