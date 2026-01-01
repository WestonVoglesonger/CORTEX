/*
 * Adapter All Kernels Test
 *
 * Tests all 6 core kernels through the native@loopback adapter.
 * Validates that adapter execution produces reasonable output.
 */

#define _POSIX_C_SOURCE 200809L

#include "../src/engine/harness/device/device_comm.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Test configuration */
const char *ADAPTER_PATH = "primitives/adapters/v1/native@loopback/cortex_adapter_native_loopback";
const uint32_t SAMPLE_RATE_HZ = 160;
const uint32_t WINDOW_SAMPLES = 160;
const uint32_t HOP_SAMPLES = 80;
const uint32_t CHANNELS = 64;

/* Generate test signal: mix of sine waves */
static void generate_test_signal(float *output, uint32_t window_samples, uint32_t channels)
{
    for (uint32_t c = 0; c < channels; c++) {
        for (uint32_t s = 0; s < window_samples; s++) {
            /* Mix of 10Hz and 60Hz sine waves with channel-specific amplitude */
            float t = (float)s / SAMPLE_RATE_HZ;
            float amp = 1.0f + 0.1f * (float)c;
            output[c * window_samples + s] =
                amp * (sinf(2.0f * M_PI * 10.0f * t) +
                       0.5f * sinf(2.0f * M_PI * 60.0f * t));
        }
    }
}

/* Check if output is non-zero (for most kernels) */
static int check_nonzero_output(const float *output, size_t total_samples, const char *kernel_name)
{
    int nonzero_count = 0;
    for (size_t i = 0; i < total_samples; i++) {
        if (fabsf(output[i]) > 1e-6f) {
            nonzero_count++;
        }
    }

    /* At least 10% of samples should be non-zero for most kernels */
    if (nonzero_count < (int)(total_samples * 0.1)) {
        printf("ERROR: %s output is mostly zeros (%d/%zu non-zero)\n",
               kernel_name, nonzero_count, total_samples);
        return 0;
    }

    return 1;
}

/* Test a single kernel */
static int test_kernel(const char *plugin_name, const char *plugin_params)
{
    printf("\n--- Testing %s ---\n", plugin_name);

    /* Initialize device */
    cortex_device_handle_t *handle = NULL;
    int ret = device_comm_init(
        ADAPTER_PATH,
        NULL,  /* transport_config (NULL = default "local://") */
        plugin_name,
        plugin_params,
        SAMPLE_RATE_HZ,
        WINDOW_SAMPLES,
        HOP_SAMPLES,
        CHANNELS,
        NULL,  /* No calibration state */
        0,
        &handle
    );

    if (ret < 0) {
        printf("ERROR: device_comm_init failed with code %d\n", ret);
        return 0;
    }

    printf("  ✓ Adapter spawned\n");

    /* Allocate buffers */
    const size_t total_samples = WINDOW_SAMPLES * CHANNELS;
    float *input = (float *)malloc(total_samples * sizeof(float));
    float *output = (float *)malloc(total_samples * sizeof(float));
    assert(input && output);

    /* Generate test signal */
    generate_test_signal(input, WINDOW_SAMPLES, CHANNELS);

    /* Execute window */
    cortex_device_timing_t timing;
    ret = device_comm_execute_window(
        handle,
        0,  /* sequence 0 */
        input,
        WINDOW_SAMPLES,
        CHANNELS,
        output,
        total_samples * sizeof(float),
        &timing
    );

    if (ret < 0) {
        printf("ERROR: device_comm_execute_window failed with code %d\n", ret);
        device_comm_teardown(handle);
        free(input);
        free(output);
        return 0;
    }

    printf("  ✓ Window executed (latency: %lu ns)\n",
           (unsigned long)(timing.tend - timing.tstart));

    /* Count non-zero samples to understand actual output */
    int nonzero_count = 0;
    for (size_t i = 0; i < total_samples; i++) {
        if (fabsf(output[i]) > 1e-6f) {
            nonzero_count++;
        }
    }
    printf("  → Non-zero samples: %d/%zu (%.1f%%)\n",
           nonzero_count, total_samples,
           100.0 * nonzero_count / total_samples);

    /* Kernel-specific validation */
    int valid = 1;

    if (strcmp(plugin_name, "noop@f32") == 0) {
        /* Noop: output must match input exactly */
        if (memcmp(input, output, total_samples * sizeof(float)) != 0) {
            printf("ERROR: noop output does not match input\n");
            valid = 0;
        } else {
            printf("  ✓ Output matches input (identity verified)\n");
        }
    } else if (strcmp(plugin_name, "goertzel@f32") == 0) {
        /* Goertzel outputs 2 samples per channel (alpha + beta power) */
        size_t expected_nonzero = 2 * CHANNELS;  /* 2 × 64 = 128 */
        if (nonzero_count < (int)(expected_nonzero * 0.9)) {
            printf("ERROR: goertzel expected ~%zu non-zero, got %d\n",
                   expected_nonzero, nonzero_count);
            valid = 0;
        } else {
            printf("  ✓ Output shape correct (%d non-zero samples)\n", nonzero_count);
        }
    } else {
        /* Other kernels: output should be non-zero */
        if (!check_nonzero_output(output, total_samples, plugin_name)) {
            valid = 0;
        } else {
            printf("  ✓ Output is non-zero\n");
        }
    }

    /* Cleanup */
    device_comm_teardown(handle);
    free(input);
    free(output);

    if (valid) {
        printf("  ✓ %s PASSED\n", plugin_name);
    } else {
        printf("  ✗ %s FAILED\n", plugin_name);
    }

    return valid;
}

int main(void)
{
    printf("=== Adapter All Kernels Test ===\n");
    printf("Testing 6 core kernels through native@loopback adapter\n");

    int total_tests = 0;
    int passed_tests = 0;

    /* Test each kernel */
    struct {
        const char *name;
        const char *params;
    } kernels[] = {
        {"noop@f32", ""},
        {"car@f32", ""},
        {"notch_iir@f32", "f0_hz: 60.0, Q: 30.0"},
        {"bandpass_fir@f32", ""},
        {"goertzel@f32", "alpha_low_hz: 8.0, alpha_high_hz: 13.0, beta_low_hz: 13.0, beta_high_hz: 30.0"},
        {"welch_psd@f32", "n_fft: 256, n_overlap: 128"},
    };

    for (size_t i = 0; i < sizeof(kernels) / sizeof(kernels[0]); i++) {
        total_tests++;
        if (test_kernel(kernels[i].name, kernels[i].params)) {
            passed_tests++;
        }
    }

    printf("\n=== Test Summary ===\n");
    printf("Passed: %d/%d\n", passed_tests, total_tests);

    if (passed_tests == total_tests) {
        printf("\n✓ All kernels PASSED through adapter!\n");
        return 0;
    } else {
        printf("\n✗ %d kernel(s) FAILED\n", total_tests - passed_tests);
        return 1;
    }
}
