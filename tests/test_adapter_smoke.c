/*
 * Adapter Smoke Test
 *
 * End-to-end test: Spawn native@loopback adapter and execute one window.
 * Validates full protocol flow works (handshake + window execution).
 */

#define _POSIX_C_SOURCE 200809L

#include "../src/engine/harness/device/device_comm.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    printf("=== Adapter Smoke Test ===\n\n");

    const char *adapter_path = "primitives/adapters/v1/native@loopback/cortex_adapter_native_loopback";
    const char *spec_uri = "primitives/kernels/v1/noop@f32";  /* Full path, not just "noop@f32" */
    const char *plugin_params = "";

    const uint32_t sample_rate_hz = 160;
    const uint32_t window_samples = 160;
    const uint32_t hop_samples = 80;
    const uint32_t channels = 64;

    /* Initialize device (spawn adapter + handshake) */
    printf("1. Spawning adapter and performing handshake...\n");

    cortex_device_init_result_t result;
    int ret = device_comm_init(
        adapter_path,
        NULL,  /* transport_config (NULL = default "local://") */
        spec_uri,
        plugin_params,
        sample_rate_hz,
        window_samples,
        hop_samples,
        channels,
        NULL,  /* No calibration state */
        0,
        &result
    );

    if (ret < 0) {
        printf("ERROR: device_comm_init failed with code %d\n", ret);
        return 1;
    }

    printf("   ✓ Adapter spawned and ready\n\n");

    /* Execute one window */
    printf("2. Executing test window (noop kernel)...\n");

    const size_t total_samples = window_samples * channels;
    float *input = (float *)malloc(total_samples * sizeof(float));
    float *output = (float *)malloc(total_samples * sizeof(float));
    assert(input && output);

    /* Fill input with test pattern */
    for (size_t i = 0; i < total_samples; i++) {
        input[i] = (float)i * 0.1f;
    }

    cortex_device_timing_t timing;
    ret = device_comm_execute_window(
        result.handle,
        0,  /* sequence 0 */
        input,
        window_samples,
        channels,
        output,
        total_samples * sizeof(float),
        &timing
    );

    if (ret < 0) {
        printf("ERROR: device_comm_execute_window failed with code %d\n", ret);
        device_comm_teardown(result.handle);
        free(input);
        free(output);
        return 1;
    }

    /* Verify noop output matches input (bit-exact) */
    if (memcmp(input, output, total_samples * sizeof(float)) != 0) {
        printf("ERROR: Output does not match input (noop should be identity)\n");
        /* Show first few samples for debugging */
        printf("First 10 input samples:  ");
        for (int i = 0; i < 10; i++) printf("%.2f ", input[i]);
        printf("\n");
        printf("First 10 output samples: ");
        for (int i = 0; i < 10; i++) printf("%.2f ", output[i]);
        printf("\n");
        device_comm_teardown(result.handle);
        free(input);
        free(output);
        return 1;
    }

    printf("   ✓ Window executed successfully\n");
    printf("   ✓ Output matches input (noop identity verified)\n\n");

    /* Display timing */
    printf("3. Device timing:\n");
    printf("   tin:       %lu ns\n", (unsigned long)timing.tin);
    printf("   tstart:    %lu ns\n", (unsigned long)timing.tstart);
    printf("   tend:      %lu ns\n", (unsigned long)timing.tend);
    printf("   tfirst_tx: %lu ns\n", (unsigned long)timing.tfirst_tx);
    printf("   tlast_tx:  %lu ns\n\n", (unsigned long)timing.tlast_tx);

    printf("   Processing latency: %lu ns\n", (unsigned long)(timing.tend - timing.tstart));

    /* Teardown */
    printf("4. Cleaning up adapter process...\n");
    device_comm_teardown(result.handle);
    free(input);
    free(output);

    printf("   ✓ Adapter cleaned up\n\n");

    printf("=== Smoke Test PASSED ===\n");
    return 0;
}
