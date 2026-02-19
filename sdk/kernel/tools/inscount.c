/*
 * CORTEX Instruction Counter Tool
 *
 * Standalone binary that loads a kernel plugin, wraps cortex_process()
 * with hardware PMU counters, and outputs the retired instruction count
 * as JSON on stdout.
 *
 * Usage:
 *   cortex_inscount --plugin <spec_uri> [--channels N] [--window-length N] [--repeats N]
 *
 * Output (stdout):
 *   {"kernel": "bandpass_fir", "instruction_count": 12345, "repeats": 3, "available": true}
 *
 * On PMU failure:
 *   {"kernel": "bandpass_fir", "instruction_count": 0, "available": false, "error": "..."}
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>

#include "cortex_plugin.h"
#include "cortex_loader.h"
#include "inscount.h"

#define DEFAULT_CHANNELS       64
#define DEFAULT_WINDOW_LENGTH  160
#define DEFAULT_SAMPLE_RATE    160
#define DEFAULT_REPEATS        3

static void print_usage(const char *prog) {
    fprintf(stderr, "Usage: %s [options]\n", prog);
    fprintf(stderr, "\nRequired:\n");
    fprintf(stderr, "  --plugin PATH        Plugin spec_uri (e.g., primitives/kernels/v1/bandpass_fir@f32)\n");
    fprintf(stderr, "\nOptional:\n");
    fprintf(stderr, "  --channels N         Number of channels (default: %d)\n", DEFAULT_CHANNELS);
    fprintf(stderr, "  --window-length N    Window length in samples (default: %d)\n", DEFAULT_WINDOW_LENGTH);
    fprintf(stderr, "  --repeats N          Number of measurement repeats (default: %d)\n", DEFAULT_REPEATS);
    fprintf(stderr, "  --help               Show this help\n");
}

/* Extract kernel name from spec_uri: "primitives/kernels/v1/bandpass_fir@f32" -> "bandpass_fir" */
static const char *extract_kernel_name(const char *spec_uri) {
    const char *last_slash = strrchr(spec_uri, '/');
    const char *name = last_slash ? last_slash + 1 : spec_uri;

    /* Strip @dtype suffix */
    static char buf[256];
    strncpy(buf, name, sizeof(buf) - 1);
    buf[sizeof(buf) - 1] = '\0';
    char *at = strchr(buf, '@');
    if (at) *at = '\0';
    return buf;
}

/* Compare for qsort (uint64_t ascending) */
static int cmp_u64(const void *a, const void *b) {
    uint64_t va = *(const uint64_t *)a;
    uint64_t vb = *(const uint64_t *)b;
    if (va < vb) return -1;
    if (va > vb) return  1;
    return 0;
}

int main(int argc, char **argv) {
    const char *plugin_spec = NULL;
    uint32_t channels = DEFAULT_CHANNELS;
    uint32_t window_length = DEFAULT_WINDOW_LENGTH;
    int repeats = DEFAULT_REPEATS;

    static struct option long_options[] = {
        {"plugin",        required_argument, 0, 'p'},
        {"channels",      required_argument, 0, 'c'},
        {"window-length", required_argument, 0, 'l'},
        {"repeats",       required_argument, 0, 'r'},
        {"help",          no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };

    int opt;
    while ((opt = getopt_long(argc, argv, "p:c:l:r:h", long_options, NULL)) != -1) {
        switch (opt) {
            case 'p': plugin_spec = optarg; break;
            case 'c': channels = (uint32_t)atoi(optarg); break;
            case 'l': window_length = (uint32_t)atoi(optarg); break;
            case 'r': repeats = atoi(optarg); break;
            case 'h':
                print_usage(argv[0]);
                return 0;
            default:
                print_usage(argv[0]);
                return 1;
        }
    }

    if (!plugin_spec) {
        fprintf(stderr, "Error: --plugin is required\n\n");
        print_usage(argv[0]);
        return 1;
    }
    if (repeats < 1) repeats = 1;

    const char *kernel_name = extract_kernel_name(plugin_spec);

    /* Build plugin path */
    char plugin_path[512];
    if (cortex_plugin_build_path(plugin_spec, plugin_path, sizeof(plugin_path)) != 0) {
        printf("{\"kernel\": \"%s\", \"instruction_count\": 0, \"available\": false, "
               "\"error\": \"failed to build plugin path\"}\n", kernel_name);
        return 1;
    }

    /* Load plugin */
    cortex_loaded_plugin_t plugin;
    if (cortex_plugin_load(plugin_path, &plugin) != 0) {
        printf("{\"kernel\": \"%s\", \"instruction_count\": 0, \"available\": false, "
               "\"error\": \"failed to load plugin\"}\n", kernel_name);
        return 1;
    }

    /* Configure plugin — use ABI v2 for v2 kernels, v3 for v3 kernels */
    uint32_t abi_ver = (plugin.api.calibrate != NULL) ? 3u : 2u;

    cortex_plugin_config_t config;
    memset(&config, 0, sizeof(config));
    config.abi_version = abi_ver;
    config.struct_size = sizeof(cortex_plugin_config_t);
    config.sample_rate_hz = DEFAULT_SAMPLE_RATE;
    config.window_length_samples = window_length;
    config.hop_samples = window_length / 2;
    config.channels = channels;
    config.dtype = CORTEX_DTYPE_FLOAT32;
    config.allow_in_place = 0;

    /* Initialize plugin */
    cortex_init_result_t init_result = plugin.api.init(&config);
    if (init_result.handle == NULL) {
        printf("{\"kernel\": \"%s\", \"instruction_count\": 0, \"available\": false, "
               "\"error\": \"plugin init failed\"}\n", kernel_name);
        cortex_plugin_unload(&plugin);
        return 1;
    }

    /* Allocate I/O buffers (zeroed — content doesn't affect instruction count) */
    size_t input_size  = (size_t)window_length * channels * sizeof(float);
    size_t output_size = (size_t)init_result.output_window_length_samples
                       * init_result.output_channels * sizeof(float);

    float *input  = calloc(1, input_size);
    float *output = calloc(1, output_size);
    if (!input || !output) {
        printf("{\"kernel\": \"%s\", \"instruction_count\": 0, \"available\": false, "
               "\"error\": \"allocation failed\"}\n", kernel_name);
        plugin.api.teardown(init_result.handle);
        cortex_plugin_unload(&plugin);
        free(input);
        free(output);
        return 1;
    }

    /* Query CPU frequency (available regardless of PMU) */
    uint64_t cpu_freq_hz = cortex_inscount_cpu_freq_hz();

    /* Initialize PMU */
    if (cortex_inscount_init() != 0) {
        printf("{\"kernel\": \"%s\", \"instruction_count\": 0, \"cpu_freq_hz\": %llu, "
               "\"available\": false, "
               "\"error\": \"PMU init failed (no permission or unsupported platform)\"}\n",
               kernel_name, (unsigned long long)cpu_freq_hz);
        plugin.api.teardown(init_result.handle);
        cortex_plugin_unload(&plugin);
        free(input);
        free(output);
        return 0;  /* Not an error — PMU just isn't available */
    }

    /* Warm up: one uncounted call to prime caches */
    plugin.api.process(init_result.handle, input, output);

    /* Measure instruction count over repeats, take median */
    uint64_t *counts = malloc((size_t)repeats * sizeof(uint64_t));
    if (!counts) {
        printf("{\"kernel\": \"%s\", \"instruction_count\": 0, \"available\": false, "
               "\"error\": \"allocation failed\"}\n", kernel_name);
        cortex_inscount_teardown();
        plugin.api.teardown(init_result.handle);
        cortex_plugin_unload(&plugin);
        free(input);
        free(output);
        return 1;
    }

    for (int i = 0; i < repeats; i++) {
        cortex_inscount_start();
        plugin.api.process(init_result.handle, input, output);
        counts[i] = cortex_inscount_stop();
    }

    /* Median */
    qsort(counts, (size_t)repeats, sizeof(uint64_t), cmp_u64);
    uint64_t median_count = counts[repeats / 2];

    /* Output JSON */
    printf("{\"kernel\": \"%s\", \"instruction_count\": %llu, \"cpu_freq_hz\": %llu, "
           "\"repeats\": %d, \"available\": true}\n",
           kernel_name, (unsigned long long)median_count, (unsigned long long)cpu_freq_hz, repeats);

    /* Cleanup */
    free(counts);
    cortex_inscount_teardown();
    plugin.api.teardown(init_result.handle);
    cortex_plugin_unload(&plugin);
    free(input);
    free(output);

    return 0;
}
