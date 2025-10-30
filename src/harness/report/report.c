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
    double min_latency_us;
    double max_latency_us;
    double mean_latency_us;
    double stddev_latency_us;
    double throughput_windows_per_s;
    uint32_t W;  /* Window length */
    uint32_t H;  /* Hop length */
    uint32_t C;  /* Channels */
    uint32_t Fs; /* Sample rate */
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
    uint64_t sum_latency_ns = 0;
    uint32_t W = 0, H = 0, C = 0, Fs = 0;

    /* Extract latencies and count misses */
    for (size_t i = 0; i < telemetry->count; i++) {
        const cortex_telemetry_record_t *r = &telemetry->records[i];
        if (r->warmup) continue;
        if (!plugin_filter || strcmp(r->plugin_name, plugin_filter) == 0) {
            uint64_t latency = r->end_ts_ns - r->start_ts_ns;
            latencies[idx] = latency;
            latencies_chrono[idx] = latency;  /* Keep chronological copy */
            sum_latency_ns += latency;
            idx++;
            if (r->deadline_missed) misses++;
            
            /* Get configuration from first record */
            if (idx == 1) {
                W = r->W;
                H = r->H;
                C = r->C;
                Fs = r->Fs;
            }
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
    
    /* Percentiles */
    stats->p50_latency_us = compute_percentile(latencies, filtered_count, 50.0) / 1000.0;
    stats->p95_latency_us = compute_percentile(latencies, filtered_count, 95.0) / 1000.0;
    stats->p99_latency_us = compute_percentile(latencies, filtered_count, 99.0) / 1000.0;
    stats->jitter_p95_us = (stats->p95_latency_us - stats->p50_latency_us);
    stats->jitter_p99_us = (stats->p99_latency_us - stats->p50_latency_us);
    
    /* Min/Max */
    stats->min_latency_us = (double)latencies[0] / 1000.0;
    stats->max_latency_us = (double)latencies[filtered_count - 1] / 1000.0;
    
    /* Mean */
    stats->mean_latency_us = (double)sum_latency_ns / (double)filtered_count / 1000.0;
    
    /* Standard deviation */
    double variance_sum = 0.0;
    double mean_ns = stats->mean_latency_us * 1000.0;
    for (size_t i = 0; i < filtered_count; i++) {
        double diff = (double)latencies[i] - mean_ns;
        variance_sum += diff * diff;
    }
    stats->stddev_latency_us = sqrt(variance_sum / (double)filtered_count) / 1000.0;
    
    /* Throughput: windows per second = Fs / H */
    if (H > 0 && Fs > 0) {
        stats->throughput_windows_per_s = (double)Fs / (double)H;
    } else {
        stats->throughput_windows_per_s = 0.0;
    }
    
    /* Configuration */
    stats->W = W;
    stats->H = H;
    stats->C = C;
    stats->Fs = Fs;

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

/* Generate SVG histogram with logarithmic binning for latency data */
static void generate_histogram_svg(FILE *f, uint64_t *data, size_t count,
                                    int width, int height) {
    if (count == 0) return;

    /* Convert to microseconds for display */
    double *latencies_us = (double *)malloc(count * sizeof(double));
    if (!latencies_us) return;

    for (size_t i = 0; i < count; i++) {
        latencies_us[i] = (double)data[i] / 1000.0;
    }

    /* Find min and max in microseconds */
    double min_us = latencies_us[0];
    double max_us = latencies_us[0];
    for (size_t i = 1; i < count; i++) {
        if (latencies_us[i] < min_us) min_us = latencies_us[i];
        if (latencies_us[i] > max_us) max_us = latencies_us[i];
    }

    if (min_us == max_us) {
        fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#666\">No variation</text>",
                width/2, height/2);
        free(latencies_us);
        return;
    }

    /* For latency data, use adaptive binning based on data distribution */
    /* Focus on the main distribution (P99) and use wider bins for outliers */
    double p99_us = latencies_us[(size_t)(count * 0.99)];  // 99th percentile
    double p95_us = latencies_us[(size_t)(count * 0.95)];  // 95th percentile

    int num_main_bins = 15;  // Bins for main distribution (up to P99)
    int num_tail_bins = 5;   // Bins for outliers (P99+)
    int num_bins = num_main_bins + num_tail_bins;

    int *bins = (int *)calloc(num_bins, sizeof(int));
    if (!bins) {
        free(latencies_us);
        return;
    }

    /* Create bins: fine-grained for main distribution, coarse for outliers */
    double main_range = p99_us - min_us;
    double tail_range = max_us - p99_us;

    for (size_t i = 0; i < count; i++) {
        int bin;
        if (latencies_us[i] <= p99_us) {
            // Main distribution: linear bins within P99
            bin = (int)((latencies_us[i] - min_us) / main_range * num_main_bins);
            if (bin >= num_main_bins) bin = num_main_bins - 1;
        } else {
            // Outliers: linear bins above P99
            bin = num_main_bins + (int)((latencies_us[i] - p99_us) / tail_range * num_tail_bins);
            if (bin >= num_bins) bin = num_bins - 1;
        }
        bins[bin]++;
    }

    /* Find max bin count for scaling */
    int max_bin_count = 0;
    for (int i = 0; i < num_bins; i++) {
        if (bins[i] > max_bin_count) max_bin_count = bins[i];
    }

    /* Draw histogram bars */
    double scale_x = (double)width / num_bins;
    double scale_y = (double)(height - 60) / max_bin_count;  // Leave room for percentile lines

    for (int i = 0; i < num_bins; i++) {
        int bar_height = (int)(bins[i] * scale_y);
        double x = i * scale_x;
        const char* fill_color = (i < num_main_bins) ? "#4a90e2" : "#e74c3c";  // Blue for main, red for outliers
        fprintf(f, "<rect x=\"%.0f\" y=\"%d\" width=\"%.0f\" height=\"%d\" "
                "fill=\"%s\" stroke=\"#2e5c8a\" stroke-width=\"1\"/>\n",
                x, height - bar_height - 40, scale_x - 1, bar_height, fill_color);
    }

    /* Draw percentile markers */
    double p50_us = latencies_us[count / 2];
    double p95_x = (p95_us - min_us) / main_range * num_main_bins * scale_x;
    double p99_x = num_main_bins * scale_x;
    double p50_x = (p50_us - min_us) / main_range * num_main_bins * scale_x;

    fprintf(f, "<line x1=\"%.0f\" y1=\"%d\" x2=\"%.0f\" y2=\"%d\" stroke=\"#27ae60\" stroke-width=\"2\" opacity=\"0.8\"/>\n",
            p50_x, height - 40, p50_x, height - 35);
    fprintf(f, "<line x1=\"%.0f\" y1=\"%d\" x2=\"%.0f\" y2=\"%d\" stroke=\"#f39c12\" stroke-width=\"2\" opacity=\"0.8\"/>\n",
            p95_x, height - 40, p95_x, height - 35);
    fprintf(f, "<line x1=\"%.0f\" y1=\"%d\" x2=\"%.0f\" y2=\"%d\" stroke=\"#e74c3c\" stroke-width=\"2\" opacity=\"0.8\"/>\n",
            p99_x, height - 40, p99_x, height - 35);

    /* Draw axes */
    fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"%d\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", height - 40, width, height - 40);
    fprintf(f, "<line x1=\"0\" y1=\"%d\" x2=\"0\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", height - 40, 20);

    /* Axis labels */
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"12\" text-anchor=\"middle\">"
            "Latency (µs)</text>\n", width / 2, height - 5);
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"12\" text-anchor=\"middle\" "
            "transform=\"rotate(-90 %d %d)\">Frequency</text>\n", 15, height / 2, 15, height / 2);

    /* Percentile labels */
    fprintf(f, "<text x=\"%.0f\" y=\"%d\" fill=\"#27ae60\" font-size=\"10\" text-anchor=\"middle\">P50: %.0f</text>\n",
            p50_x, height - 20, p50_us);
    fprintf(f, "<text x=\"%.0f\" y=\"%d\" fill=\"#f39c12\" font-size=\"10\" text-anchor=\"middle\">P95: %.0f</text>\n",
            p95_x, height - 20, p95_us);
    fprintf(f, "<text x=\"%.0f\" y=\"%d\" fill=\"#e74c3c\" font-size=\"10\" text-anchor=\"middle\">P99: %.0f</text>\n",
            p99_x, height - 20, p99_us);

    /* Legend */
    fprintf(f, "<rect x=\"%d\" y=\"%d\" width=\"12\" height=\"12\" fill=\"#4a90e2\" stroke=\"#2e5c8a\" stroke-width=\"1\"/>\n",
            width - 120, 25, 12, 12);
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"10\">Main distribution</text>\n",
            width - 100, 35);

    fprintf(f, "<rect x=\"%d\" y=\"%d\" width=\"12\" height=\"12\" fill=\"#e74c3c\" stroke=\"#2e5c8a\" stroke-width=\"1\"/>\n",
            width - 120, 40, 12, 12);
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"10\">Outliers (>%0.f µs)</text>\n",
            width - 100, 50, p99_us);

    free(bins);
    free(latencies_us);
}

/* Comparison function for qsort with doubles */
static int compare_double(const void *a, const void *b) {
    double da = *(const double *)a;
    double db = *(const double *)b;
    return (da > db) - (da < db);
}

/* Generate Cumulative Distribution Function (CDF) plot - more useful than timeline */
static void generate_cdf_plot_svg(FILE *f, uint64_t *data, size_t count,
                                  int width, int height) {
    if (count < 2) return;

    /* Convert to microseconds and sort for CDF */
    double *latencies_us = (double *)malloc(count * sizeof(double));
    if (!latencies_us) return;

    for (size_t i = 0; i < count; i++) {
        latencies_us[i] = (double)data[i] / 1000.0;
    }

    /* Sort for CDF calculation */
    qsort(latencies_us, count, sizeof(double), compare_double);

    double min_us = latencies_us[0];
    double max_us = latencies_us[count - 1];

    if (min_us == max_us) {
        fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#666\">No variation</text>",
                width/2, height/2);
        free(latencies_us);
        return;
    }

    /* Calculate percentiles for reference */
    double p50_us = latencies_us[count / 2];
    double p95_us = latencies_us[(size_t)(count * 0.95)];
    double p99_us = latencies_us[(size_t)(count * 0.99)];

    /* Draw CDF curve */
    fprintf(f, "<polyline points=\"");
    double x_range = max_us - min_us;
    double y_range = height - 60;
    
    for (size_t i = 0; i < count; i++) {
        double x = ((latencies_us[i] - min_us) / x_range) * (width - 40) + 20;
        double y = height - 40 - ((double)i / (count - 1)) * y_range;
        if (i > 0) fprintf(f, " ");
        fprintf(f, "%.1f,%.1f", x, y);
    }
    fprintf(f, "\" fill=\"none\" stroke=\"#4a90e2\" stroke-width=\"2.5\"/>\n");

    /* Draw percentile reference lines and markers */
    double p50_x = ((p50_us - min_us) / x_range) * (width - 40) + 20;
    double p95_x = ((p95_us - min_us) / x_range) * (width - 40) + 20;
    double p99_x = ((p99_us - min_us) / x_range) * (width - 40) + 20;
    double p50_y = height - 40 - 0.50 * y_range;
    double p95_y = height - 40 - 0.95 * y_range;
    double p99_y = height - 40 - 0.99 * y_range;

    /* Vertical percentile lines */
    fprintf(f, "<line x1=\"%.0f\" y1=\"%d\" x2=\"%.0f\" y2=\"%d\" "
            "stroke=\"#27ae60\" stroke-width=\"1.5\" stroke-dasharray=\"4,4\" opacity=\"0.8\"/>\n",
            p50_x, 20, p50_x, height - 40);
    fprintf(f, "<line x1=\"%.0f\" y1=\"%d\" x2=\"%.0f\" y2=\"%d\" "
            "stroke=\"#f39c12\" stroke-width=\"1.5\" stroke-dasharray=\"4,4\" opacity=\"0.8\"/>\n",
            p95_x, 20, p95_x, height - 40);
    fprintf(f, "<line x1=\"%.0f\" y1=\"%d\" x2=\"%.0f\" y2=\"%d\" "
            "stroke=\"#e74c3c\" stroke-width=\"1.5\" stroke-dasharray=\"4,4\" opacity=\"0.8\"/>\n",
            p99_x, 20, p99_x, height - 40);

    /* Horizontal percentile lines */
    fprintf(f, "<line x1=\"%d\" y1=\"%.0f\" x2=\"%d\" y2=\"%.0f\" "
            "stroke=\"#27ae60\" stroke-width=\"1.5\" stroke-dasharray=\"4,4\" opacity=\"0.8\"/>\n",
            20, p50_y, width - 20, p50_y);
    fprintf(f, "<line x1=\"%d\" y1=\"%.0f\" x2=\"%d\" y2=\"%.0f\" "
            "stroke=\"#f39c12\" stroke-width=\"1.5\" stroke-dasharray=\"4,4\" opacity=\"0.8\"/>\n",
            20, p95_y, width - 20, p95_y);
    fprintf(f, "<line x1=\"%d\" y1=\"%.0f\" x2=\"%d\" y2=\"%.0f\" "
            "stroke=\"#e74c3c\" stroke-width=\"1.5\" stroke-dasharray=\"4,4\" opacity=\"0.8\"/>\n",
            20, p99_y, width - 20, p99_y);

    /* Draw axes */
    fprintf(f, "<line x1=\"%d\" y1=\"%d\" x2=\"%d\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", 20, height - 40, width - 20, height - 40);
    fprintf(f, "<line x1=\"%d\" y1=\"%d\" x2=\"%d\" y2=\"%d\" "
            "stroke=\"#333\" stroke-width=\"2\"/>\n", 20, height - 40, 20, 20);

    /* Axis labels */
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"12\" text-anchor=\"middle\">"
            "Latency (µs)</text>\n", width / 2, height - 5);
    /* Y-axis label: center in plot area vertically, with padding from left edge */
    int plot_center_y = 20 + (height - 60) / 2;  /* Center of plot area (between y=20 and y=height-40) */
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#333\" font-size=\"12\" text-anchor=\"middle\" "
            "transform=\"rotate(-90 %d %d)\">Cumulative Probability</text>\n", 
            10, plot_center_y, 10, plot_center_y);

    /* Percentile labels on X-axis */
    fprintf(f, "<text x=\"%.0f\" y=\"%d\" fill=\"#27ae60\" font-size=\"10\" text-anchor=\"middle\">P50: %.0f</text>\n",
            p50_x, height - 20, p50_us);
    fprintf(f, "<text x=\"%.0f\" y=\"%d\" fill=\"#f39c12\" font-size=\"10\" text-anchor=\"middle\">P95: %.0f</text>\n",
            p95_x, height - 20, p95_us);
    fprintf(f, "<text x=\"%.0f\" y=\"%d\" fill=\"#e74c3c\" font-size=\"10\" text-anchor=\"middle\">P99: %.0f</text>\n",
            p99_x, height - 20, p99_us);

    /* Percentile labels on Y-axis */
    fprintf(f, "<text x=\"%d\" y=\"%.0f\" fill=\"#333\" font-size=\"10\" text-anchor=\"end\">50%%</text>\n",
            15, p50_y + 3);
    fprintf(f, "<text x=\"%d\" y=\"%.0f\" fill=\"#333\" font-size=\"10\" text-anchor=\"end\">95%%</text>\n",
            15, p95_y + 3);
    fprintf(f, "<text x=\"%d\" y=\"%.0f\" fill=\"#333\" font-size=\"10\" text-anchor=\"end\">99%%</text>\n",
            15, p99_y + 3);

    /* Min/Max labels */
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#666\" font-size=\"9\">%.0f µs</text>",
            25, height - 25, min_us);
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#666\" font-size=\"9\" text-anchor=\"end\">%.0f µs</text>",
            width - 25, height - 25, max_us);

    /* Explanation text */
    fprintf(f, "<text x=\"%d\" y=\"%d\" fill=\"#666\" font-size=\"10\" font-style=\"italic\">"
            "Shows what percentage of operations complete by each latency threshold</text>\n",
            width / 2, 15);

    free(latencies_us);
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
    fprintf(f, ".plot { margin: 20px 0; background: #fafafa; padding: 15px; border-radius: 5px; }\n");
    fprintf(f, "tr:nth-child(even) { background: #f9f9f9; }\n");
    fprintf(f, ".stat-label { color: #7f8c8d; font-size: 0.9em; }\n");
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
    fprintf(f, "<tr><th>Kernel</th><th>Windows</th><th>Min</th><th>P50</th><th>Mean</th><th>P95</th><th>P99</th><th>Max</th>"
            "<th>Std Dev</th><th>Jitter</th><th>Miss Rate</th><th>Throughput</th></tr>\n");
    fprintf(f, "<tr><th></th><th></th><th colspan=\"7\">Latency (µs)</th><th>µs</th><th>µs</th><th>%%</th><th>win/s</th></tr>\n");

    for (size_t i = 0; i < plugin_count; i++) {
        fprintf(f, "<tr>");
        fprintf(f, "<td><strong>%s</strong></td>", stats[i].plugin_name);
        fprintf(f, "<td>%zu</td>", stats[i].count);
        fprintf(f, "<td>%.2f</td>", stats[i].min_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].p50_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].mean_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].p95_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].p99_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].max_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].stddev_latency_us);
        fprintf(f, "<td>%.2f</td>", stats[i].jitter_p95_us);
        fprintf(f, "<td>%.2f</td>", stats[i].deadline_miss_rate);
        fprintf(f, "<td>%.2f</td>", stats[i].throughput_windows_per_s);
        fprintf(f, "</tr>\n");
    }
    fprintf(f, "</table>\n</div>\n");

    /* Per-kernel sections */
    for (size_t p = 0; p < plugin_count; p++) {
        if (stats[p].count == 0) continue;

        fprintf(f, "<div class=\"kernel-section\">\n");
        fprintf(f, "<h2>%s</h2>\n", stats[p].plugin_name);
        
        /* Configuration summary */
        fprintf(f, "<div style=\"background: #ecf0f1; padding: 15px; border-radius: 5px; margin-bottom: 20px;\">\n");
        fprintf(f, "<h3 style=\"margin-top: 0;\">Configuration</h3>\n");
        fprintf(f, "<table style=\"margin: 0;\">\n");
        fprintf(f, "<tr><th>Parameter</th><th>Value</th><th>Parameter</th><th>Value</th></tr>\n");
        fprintf(f, "<tr><td>Window Length (W)</td><td>%u samples</td>", stats[p].W);
        fprintf(f, "<td>Hop Length (H)</td><td>%u samples</td></tr>\n", stats[p].H);
        fprintf(f, "<tr><td>Channels (C)</td><td>%u</td>", stats[p].C);
        fprintf(f, "<td>Sample Rate (Fs)</td><td>%u Hz</td></tr>\n", stats[p].Fs);
        fprintf(f, "<tr><td>Window Period</td><td>%.3f ms</td>", 
                (double)stats[p].W / (double)stats[p].Fs * 1000.0);
        fprintf(f, "<td>Hop Period</td><td>%.3f ms</td></tr>\n",
                (double)stats[p].H / (double)stats[p].Fs * 1000.0);
        fprintf(f, "</table>\n");
        fprintf(f, "</div>\n");
        
        /* Detailed statistics */
        fprintf(f, "<h3>Detailed Statistics</h3>\n");
        fprintf(f, "<table>\n");
        fprintf(f, "<tr><th>Metric</th><th>Value</th><th>Metric</th><th>Value</th></tr>\n");
        fprintf(f, "<tr><td>Total Windows</td><td>%zu</td>", stats[p].count);
        fprintf(f, "<td>Deadline Misses</td><td>%u</td></tr>\n", stats[p].deadline_misses);
        fprintf(f, "<tr><td>Min Latency</td><td>%.2f µs</td>", stats[p].min_latency_us);
        fprintf(f, "<td>Max Latency</td><td>%.2f µs</td></tr>\n", stats[p].max_latency_us);
        fprintf(f, "<tr><td>Mean Latency</td><td>%.2f µs</td>", stats[p].mean_latency_us);
        fprintf(f, "<td>Std Deviation</td><td>%.2f µs</td></tr>\n", stats[p].stddev_latency_us);
        fprintf(f, "<tr><td>P50 Latency</td><td>%.2f µs</td>", stats[p].p50_latency_us);
        fprintf(f, "<td>P95 Latency</td><td>%.2f µs</td></tr>\n", stats[p].p95_latency_us);
        fprintf(f, "<tr><td>P99 Latency</td><td>%.2f µs</td>", stats[p].p99_latency_us);
        fprintf(f, "<td>Jitter (P95-P50)</td><td>%.2f µs</td></tr>\n", stats[p].jitter_p95_us);
        fprintf(f, "<tr><td>Throughput</td><td>%.2f windows/s</td>", stats[p].throughput_windows_per_s);
        fprintf(f, "<td>Miss Rate</td><td>%.2f%%</td></tr>\n", stats[p].deadline_miss_rate);
        fprintf(f, "</table>\n");

        /* Latency distribution histogram */
        fprintf(f, "<h3>Latency Distribution</h3>\n");
        fprintf(f, "<div class=\"plot\">\n");
        fprintf(f, "<svg width=\"700\" height=\"350\">\n");
        generate_histogram_svg(f, stats[p].latencies_ns, stats[p].count, 700, 350);
        fprintf(f, "</svg>\n</div>\n");

        /* Cumulative Distribution Function - more useful than timeline */
        fprintf(f, "<h3>Cumulative Distribution Function (CDF)</h3>\n");
        fprintf(f, "<div class=\"plot\">\n");
        fprintf(f, "<svg width=\"700\" height=\"350\">\n");
        generate_cdf_plot_svg(f, stats[p].latencies_ns, stats[p].count, 700, 350);
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

