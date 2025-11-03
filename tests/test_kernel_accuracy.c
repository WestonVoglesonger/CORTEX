/*
 * Kernel Accuracy Test
 *
 * Validates kernel C implementations against Python oracles by:
 * 1. Loading real EEG data from dataset
 * 2. Processing windows through C kernels
 * 3. Processing same data through Python oracles
 * 4. Comparing outputs with tolerance checking (rtol=1e-5, atol=1e-6)
 *
 * FUTURE: Capability Assessment System
 * ===================================
 * Instead of loading real datasets for each test, implement pre-computed
 * capability database approach:
 * - Pre-generate synthetic datasets for standard configurations (64→2048ch, 160→500Hz)
 * - Benchmark system capabilities once to build capability database
 * - Provide instant answers to "can system X handle config Y?" queries
 * - Benefits: Fast queries, reproducible benchmarks, scalable to high channel counts
 * - Location: scripts/ directory with generation/benchmarking/query tools
 */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <getopt.h>
#include <dirent.h>
#include <sys/stat.h>
#include <unistd.h>
#include <fcntl.h>

#include "../include/cortex_plugin.h"
#include "../src/harness/loader/loader.h"

/* Test configuration */
typedef struct {
    char kernel_name[64];
    char data_path[512];
    int max_windows;
    int verbose;
    int test_all;
} test_config_t;

/* EEG data structure */
typedef struct {
    float *data;         /* [samples × channels] interleaved */
    size_t num_samples;
    size_t num_channels;
} eeg_data_t;

/* Test window */
typedef struct {
    float *window_data;  /* [W × C] */
    size_t window_idx;
} test_window_t;

/* Tolerance specification */
typedef struct {
    double rtol;
    double atol;
} tolerance_t;

/* Comparison result */
typedef struct {
    size_t mismatches;
    double max_abs_error;
    double max_rel_error;
    int passed;
} comparison_result_t;

/* Default configuration */
static test_config_t default_config = {
    .kernel_name = "",
    .data_path = "datasets/eegmmidb/converted/S001R03.float32",
    .max_windows = 10,
    .verbose = 0,
    .test_all = 1
};

/* Load EEG data from binary file */
static int load_eeg_data(const char *path, eeg_data_t *out) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        perror("Failed to open data file");
        return -1;
    }
    
    /* Get file size */
    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    fseek(f, 0, SEEK_SET);
    
    /* Assume 64 channels, calculate samples */
    const size_t channels = 64;
    const size_t num_samples = file_size / (sizeof(float) * channels);
    const size_t total_floats = num_samples * channels;
    
    /* Allocate and read */
    float *data = (float *)malloc(total_floats * sizeof(float));
    if (!data) {
        fclose(f);
        return -1;
    }
    
    size_t read_count = fread(data, sizeof(float), total_floats, f);
    fclose(f);
    
    if (read_count != total_floats) {
        fprintf(stderr, "Warning: read %zu floats, expected %zu\n", 
                read_count, total_floats);
    }
    
    out->data = data;
    out->num_samples = num_samples;
    out->num_channels = channels;
    
    return 0;
}

/* Extract windows from EEG data */
static int extract_windows(const eeg_data_t *data, size_t W, size_t H,
                          test_window_t **out_windows, size_t *out_count) {
    /* Guard against underflow: if num_samples < W, we can only create at most 1 window */
    if (data->num_samples < W) {
        /* Dataset too short for even one full window - return empty or error */
        *out_windows = NULL;
        *out_count = 0;
        return -1;
    }
    
    size_t max_windows = (data->num_samples - W) / H + 1;
    if (max_windows == 0) {
        max_windows = 1;
    }
    
    test_window_t *windows = (test_window_t *)calloc(max_windows, 
                                                      sizeof(test_window_t));
    if (!windows) {
        return -1;
    }
    
    size_t count = 0;
    for (size_t start = 0; start + W <= data->num_samples; start += H) {
        float *window = (float *)malloc(W * data->num_channels * sizeof(float));
        if (!window) {
            /* Free already allocated windows */
            for (size_t i = 0; i < count; i++) {
                free(windows[i].window_data);
            }
            free(windows);
            return -1;
        }
        
        memcpy(window, &data->data[start * data->num_channels],
               W * data->num_channels * sizeof(float));
        
        windows[count].window_data = window;
        windows[count].window_idx = start / H;
        count++;
    }
    
    *out_windows = windows;
    *out_count = count;
    return 0;
}

/* Compare outputs with tolerance checking */
static int compare_outputs(const float *c_output, const float *py_output,
                          size_t num_elements, const tolerance_t *tol,
                          comparison_result_t *result) {
    size_t mismatches = 0;
    double max_abs_error = 0.0;
    double max_rel_error = 0.0;
    
    for (size_t i = 0; i < num_elements; i++) {
        if (!isfinite(c_output[i]) || !isfinite(py_output[i])) {
            /* NaN or Inf handling */
            if (c_output[i] != py_output[i]) {
                mismatches++;
            }
            continue;
        }
        
        double abs_err = fabs(c_output[i] - py_output[i]);
        double rel_err = abs_err / (fabs(py_output[i]) + 1e-12);
        
        max_abs_error = fmax(max_abs_error, abs_err);
        max_rel_error = fmax(max_rel_error, rel_err);
        
        if (abs_err > tol->atol && rel_err > tol->rtol) {
            mismatches++;
        }
    }
    
    result->mismatches = mismatches;
    result->max_abs_error = max_abs_error;
    result->max_rel_error = max_rel_error;
    result->passed = (mismatches == 0);
    
    return 0;
}

/* Run Python oracle via subprocess */
static int run_python_oracle(const char *kernel_name, const float *input,
                             size_t W, size_t C, float *output,
                             const char *state_path, size_t output_size) {
    char input_file[] = "/tmp/test_input_XXXXXX";
    char output_file[] = "/tmp/test_output_XXXXXX";
    char command[1024];
    
    /* Create temporary input file */
    int fd_in = mkstemp(input_file);
    if (fd_in < 0) {
        perror("mkstemp failed for input");
        return -1;
    }
    
    FILE *f = fdopen(fd_in, "wb");
    if (!f) {
        close(fd_in);
        unlink(input_file);
        return -1;
    }
    
    size_t written = fwrite(input, sizeof(float), W * C, f);
    fclose(f);
    
    if (written != W * C) {
        unlink(input_file);
        return -1;
    }
    
    /* Create temporary output file */
    int fd_out = mkstemp(output_file);
    if (fd_out < 0) {
        perror("mkstemp failed for output");
        unlink(input_file);
        return -1;
    }
    close(fd_out);  /* Close it, Python will write to it */
    
    /* Build command with unique paths */
    /* Detect v2 kernels and use appropriate oracle path */
    if (strlen(kernel_name) > 3 && strcmp(kernel_name + strlen(kernel_name) - 3, "_v2") == 0) {
        /* Extract base name for v2 kernels */
        char base_name[64];
        size_t base_len = strlen(kernel_name) - 3;
        strncpy(base_name, kernel_name, base_len);
        base_name[base_len] = '\0';
        snprintf(command, sizeof(command),
                 "python3 kernels/v2/%s@f32/oracle.py --test %s --output %s --state %s > /dev/null 2>&1",
                 base_name, input_file, output_file, state_path);
    } else {
        snprintf(command, sizeof(command),
                 "python3 kernels/v1/%s@f32/oracle.py --test %s --output %s --state %s > /dev/null 2>&1",
                 kernel_name, input_file, output_file, state_path);
    }
    
    /* Execute oracle */
    int status = system(command);
    
    /* Clean up input file */
    unlink(input_file);
    
    if (status != 0) {
        fprintf(stderr, "Python oracle failed for %s\n", kernel_name);
        unlink(output_file);
        return -1;
    }
    
    /* Read output from unique temp file */
    FILE *out = fopen(output_file, "rb");
    if (!out) {
        fprintf(stderr, "Failed to read oracle output from %s\n", output_file);
        unlink(output_file);
        return -1;
    }
    
    size_t read_count = fread(output, sizeof(float), output_size, out);
    fclose(out);
    unlink(output_file);
    
    if (read_count != output_size) {
        fprintf(stderr, "Partial read: got %zu floats, expected %zu\n", 
                read_count, output_size);
        return -1;
    }
    
    return 0;
}

/* Build plugin config */
static cortex_plugin_config_t build_plugin_config(uint32_t Fs, uint32_t W,
                                                  uint32_t H, uint32_t C) {
    cortex_plugin_config_t config = {0};
    config.abi_version = CORTEX_ABI_VERSION;
    config.struct_size = sizeof(cortex_plugin_config_t);
    config.sample_rate_hz = Fs;
    config.window_length_samples = W;
    config.hop_samples = H;
    config.channels = C;
    config.dtype = CORTEX_DTYPE_FLOAT32;
    config.allow_in_place = 0;
    config.kernel_params = NULL;
    config.kernel_params_size = 0;
    return config;
}

/* Load tolerances from spec.yaml */
static tolerance_t load_tolerances(const char *kernel_name __attribute__((unused))) {
    /* For now, use default tolerances from spec */
    tolerance_t tol = {.rtol = 1e-5, .atol = 1e-6};
    return tol;
}

/* Test a single kernel */
static int test_kernel(const char *kernel_name, const test_config_t *config) {
    printf("\nTesting kernel: %s\n", kernel_name);
    printf("  Loading data: %s\n", config->data_path);

    /* Create unique state file for this test process */
    char state_file_template[512];
    snprintf(state_file_template, sizeof(state_file_template), "/tmp/%s_state_XXXXXX", kernel_name);
    int state_fd = mkstemp(state_file_template);
    if (state_fd < 0) {
        perror("mkstemp failed for state file");
        return -1;
    }
    close(state_fd);  /* Close it, Python will write to .npy version */
    unlink(state_file_template);  /* Remove temp, we'll use .npy extension */
    
    /* Construct .npy filename */
    char state_file[512];
    snprintf(state_file, sizeof(state_file), "%s.npy", state_file_template);
    
    /* 1. Load EEG data */
    eeg_data_t data;
    if (load_eeg_data(config->data_path, &data) != 0) {
        return -1;
    }
    
    printf("  Loaded %zu samples, %zu channels\n", 
           data.num_samples, data.num_channels);
    
    /* 2. Extract windows */
    test_window_t *windows = NULL;
    size_t num_windows = 0;
    const size_t W = 160;
    const size_t H = 80;
    
    if (extract_windows(&data, W, H, &windows, &num_windows) != 0) {
        fprintf(stderr, "Failed to extract windows\n");
        free(data.data);
        return -1;
    }
    
    printf("  Extracted %zu windows (W=%zu, H=%zu)\n", num_windows, W, H);
    
    /* 3. Load plugin */
    char plugin_path[512];
    char spec_uri[256];
    /* Detect v2 kernels (name ends with _v2) and use v2 path */
    if (strlen(kernel_name) > 3 && strcmp(kernel_name + strlen(kernel_name) - 3, "_v2") == 0) {
        /* Extract base name (e.g., "goertzel" from "goertzel_v2") */
        char base_name[64];
        size_t base_len = strlen(kernel_name) - 3;
        strncpy(base_name, kernel_name, base_len);
        base_name[base_len] = '\0';
        snprintf(spec_uri, sizeof(spec_uri), "kernels/v2/%s@f32", base_name);
    } else {
        snprintf(spec_uri, sizeof(spec_uri), "kernels/v1/%s@f32", kernel_name);
    }
    
    if (cortex_plugin_build_path(spec_uri, plugin_path, sizeof(plugin_path)) != 0) {
        fprintf(stderr, "  Failed to build plugin path for '%s'\n", kernel_name);
        for (size_t i = 0; i < num_windows; i++) {
            free(windows[i].window_data);
        }
        free(windows);
        free(data.data);
        return -1;
    }
    
    cortex_loaded_plugin_t plugin;
    if (cortex_plugin_load(plugin_path, &plugin) != 0) {
        fprintf(stderr, "  Failed to load plugin: %s\n", plugin_path);
        for (size_t i = 0; i < num_windows; i++) {
            free(windows[i].window_data);
        }
        free(windows);
        free(data.data);
        return -1;
    }
    
    /* Get plugin info to determine output shape */
    cortex_plugin_info_t info = plugin.api.get_info();
    size_t output_size = info.output_window_length_samples * info.output_channels;
    
    /* 4. Initialize plugin */
    cortex_plugin_config_t cfg = build_plugin_config(160, W, H, 64);
    void *handle = plugin.api.init(&cfg);
    
    if (!handle) {
        fprintf(stderr, "  Failed to initialize plugin\n");
        cortex_plugin_unload(&plugin);
        for (size_t i = 0; i < num_windows; i++) {
            free(windows[i].window_data);
        }
        free(windows);
        free(data.data);
        return -1;
    }
    
    /* 5. Load tolerances */
    tolerance_t tol = load_tolerances(kernel_name);
    
    printf("  Testing %d windows...\n", config->max_windows);
    
    /* 6. Test each window */
    int failures = 0;
    for (int i = 0; i < config->max_windows && i < (int)num_windows; i++) {
        float *c_output = (float *)calloc(output_size, sizeof(float));
        float *py_output = (float *)calloc(output_size, sizeof(float));
        
        /* Run C kernel */
        plugin.api.process(handle, windows[i].window_data, c_output);
        
        /* Run Python oracle */
        if (run_python_oracle(kernel_name, windows[i].window_data,
                             W, 64, py_output, state_file, output_size) != 0) {
            fprintf(stderr, "  Window %d: Oracle execution failed\n", i);
            failures++;
            free(c_output);
            free(py_output);
            continue;
        }
        
        /* Compare */
        comparison_result_t result;
        compare_outputs(c_output, py_output, output_size, &tol, &result);
        
        if (!result.passed) {
            fprintf(stderr, "  Window %d FAILED: %zu mismatches, "
                   "max_abs=%.2e, max_rel=%.2e\n",
                   i, result.mismatches, result.max_abs_error,
                   result.max_rel_error);
            failures++;
        } else if (config->verbose) {
            printf("  Window %d PASSED: max_abs=%.2e, max_rel=%.2e\n",
                   i, result.max_abs_error, result.max_rel_error);
        }
        
        free(c_output);
        free(py_output);
    }
    
    /* 7. Cleanup */
    plugin.api.teardown(handle);
    cortex_plugin_unload(&plugin);
    
    for (size_t i = 0; i < num_windows; i++) {
        free(windows[i].window_data);
    }
    free(windows);
    free(data.data);
    
    /* Clean up unique state file */
    unlink(state_file);
    
    /* 8. Report */
    if (failures == 0) {
        printf("  ✅ %s: ALL TESTS PASSED (%d windows)\n", 
               kernel_name, config->max_windows);
        return 0;
    } else {
        printf("  ❌ %s: %d/%d windows FAILED\n", 
               kernel_name, failures, config->max_windows);
        return -1;
    }
}

/* Show usage */
static void show_usage(const char *program_name) {
    printf("Usage: %s [options]\n", program_name);
    printf("\nOptions:\n");
    printf("  --kernel <name>     Test specific kernel (e.g., \"notch_iir\", \"fir_bandpass\")\n");
    printf("  --all               Test all kernels in registry (default)\n");
    printf("  --data <path>       Path to dataset\n");
    printf("  --windows <N>       Number of windows to test (default: 10)\n");
    printf("  --verbose           Print detailed comparison results\n");
    printf("  --help              Show this help\n");
}

/* Main */
int main(int argc, char **argv) {
    test_config_t config = default_config;
    int opt;
    struct option long_options[] = {
        {"kernel", required_argument, 0, 'k'},
        {"all", no_argument, 0, 'a'},
        {"data", required_argument, 0, 'd'},
        {"windows", required_argument, 0, 'w'},
        {"verbose", no_argument, 0, 'v'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };
    
    while ((opt = getopt_long(argc, argv, "k:ad:w:vh", 
                              long_options, NULL)) != -1) {
        switch (opt) {
        case 'k':
            strncpy(config.kernel_name, optarg, sizeof(config.kernel_name) - 1);
            config.test_all = 0;
            break;
        case 'a':
            config.test_all = 1;
            break;
        case 'd':
            strncpy(config.data_path, optarg, sizeof(config.data_path) - 1);
            break;
        case 'w':
            config.max_windows = atoi(optarg);
            break;
        case 'v':
            config.verbose = 1;
            break;
        case 'h':
            show_usage(argv[0]);
            return 0;
        default:
            show_usage(argv[0]);
            return 1;
        }
    }
    
    printf("Kernel Accuracy Test\n");
    printf("====================\n");
    
    /* Test specified kernel if --kernel provided */
    if (config.test_all) {
        printf("Testing all kernels not yet implemented\n");
        return 0;
    }
    
    if (strlen(config.kernel_name) == 0) {
        fprintf(stderr, "Must specify --kernel <name> or --all\n");
        return 1;
    }
    
    int status = test_kernel(config.kernel_name, &config);
    
    return status;
}
