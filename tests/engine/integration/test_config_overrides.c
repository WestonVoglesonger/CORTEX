/*
 * Unit tests for CORTEX config filtering and environment variable overrides
 */

#define _POSIX_C_SOURCE 200809L  /* For setenv, unsetenv */

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "config.h"

/* Test: Filter to single kernel */
void test_kernel_filter_single() {
    cortex_run_config_t cfg = {0};

    /* Setup: 3 plugins */
    strncpy(cfg.plugins[0].name, "car", sizeof(cfg.plugins[0].name) - 1);
    strncpy(cfg.plugins[1].name, "goertzel", sizeof(cfg.plugins[1].name) - 1);
    strncpy(cfg.plugins[2].name, "notch_iir", sizeof(cfg.plugins[2].name) - 1);
    cfg.plugin_count = 3;

    /* Filter to just "goertzel" */
    int result = cortex_apply_kernel_filter(&cfg, "goertzel");
    assert(result == 0);
    assert(cfg.plugin_count == 1);
    assert(strcmp(cfg.plugins[0].name, "goertzel") == 0);

    printf("[PASS] test_kernel_filter_single\n");
}

/* Test: Filter to multiple kernels */
void test_kernel_filter_multiple() {
    cortex_run_config_t cfg = {0};

    /* Setup: 4 plugins */
    strncpy(cfg.plugins[0].name, "car", sizeof(cfg.plugins[0].name) - 1);
    strncpy(cfg.plugins[1].name, "goertzel", sizeof(cfg.plugins[1].name) - 1);
    strncpy(cfg.plugins[2].name, "notch_iir", sizeof(cfg.plugins[2].name) - 1);
    strncpy(cfg.plugins[3].name, "bandpass_fir", sizeof(cfg.plugins[3].name) - 1);
    cfg.plugin_count = 4;

    /* Filter to "goertzel,car" (order in filter determines output order) */
    int result = cortex_apply_kernel_filter(&cfg, "goertzel,car");
    assert(result == 0);
    assert(cfg.plugin_count == 2);
    assert(strcmp(cfg.plugins[0].name, "goertzel") == 0);
    assert(strcmp(cfg.plugins[1].name, "car") == 0);

    printf("[PASS] test_kernel_filter_multiple\n");
}

/* Test: Filter with whitespace */
void test_kernel_filter_whitespace() {
    cortex_run_config_t cfg = {0};

    /* Setup: 3 plugins */
    strncpy(cfg.plugins[0].name, "car", sizeof(cfg.plugins[0].name) - 1);
    strncpy(cfg.plugins[1].name, "goertzel", sizeof(cfg.plugins[1].name) - 1);
    strncpy(cfg.plugins[2].name, "notch_iir", sizeof(cfg.plugins[2].name) - 1);
    cfg.plugin_count = 3;

    /* Filter with extra whitespace: " goertzel , car " */
    int result = cortex_apply_kernel_filter(&cfg, " goertzel , car ");
    assert(result == 0);
    assert(cfg.plugin_count == 2);
    assert(strcmp(cfg.plugins[0].name, "goertzel") == 0);
    assert(strcmp(cfg.plugins[1].name, "car") == 0);

    printf("[PASS] test_kernel_filter_whitespace\n");
}

/* Test: Filter with kernel not found (should warn but not fail) */
void test_kernel_filter_not_found() {
    cortex_run_config_t cfg = {0};

    /* Setup: 2 plugins */
    strncpy(cfg.plugins[0].name, "car", sizeof(cfg.plugins[0].name) - 1);
    strncpy(cfg.plugins[1].name, "goertzel", sizeof(cfg.plugins[1].name) - 1);
    cfg.plugin_count = 2;

    /* Filter includes nonexistent kernel: "goertzel,nonexistent,car" */
    int result = cortex_apply_kernel_filter(&cfg, "goertzel,nonexistent,car");
    assert(result == 0);  /* Should succeed */
    assert(cfg.plugin_count == 2);  /* Only 2 kernels found */
    assert(strcmp(cfg.plugins[0].name, "goertzel") == 0);
    assert(strcmp(cfg.plugins[1].name, "car") == 0);

    printf("[PASS] test_kernel_filter_not_found\n");
}

/* Test: Filter resulting in zero kernels (should fail) */
void test_kernel_filter_zero_result() {
    cortex_run_config_t cfg = {0};

    /* Setup: 2 plugins */
    strncpy(cfg.plugins[0].name, "car", sizeof(cfg.plugins[0].name) - 1);
    strncpy(cfg.plugins[1].name, "goertzel", sizeof(cfg.plugins[1].name) - 1);
    cfg.plugin_count = 2;

    /* Filter to nonexistent kernels only */
    int result = cortex_apply_kernel_filter(&cfg, "nonexistent1,nonexistent2");
    assert(result == -1);  /* Should fail */

    printf("[PASS] test_kernel_filter_zero_result\n");
}

/* Test: Config overrides via environment variables */
void test_all_config_overrides() {
    /* Load baseline config without overrides */
    unsetenv("CORTEX_DURATION_OVERRIDE");
    unsetenv("CORTEX_REPEATS_OVERRIDE");
    unsetenv("CORTEX_WARMUP_OVERRIDE");

    cortex_run_config_t baseline_cfg = {0};
    int result = cortex_config_load("primitives/configs/cortex.yaml", &baseline_cfg);
    if (result != 0) {
        fprintf(stderr, "[SKIP] test_all_config_overrides (config load failed)\n");
        return;
    }

    /* Set all overrides */
    setenv("CORTEX_DURATION_OVERRIDE", "999", 1);
    setenv("CORTEX_REPEATS_OVERRIDE", "42", 1);
    setenv("CORTEX_WARMUP_OVERRIDE", "7", 1);

    cortex_run_config_t cfg = {0};
    result = cortex_config_load("primitives/configs/cortex.yaml", &cfg);
    assert(result == 0);

    /* Verify overrides were applied */
    assert(cfg.benchmark.parameters.duration_seconds == 999);
    assert(cfg.benchmark.parameters.repeats == 42);
    assert(cfg.benchmark.parameters.warmup_seconds == 7);

    /* Cleanup */
    unsetenv("CORTEX_DURATION_OVERRIDE");
    unsetenv("CORTEX_REPEATS_OVERRIDE");
    unsetenv("CORTEX_WARMUP_OVERRIDE");

    printf("[PASS] test_all_config_overrides\n");
}

/* Test: Empty override strings should not override */
void test_override_empty_string() {
    /* Load baseline config */
    unsetenv("CORTEX_DURATION_OVERRIDE");
    cortex_run_config_t baseline_cfg = {0};
    int result = cortex_config_load("primitives/configs/cortex.yaml", &baseline_cfg);
    if (result != 0) {
        fprintf(stderr, "[SKIP] test_override_empty_string (config load failed)\n");
        return;
    }

    /* Set empty override */
    setenv("CORTEX_DURATION_OVERRIDE", "", 1);

    cortex_run_config_t cfg = {0};
    result = cortex_config_load("primitives/configs/cortex.yaml", &cfg);
    assert(result == 0);

    /* Should use value from YAML (same as baseline), not override */
    assert(cfg.benchmark.parameters.duration_seconds ==
           baseline_cfg.benchmark.parameters.duration_seconds);

    /* Cleanup */
    unsetenv("CORTEX_DURATION_OVERRIDE");

    printf("[PASS] test_override_empty_string\n");
}

/* Test: Invalid override values should be ignored */
void test_override_invalid_values() {
    /* Load baseline config */
    unsetenv("CORTEX_DURATION_OVERRIDE");
    cortex_run_config_t baseline_cfg = {0};
    int result = cortex_config_load("primitives/configs/cortex.yaml", &baseline_cfg);
    if (result != 0) {
        fprintf(stderr, "[SKIP] test_override_invalid_values (config load failed)\n");
        return;
    }

    /* Set invalid override (negative) */
    setenv("CORTEX_DURATION_OVERRIDE", "-100", 1);

    cortex_run_config_t cfg = {0};
    result = cortex_config_load("primitives/configs/cortex.yaml", &cfg);
    assert(result == 0);

    /* Should ignore invalid value, use YAML value */
    assert(cfg.benchmark.parameters.duration_seconds ==
           baseline_cfg.benchmark.parameters.duration_seconds);

    /* Cleanup */
    unsetenv("CORTEX_DURATION_OVERRIDE");

    printf("[PASS] test_override_invalid_values\n");
}

int main() {
    printf("=== Running config override tests ===\n");

    test_kernel_filter_single();
    test_kernel_filter_multiple();
    test_kernel_filter_whitespace();
    test_kernel_filter_not_found();
    test_kernel_filter_zero_result();
    test_all_config_overrides();
    test_override_empty_string();
    test_override_invalid_values();

    printf("=== All tests passed ===\n");
    return 0;
}
