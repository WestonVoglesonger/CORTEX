/*
 * hello_kernel.c - Minimal Kernel SDK example
 *
 * Demonstrates the minimal required implementation of the CORTEX kernel ABI v3:
 * - cortex_init()
 * - cortex_process()
 * - cortex_teardown()
 *
 * This kernel implements a simple passthrough (identity function) with
 * printf debugging to show the SDK interface in action.
 */

#define _POSIX_C_SOURCE 200809L

#include "cortex_plugin.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Kernel state (allocated in init, freed in teardown) */
typedef struct {
    uint32_t sample_rate_hz;
    uint32_t window_length;
    uint32_t hop_samples;
    uint32_t channels;
    uint32_t process_count;
} hello_state_t;

/*
 * cortex_init - Initialize kernel
 *
 * Called once at startup. Allocate resources, validate configuration.
 * MUST NOT allocate on subsequent cortex_process() calls.
 *
 * Returns cortex_init_result_t with handle and output dimensions.
 * Returns {NULL, 0, 0, 0} on error.
 */
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    cortex_init_result_t result = {0};

    /* ABI version check (required for all kernels) */
    if (!config) return result;
    if (config->abi_version != CORTEX_ABI_VERSION) {
        fprintf(stderr, "[hello] ABI mismatch: got %u, expected %u\n",
                config->abi_version, CORTEX_ABI_VERSION);
        return result;
    }
    if (config->struct_size < sizeof(cortex_plugin_config_t)) return result;

    /* Only support float32 for this example */
    if (config->dtype != CORTEX_DTYPE_FLOAT32) {
        fprintf(stderr, "[hello] Unsupported dtype: %u (expected FLOAT32)\n",
                config->dtype);
        return result;
    }

    /* Allocate state */
    hello_state_t *state = (hello_state_t *)calloc(1, sizeof(hello_state_t));
    if (!state) {
        fprintf(stderr, "[hello] Failed to allocate state\n");
        return result;
    }

    /* Store configuration */
    state->sample_rate_hz = config->sample_rate_hz;
    state->window_length = config->window_length_samples;
    state->hop_samples = config->hop_samples;
    state->channels = config->channels;
    state->process_count = 0;

    printf("[hello] Initialized successfully\n");
    printf("  Sample rate: %u Hz\n", state->sample_rate_hz);
    printf("  Window: %u samples × %u channels\n",
           state->window_length, state->channels);
    printf("  Hop: %u samples\n", state->hop_samples);

    /* Return handle and output dimensions */
    result.handle = state;
    result.output_window_length_samples = config->window_length_samples;
    result.output_channels = config->channels;
    result.capabilities = 0;  /* No special capabilities */

    return result;
}

/*
 * cortex_process - Process one window of data
 *
 * HERMETIC CONSTRAINT: No allocations, no I/O, no blocking syscalls.
 * This function is called in the hot path and must be deterministic.
 *
 * Parameters:
 *  - handle: Opaque state pointer returned by cortex_init()
 *  - input: Pointer to input buffer (window_length × channels samples)
 *  - output: Pointer to output buffer (same size)
 */
void cortex_process(void *handle, const void *input, void *output) {
    if (!handle || !input || !output) return;

    hello_state_t *state = (hello_state_t *)handle;

    const float *in = (const float *)input;
    float *out = (float *)output;

    /* Calculate buffer size */
    size_t total_samples = (size_t)state->window_length * state->channels;

    /* Copy input to output (identity/passthrough) */
    memcpy(out, in, total_samples * sizeof(float));

    state->process_count++;

    /* Only print first window to avoid spam */
    if (state->process_count == 1) {
        printf("[hello] Processed first window: %zu samples\n", total_samples);
        printf("  First input sample: %.6f\n", in[0]);
        printf("  First output sample: %.6f\n", out[0]);
    }
}

/*
 * cortex_teardown - Cleanup resources
 *
 * Called once at shutdown. Free all resources allocated in init.
 */
void cortex_teardown(void *handle) {
    if (!handle) return;

    hello_state_t *state = (hello_state_t *)handle;
    printf("[hello] Tearing down after %u process calls\n", state->process_count);
    free(state);
}

/*
 * Test harness (when compiled as standalone executable)
 */
#ifdef BUILD_STANDALONE

int main(void) {
    printf("=== Hello Kernel SDK Example ===\n\n");

    /* Setup configuration */
    cortex_plugin_config_t config = {
        .abi_version = CORTEX_ABI_VERSION,
        .struct_size = sizeof(cortex_plugin_config_t),
        .sample_rate_hz = 160,
        .window_length_samples = 160,
        .hop_samples = 80,
        .channels = 4,
        .dtype = CORTEX_DTYPE_FLOAT32,
        .allow_in_place = 0,
        .reserved0 = {0},
        .kernel_params = NULL,
        .kernel_params_size = 0,
        .calibration_state = NULL,
        .calibration_state_size = 0
    };

    /* Initialize kernel */
    cortex_init_result_t init_result = cortex_init(&config);
    if (!init_result.handle) {
        fprintf(stderr, "ERROR: cortex_init failed\n");
        return 1;
    }
    printf("\n");

    /* Allocate test data */
    size_t window_size = config.window_length_samples * config.channels;
    float *input = (float *)calloc(window_size, sizeof(float));
    float *output = (float *)calloc(window_size, sizeof(float));

    if (!input || !output) {
        fprintf(stderr, "ERROR: Failed to allocate test buffers\n");
        cortex_teardown(init_result.handle);
        free(input);
        free(output);
        return 1;
    }

    /* Fill input with test pattern */
    for (size_t i = 0; i < window_size; i++) {
        input[i] = (float)i * 0.01f;
    }

    /* Process window */
    cortex_process(init_result.handle, input, output);
    printf("\n");

    /* Verify output matches input (identity function) */
    int match_count = 0;
    for (size_t i = 0; i < window_size; i++) {
        if (input[i] == output[i]) {
            match_count++;
        }
    }

    printf("Verification:\n");
    printf("  Output dimensions: %u samples × %u channels\n",
           init_result.output_window_length_samples,
           init_result.output_channels);
    printf("  Matching samples: %d/%zu (%.1f%%)\n",
           match_count, window_size,
           100.0 * match_count / window_size);

    /* Cleanup */
    printf("\n");
    cortex_teardown(init_result.handle);
    free(input);
    free(output);

    if (match_count == (int)window_size) {
        printf("\n✓ Test PASSED\n");
        return 0;
    } else {
        printf("\n✗ Test FAILED\n");
        return 1;
    }
}

#endif /* BUILD_STANDALONE */
