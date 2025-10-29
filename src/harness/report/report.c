/* HTML Report Generator Implementation */

#include "report.h"
#include "../util/util.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

/* Statistics structure for a single kernel */
typedef struct {
    char plugin_name[64];
    uint64_t *latencies_ns;        /* Sorted for percentile calculations */
    uint64_t *latencies_ns_chrono;  /* Unsorted, chronological order for "Latency Over Time" plot */
    size_t count;
    uint32_t deadline_misses;
    double deadline_miss_rate;
    double p50_latency_us;
    double p95_latency_us;
    double p99_latency_us;
    double jitter_p95_us;
    double jitter_p99_us;
} kernel_stats_t;

/* Helper function to compute percentile */
static double compute_percentile(uint64_t *sorted_array, size_t count, double percentile) {
    if (count == 0) return 0.0;
    size_t index = (size_t)((percentile / 100.0) * count);
    if (index >= count) index = count - 1;
    return (double)sorted_array[index];
}

/* Comparison function for qsort */
static int compare_uint64(const void *a, const void *b) {
    uint64_t ia = *(const uint64_t *)a;
    uint64_t ib = *(const uint64_t *)b;
    return (ia > ib) - (ia < ib);
}

/* Group telemetry records by kernel and calculate statistics */
static int compute_kernel_stats(const cortex_telemetry_buffer_t *telemetry,
                               const char *plugin_filter,
                               kernel_stats_t *stats) {
    if (!telemetry || !stats) return -1;

    /* Count records for this plugin (excluding warmup) */
    size_t filtered_count = 0;
    for (size_t i = 0; i < telemetry->count; i++) {
        const cortex_telemetry_record_t *r = &telemetry->records[i];
        if (r->warmup) continue;
        if (!plugin_filter || strcmp(r->plugin_name, plugin_filter) == 0) {
            filtered_count++;
        }
    }

    if (filtered_count == 0) return -1;

    /* Allocate latency arrays (sorted and chronological) */
    uint64_t *latencies = (uint64_t *)malloc(filtered_count * sizeof(uint64_t));
    uint64_t *latencies_chrono = (uint64_t *)malloc(filtered_count * sizeof(uint64_t));
    if (!latencies || !latencies_chrono) {
        free(latencies);
        free(latencies_chrono);
        return -1;
    }

    uint32_t misses = 0;
    size_t idx = 0;

    /* Extract latencies and count misses */
    for (size_t i = 0; i < telemetry->count; i++) {
        const cortex_telemetry_record_t *r = &telemetry->records[i];
        if (r->warmup) continue;
        if (!plugin_filter || strcmp(r->plugin_name, plugin_filter) == 0) {
            uint64_t latency = r->end_ts_ns - r->start_ts_ns;
            latencies[idx] = latency;
            latencies_chrono[idx] = latency;  /* Keep chronological copy */
            idx++;
            if (r->deadline_missed) misses++;
        }
    }

    /* Sort for percentile calculation */
    qsort(latencies, filtered_count, sizeof(uint64_t), compare_uint64);

    /* Calculate statistics */
    strncpy(stats->plugin_name, plugin_filter ? plugin_filter : "all", sizeof(stats->plugin_name) - 1);
    stats->latencies_ns = latencies;
    stats->latencies_ns_chrono = latencies_chrono;
    stats->count = filtered_count;
    stats->deadline_misses = misses;
    stats->deadline_miss_rate = 100.0 * (double)misses / (double)filtered_count;
    stats->p50_latency_us = compute_percentile(latencies, filtered_count, 50.0) / 1000.0;
    stats->p95_latency_us = compute_percentile(latencies, filtered_count, 95.0) / 1000.0;
    stats->p99_latency_us = compute_percentile(latencies, filtered_count, 99.0) / 1000.0;
    stats->jitter_p95_us = (stats->p95_latency_us - stats->p50_latency_us);
    stats->jitter_p99_us = (stats->p99_latency_us - stats->p50_latency_us);

    return 0;
}

/* Free kernel statistics */
static void free_kernel_stats(kernel_stats_t *stats) {
    if (stats) {
        free(stats->latencies_ns);
        free(stats->latencies_ns_chrono);
        memset(stats, 0, sizeof(*stats));
    }
}

/* Get unique plugin names from telemetry */
static int get_unique_plugins(const cortex_telemetry_buffer_t *telemetry,
                             char (*plugins)[64],
                             size_t *count) {
    if (!telemetry || !plugins || !count) return -1;

    size_t unique_count = 0;

    for (size_t i = 0; i < telemetry->count; i++) {
        const char *name = telemetry->records[i].plugin_name;
        int found = 0;

        for (size_t j = 0; j < unique_count; j++) {
            if (strcmp(plugins[j], name) == 0) {
                found = 1;
                break;
            }
        }

        if (!found && unique_count < 32) {
            strncpy(plugins[unique_count], name, sizeof(plugins[0]) - 1);
            plugins[unique_count][sizeof(plugins[0]) - 1] = '\0';
            unique_count++;
        }
    }

    *count = unique_count;
    return 0;
}

/* Generate SVG histogram */
static void generate_histogram_svg(FILE *f, uint64_t *data, size_t count, 
                                    int width, int height) {
    if (count == 0) return;

    /* Find min and max */
    uint64_t min_val = data[0];
    uint64_t max_val = data[0];
    for (size_t i = 1; i < count; i++) {
        if (data[i] < min_val) min_val = data[i];
        if (data[i] > max_val) max_val = data[i];
    }

    if (min_val == max_val) {
        fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#666\">No variation</text>", 
                width/2, height/2);
        return;
    }

    /* Create histogram bins (20 bins) */
    int num_bins = 20;
    int *bins = (int *)calloc(num_bins, sizeof(int));
    if (!bins) return;

    double bin_width = (double)(max_val - min_val) / num_bins;

    for (size_t i = 0; i < count; i++) {
        int bin = (int)((data[i] - min_val) / bin_width);
        if (bin >= num_bins) bin = num_bins - 1;
        bins[bin]++;
    }

    /* Find max bin count for scaling */
    int max_bin = bins[0];
    for (int i = 1; i < num_bins; i++) {
        if (bins[i] > max_bin) max_bin = bins[i];
    }

    /* Draw histogram bars */
    double scale_x = (double)width / num_bins;
    double scale_y = (double)(height - 40) / max_bin;

    for (int i = 0; i < num_bins; i++) {
        int bar_height = (int)(bins[i] * scale_y);
        double x = i * scale_x;
        fprintf(f, "<rect x=\"%.0f\" y=\"%d\" width=\"%.0f\" height=\"%d\" "
                "fill=\"#4a90e2\" stroke=\"#2e5c8a\" stroke-width=\"1\"/>\n",
                x, height - bar_height - 20, scale_x, bar_height);
    }

    /* Draw axes and labels */
    fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"%d\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", height - 20, width, height - 20);
    fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"0\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", height - 20, 0);

    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"12\">Max: %.0f µs</text>",
            width - 100, height - 5, (double)max_val / 1000.0);

    free(bins);
}

/* Generate SVG line plot */
static void generate_line_plot_svg(FILE *f, uint64_t *data, size_t count,
                                   int width, int height) {
    if (count < 2) return;

    /* Find min and max for scaling */
    uint64_t min_val = data[0];
    uint64_t max_val = data[0];
    for (size_t i = 1; i < count; i++) {
        if (data[i] < min_val) min_val = data[i];
        if (data[i] > max_val) max_val = data[i];
    }

    if (min_val == max_val) {
        fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"%d\" y2=\"%d\" "
                "stroke=\"#4a90e2\" stroke-width=\"2\"/>\n", height/2, width, height/2);
        return;
    }

    /* Draw line */
    fprintf(f, "<polyline points=\"");
    for (size_t i = 0; i < count; i++) {
        double x = (double)i * width / (count - 1);
        double y = height - 20 - ((double)(data[i] - min_val) / (max_val - min_val)) * (height - 40);
        if (i > 0) fprintf(f, " ");
        fprintf(f, "%.0f,%.0f", x, y);
    }
    fprintf(f, "\" fill=\"none\" stroke=\"#4a90e2\" stroke-width=\"2\"/>\n");

    /* Draw axes */
    fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"%d\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", height - 20, width, height - 20);
    fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"0\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", height - 20, 0);
}

/* Generate HTML report */
int cortex_report_generate(const char *output_path,
                         const cortex_telemetry_buffer_t *telemetry,
                         const char *run_id) {
    if (!output_path || !telemetry || !run_id) return -1;

    FILE *f = fopen(output_path, "w");
    if (!f) return -1;

    /* Write HTML header */
    fprintf(f, "<!DOCTYPE html>\n<html>\n<head>\n");
    fprintf(f, "<meta charset=\"UTF-8\">\n");
    fprintf(f, "<title>CORTEX Benchmark Report</title>\n");
    fprintf(f, "<style>\n");
    fprintf(f, "body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }\n");
    fprintf(f, ".header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }\n");
    fprintf(f, ".summary { background: white; padding: 20px; margin: 20px 0; border-radius: 5px; }\n");
    fprintf(f, "table { width: 100%%; border-collapse: collapse; }\n");
    fprintf(f, "th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }\n");
    fprintf(f, "th { background: #3498db; color: white; }\n");
    fprintf(f, ".kernel-section { background: white; padding: 20px; margin: 20px 0; border-radius: 5px; }\n");
    fprintf(f, ".plot { margin: 20px 0; }\n");
    fprintf(f, "</style>\n</head>\n<body>\n");

    /* Write header */
    fprintf(f, "<div class=\"header\">\n");
    fprintf(f, "<h1>CORTEX Benchmark Report</h1>\n");
    fprintf(f, "<p><strong>Run ID:</strong> %s</p>\n", run_id);

    /* Get current time */
    time_t now = time(NULL);
    char time_str[64];
    struct tm *tm_info = localtime(&now);
    strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", tm_info);
    fprintf(f, "<p><strong>Generated:</strong> %s</p>\n", time_str);
    fprintf(f, "</div>\n");

    /* Get unique plugin names */
    char plugins[32][64];
    size_t plugin_count = 0;
    get_unique_plugins(telemetry, plugins, &plugin_count);

    if (plugin_count == 0) {
        fprintf(f, "<p>No telemetry data available.</p></body></html>");
        fclose(f);
        return 0;
    }

    /* Calculate statistics for each plugin */
    kernel_stats_t *stats = (kernel_stats_t *)calloc(plugin_count, sizeof(kernel_stats_t));
    if (!stats) {
        fclose(f);
        return -1;
    }

    for (size_t i = 0; i < plugin_count; i++) {
        compute_kernel_stats(telemetry, plugins[i], &stats[i]);
    }

    /* Summary table */
    fprintf(f, "<div class=\"summary\">\n<h2>Summary Statistics</h2>\n");
    fprintf(f, "<table>\n");
    fprintf(f, "<tr><th>Kernel</th><th>P50 Latency (µs)</th><th>P95 Latency (µs)</th>"
            "<th>P99 Latency (µs)</th><th>Jitter P95-P50 (µs)</th><th>Miss Rate (%%)</th></tr>\n");

    for (size_t i = 0; i < plugin_count; i++) {
        fprintf(f, "<tr>");
        fprintf(f, "<td>%s</td>", stats[i].plugin_name);
        fprintf(f, "<td>%.2f</td>", stats[i].p50_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].p95_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].p99_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].jitter_p95_us);
        fprintf(f, "<td>%.2f</td>", stats[i].deadline_miss_rate);
        fprintf(f, "</tr>\n");
    }
    fprintf(f, "</table>\n</div>\n");

    /* Per-kernel sections */
    for (size_t p = 0; p < plugin_count; p++) {
        if (stats[p].count == 0) continue;

        fprintf(f, "<div class=\"kernel-section\">\n");
        fprintf(f, "<h2>%s</h2>\n", stats[p].plugin_name);

        /* Latency distribution histogram */
        fprintf(f, "<h3>Latency Distribution</h3>\n");
        fprintf(f, "<div class=\"plot\">\n");
        fprintf(f, "<svg width=\"600\" height=\"300\">\n");
        generate_histogram_svg(f, stats[p].latencies_ns, stats[p].count, 600, 300);
        fprintf(f, "</svg>\n</div>\n");

        /* Latency over time line plot */
        fprintf(f, "<h3>Latency Over Time</h3>\n");
        fprintf(f, "<div class=\"plot\">\n");
        fprintf(f, "<svg width=\"600\" height=\"300\">\n");
        generate_line_plot_svg(f, stats[p].latencies_ns_chrono, stats[p].count, 600, 300);
        fprintf(f, "</svg>\n</div>\n");

        fprintf(f, "</div>\n");
    }

    /* Cleanup */
    for (size_t i = 0; i < plugin_count; i++) {
        free_kernel_stats(&stats[i]);
    }
    free(stats);

    fprintf(f, "</body>\n</html>\n");
    fclose(f);

    return 0;
}

