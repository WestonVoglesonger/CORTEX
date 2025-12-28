/*
 * CORTEX Calibration Harness - ABI v3
 *
 * Standalone binary for offline kernel calibration:
 *   1. Load plugin shared library
 *   2. Load calibration dataset (.float32 file)
 *   3. Call plugin's cortex_calibrate() function
 *   4. Save calibration state to .cortex_state file
 *
 * Usage:
 *   cortex_calibrate --plugin <spec_uri> --dataset <path> --windows <N> --output <state_file>
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>

#include "cortex_plugin.h"
#include "../loader/loader.h"
#include "../util/state_io.h"

#define DEFAULT_SAMPLE_RATE 160
#define DEFAULT_WINDOW_LENGTH 160
#define DEFAULT_HOP 80
#define DEFAULT_CHANNELS 64

static void print_usage(const char *prog) {
    fprintf(stderr, "Usage: %s [options]\n", prog);
    fprintf(stderr, "\nRequired:\n");
    fprintf(stderr, "  --plugin PATH        Plugin spec_uri (e.g., primitives/kernels/v1/ica@f32)\n");
    fprintf(stderr, "  --dataset PATH       Calibration dataset (.float32 file)\n");
    fprintf(stderr, "  --windows N          Number of windows to use\n");
    fprintf(stderr, "  --output PATH        Output .cortex_state file\n");
    fprintf(stderr, "\nOptional:\n");
    fprintf(stderr, "  --channels N         Number of channels (default: 64)\n");
    fprintf(stderr, "  --window-length N    Window length in samples (default: 160)\n");
    fprintf(stderr, "  --sample-rate N      Sample rate in Hz (default: 160)\n");
    fprintf(stderr, "  --verbose            Show verbose output\n");
    fprintf(stderr, "  --help               Show this help\n");
}

int main(int argc, char **argv) {
    const char *plugin_spec = NULL;
    const char *dataset_path = NULL;
    const char *output_path = NULL;
    uint32_t num_windows = 0;
    uint32_t channels = DEFAULT_CHANNELS;
    uint32_t window_length = DEFAULT_WINDOW_LENGTH;
    uint32_t sample_rate = DEFAULT_SAMPLE_RATE;
    int verbose = 0;

    /* Parse arguments */
    static struct option long_options[] = {
        {"plugin", required_argument, 0, 'p'},
        {"dataset", required_argument, 0, 'd'},
        {"windows", required_argument, 0, 'w'},
        {"output", required_argument, 0, 'o'},
        {"channels", required_argument, 0, 'c'},
        {"window-length", required_argument, 0, 'l'},
        {"sample-rate", required_argument, 0, 'r'},
        {"verbose", no_argument, 0, 'v'},
        {"help", no_argument, 0, 'h'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "p:d:w:o:c:l:r:vh", long_options, NULL)) != -1) {
        switch (opt) {
            case 'p': plugin_spec = optarg; break;
            case 'd': dataset_path = optarg; break;
            case 'w': num_windows = atoi(optarg); break;
            case 'o': output_path = optarg; break;
            case 'c': channels = atoi(optarg); break;
            case 'l': window_length = atoi(optarg); break;
            case 'r': sample_rate = atoi(optarg); break;
            case 'v': verbose = 1; break;
            case 'h':
                print_usage(argv[0]);
                return 0;
            default:
                print_usage(argv[0]);
                return 1;
        }
    }

    /* Validate required arguments */
    if (!plugin_spec || !dataset_path || !output_path || num_windows == 0) {
        fprintf(stderr, "Error: Missing required arguments\n\n");
        print_usage(argv[0]);
        return 1;
    }

    fprintf(stderr, "[calibrate] CORTEX Calibration Harness (ABI v3)\n");
    fprintf(stderr, "[calibrate] Plugin:   %s\n", plugin_spec);
    fprintf(stderr, "[calibrate] Dataset:  %s\n", dataset_path);
    fprintf(stderr, "[calibrate] Windows:  %u\n", num_windows);
    fprintf(stderr, "[calibrate] Output:   %s\n", output_path);
    fprintf(stderr, "[calibrate] Config:   C=%u, W=%u, Fs=%u Hz\n", channels, window_length, sample_rate);

    /* Build plugin path */
    char plugin_path[512];
    if (cortex_plugin_build_path(plugin_spec, plugin_path, sizeof(plugin_path)) != 0) {
        fprintf(stderr, "[calibrate] ERROR: Failed to build plugin path\n");
        return 1;
    }

    if (verbose) {
        fprintf(stderr, "[calibrate] Plugin path: %s\n", plugin_path);
    }

    /* Load plugin */
    cortex_loaded_plugin_t plugin;
    if (cortex_plugin_load(plugin_path, &plugin) != 0) {
        fprintf(stderr, "[calibrate] ERROR: Failed to load plugin\n");
        return 1;
    }

    /* Check if plugin supports calibration */
    if (plugin.api.calibrate == NULL) {
        fprintf(stderr, "[calibrate] ERROR: Plugin does not support calibration (missing cortex_calibrate symbol)\n");
        fprintf(stderr, "[calibrate] This plugin is ABI v2 (stateless/stateful), not v3 (trainable)\n");
        cortex_plugin_unload(&plugin);
        return 1;
    }

    fprintf(stderr, "[calibrate] Plugin loaded successfully (supports calibration)\n");

    /* Load dataset */
    FILE *f = fopen(dataset_path, "rb");
    if (!f) {
        fprintf(stderr, "[calibrate] ERROR: Failed to open dataset: %s\n", dataset_path);
        cortex_plugin_unload(&plugin);
        return 1;
    }

    /* Get file size */
    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    fseek(f, 0, SEEK_SET);

    /* Calculate expected size */
    size_t samples_per_window = window_length * channels;
    size_t bytes_per_window = samples_per_window * sizeof(float);
    size_t total_bytes = num_windows * bytes_per_window;

    if (file_size < (long)total_bytes) {
        fprintf(stderr, "[calibrate] ERROR: Dataset too small\n");
        fprintf(stderr, "  Required: %zu bytes (%u windows × %u samples × %u channels)\n",
                total_bytes, num_windows, window_length, channels);
        fprintf(stderr, "  Available: %ld bytes\n", file_size);
        fclose(f);
        cortex_plugin_unload(&plugin);
        return 1;
    }

    /* Allocate calibration data buffer */
    float *calibration_data = malloc(total_bytes);
    if (!calibration_data) {
        fprintf(stderr, "[calibrate] ERROR: Failed to allocate %zu bytes for calibration data\n", total_bytes);
        fclose(f);
        cortex_plugin_unload(&plugin);
        return 1;
    }

    /* Read calibration data */
    size_t read_bytes = fread(calibration_data, 1, total_bytes, f);
    fclose(f);

    if (read_bytes != total_bytes) {
        fprintf(stderr, "[calibrate] ERROR: Failed to read calibration data (read %zu/%zu bytes)\n",
                read_bytes, total_bytes);
        free(calibration_data);
        cortex_plugin_unload(&plugin);
        return 1;
    }

    fprintf(stderr, "[calibrate] Loaded %u windows (%zu bytes)\n", num_windows, total_bytes);

    /* Prepare plugin config */
    cortex_plugin_config_t config = {0};
    config.abi_version = CORTEX_ABI_VERSION;
    config.struct_size = sizeof(cortex_plugin_config_t);
    config.sample_rate_hz = sample_rate;
    config.window_length_samples = window_length;
    config.hop_samples = DEFAULT_HOP;
    config.channels = channels;
    config.dtype = CORTEX_DTYPE_FLOAT32;
    config.allow_in_place = 0;
    config.kernel_params = NULL;
    config.kernel_params_size = 0;
    config.calibration_state = NULL;
    config.calibration_state_size = 0;

    /* Call cortex_calibrate() */
    fprintf(stderr, "[calibrate] Calling cortex_calibrate()...\n");
    cortex_calibration_result_t result = plugin.api.calibrate(&config, calibration_data, num_windows);

    free(calibration_data);

    if (result.calibration_state == NULL || result.state_size_bytes == 0) {
        fprintf(stderr, "[calibrate] ERROR: cortex_calibrate() failed (returned NULL state)\n");
        cortex_plugin_unload(&plugin);
        return 1;
    }

    fprintf(stderr, "[calibrate] Calibration successful: %u bytes (version %u)\n",
            result.state_size_bytes, result.state_version);

    /* Save calibration state */
    if (cortex_state_save(output_path, result.calibration_state, result.state_size_bytes, result.state_version) != 0) {
        fprintf(stderr, "[calibrate] ERROR: Failed to save calibration state\n");
        free(result.calibration_state);
        cortex_plugin_unload(&plugin);
        return 1;
    }

    /* Cleanup */
    free(result.calibration_state);
    cortex_plugin_unload(&plugin);

    fprintf(stderr, "[calibrate] SUCCESS: Calibration state saved to %s\n", output_path);
    return 0;
}
