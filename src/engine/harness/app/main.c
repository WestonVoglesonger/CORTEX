#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <signal.h>

#include "config.h"
#include "cortex_state_io.h"
#include "signal_handler.h"
#include "telemetry.h"
#include "util.h"
#include "../report/report.h"
#include "../device/device_comm.h"

#include "../scheduler/scheduler.h"
#include "../replayer/replayer.h"
#include "cortex_plugin.h"

typedef struct harness_context {
    cortex_run_config_t run_cfg;
    cortex_scheduler_t *scheduler;
    cortex_telemetry_buffer_t telemetry;
    char run_id[32];
} harness_context_t;

static void on_replayer_chunk(const float *chunk_data, size_t chunk_samples, void *user_data) {
    (void)chunk_samples;
    harness_context_t *ctx = (harness_context_t *)user_data;
    cortex_scheduler_feed_samples(ctx->scheduler, chunk_data, chunk_samples);
}

static int make_scheduler(const cortex_plugin_entry_cfg_t *plugin_cfg, 
                          uint32_t sample_rate_hz,
                          const cortex_realtime_cfg_t *rt_cfg,
                          const cortex_benchmark_params_t *bench_params,
                          const char *telemetry_path,
                          cortex_scheduler_t **out_sched) {
    cortex_scheduler_config_t sc = {0};
    sc.sample_rate_hz = sample_rate_hz;
    sc.window_length_samples = plugin_cfg->runtime.window_length_samples;
    sc.hop_samples = plugin_cfg->runtime.hop_samples;
    sc.channels = plugin_cfg->runtime.channels;
    sc.dtype = plugin_cfg->runtime.dtype;
    sc.warmup_seconds = bench_params->warmup_seconds;
    sc.realtime_priority = (uint32_t)(rt_cfg->priority >= 0 ? rt_cfg->priority : 0);
    sc.cpu_affinity_mask = rt_cfg->cpu_affinity_mask;
    sc.scheduler_policy = rt_cfg->scheduler[0] ? rt_cfg->scheduler : NULL;
    sc.telemetry_path = telemetry_path;
    sc.telemetry_buffer = NULL;  /* Will be set by caller */
    sc.run_id = NULL;           /* Will be set by caller */
    sc.current_repeat = 0;      /* Will be updated by caller */
    *out_sched = cortex_scheduler_create(&sc);
    return (*out_sched) ? 0 : -1;
}

static int spawn_adapter(const char *plugin_name,
                         const cortex_plugin_entry_cfg_t *plugin_cfg,
                         uint32_t sample_rate_hz,
                         cortex_device_init_result_t *out_device_result,
                         void **out_calibration_state) {
    /* Load calibration state if path provided (v3 trainable kernels) */
    void *calibration_state_buffer = NULL;
    uint32_t calibration_state_size = 0;

    if (plugin_cfg->calibration_state[0] != '\0') {
        uint32_t state_version;
        int rc = cortex_state_load(plugin_cfg->calibration_state,
                                   &calibration_state_buffer,
                                   &calibration_state_size,
                                   &state_version);
        if (rc != 0) {
            /* STRICT ERROR HANDLING - fail fast, don't continue with invalid state */
            fprintf(stderr, "[harness] ERROR: Failed to load calibration state: %s\n",
                    plugin_cfg->calibration_state);
            return -1;
        }
        fprintf(stderr, "[harness] Loaded calibration state: %s (%u bytes, v%u)\n",
                plugin_cfg->calibration_state, calibration_state_size, state_version);
    }

    /* Spawn device adapter and perform handshake (universal adapter model) */
    /* Get transport URI from environment variable (CLI override) */
    const char *transport_uri = getenv("CORTEX_TRANSPORT_URI");
    /* NULL defaults to "local://" in device_comm_init */

    /* Pass spec_uri instead of just plugin_name so adapter knows full kernel path */
    int ret = device_comm_init(
        plugin_cfg->adapter_path,
        transport_uri,  /* transport_config: from env var or NULL (defaults to "local://") */
        plugin_cfg->spec_uri,  /* Full path: "primitives/kernels/v1/noop@f32" */
        plugin_cfg->params,
        sample_rate_hz,
        plugin_cfg->runtime.window_length_samples,
        plugin_cfg->runtime.hop_samples,
        plugin_cfg->runtime.channels,
        calibration_state_buffer,
        calibration_state_size,
        out_device_result
    );

    if (ret < 0) {
        fprintf(stderr, "[harness] failed to spawn adapter for '%s': %d\n", plugin_name, ret);
        free(calibration_state_buffer);
        return -1;
    }

    fprintf(stderr, "[harness] Adapter spawned: %s (output: %ux%u)\n",
            out_device_result->adapter_name,
            out_device_result->output_window_length_samples,
            out_device_result->output_channels);

    /* Return calibration state buffer to caller for cleanup after scheduler is destroyed */
    *out_calibration_state = calibration_state_buffer;
    return 0;
}

static int run_once(harness_context_t *ctx, uint32_t seconds, const cortex_plugin_entry_cfg_t *plugin_cfg) {
    cortex_replayer_config_t rcfg = {0};
    rcfg.dataset_path = ctx->run_cfg.dataset.path;
    rcfg.sample_rate_hz = ctx->run_cfg.dataset.sample_rate_hz;
    rcfg.channels = ctx->run_cfg.dataset.channels;
    rcfg.dtype = 1u; /* float32 */
    rcfg.window_length_samples = plugin_cfg->runtime.window_length_samples;
    rcfg.hop_samples = plugin_cfg->runtime.hop_samples;
    rcfg.enable_dropouts = 0;
    rcfg.load_profile = ctx->run_cfg.benchmark.load_profile;

    /* Create replayer instance */
    cortex_replayer_t *replayer = cortex_replayer_create(&rcfg);
    if (!replayer) {
        fprintf(stderr, "failed to create replayer\n");
        return -1;
    }

    /* Start background load profile before replayer */
    if (cortex_replayer_start_background_load(replayer, rcfg.load_profile) != 0) {
        fprintf(stderr, "[harness] warning: failed to start background load\n");
        /* Continue anyway - not a fatal error */
    }

    if (cortex_replayer_start(replayer, on_replayer_chunk, ctx) != 0) {
        fprintf(stderr, "failed to start replayer\n");
        cortex_replayer_destroy(replayer);
        return -1;
    }

    /* Run for the specified duration, or until shutdown signal received */
    const uint64_t start = cortex_now_ns();
    const uint64_t end_target = start + (uint64_t)seconds * 1000000000ULL;
    while (cortex_now_ns() < end_target && !cortex_should_shutdown()) {
        /* simple sleep-loop; nanosleep inside replayer governs cadence */
        struct timespec ts = { .tv_sec = 0, .tv_nsec = 10000000L };
        nanosleep(&ts, NULL);
    }

    /* Check if we're exiting due to shutdown signal */
    int was_interrupted = cortex_should_shutdown();
    if (was_interrupted) {
        fprintf(stderr, "\n[harness] Interrupted by signal, cleaning up...\n");
    }

    /* Cleanup: stop and destroy replayer (also stops background load) */
    cortex_replayer_destroy(replayer);
    cortex_scheduler_flush(ctx->scheduler);

    /* If interrupted, return error to signal early termination */
    return was_interrupted ? -1 : 0;
}

static int run_plugin(harness_context_t *ctx, size_t plugin_idx) {
    const cortex_plugin_entry_cfg_t *plugin_cfg = &ctx->run_cfg.plugins[plugin_idx];
    const char *plugin_name = plugin_cfg->name;

    printf("[harness] Running plugin: %s\n", plugin_name);

    /* Track starting telemetry count for this plugin */
    size_t telemetry_start_count = ctx->telemetry.count;

    /* Step 1: Get plugin config pointer */
    /* Step 2: Build per-plugin output directory and telemetry path */
    char plugin_output_dir[1024];
    snprintf(plugin_output_dir, sizeof(plugin_output_dir),
             "%s/kernel-data/%s",
             ctx->run_cfg.output.directory, plugin_name);

    /* Create per-plugin output directory */
    if (cortex_create_directories(plugin_output_dir) != 0) {
        fprintf(stderr, "[harness] failed to create output directory for plugin '%s'\n", plugin_name);
        return -1;
    }

    char telemetry_path[1024];
    snprintf(telemetry_path, sizeof(telemetry_path),
             "%s/telemetry.csv", plugin_output_dir);

    /* Step 3: Call make_scheduler() with plugin config */
    cortex_scheduler_t *scheduler = NULL;
    if (make_scheduler(plugin_cfg, 
                       ctx->run_cfg.dataset.sample_rate_hz,
                       &ctx->run_cfg.realtime,
                       &ctx->run_cfg.benchmark.parameters,
                       telemetry_path,
                       &scheduler) != 0) {
        fprintf(stderr, "[harness] failed to create scheduler for plugin '%s'\n", plugin_name);
        return -1;
    }
    
    /* Configure scheduler with telemetry buffer */
    cortex_scheduler_set_telemetry_buffer(scheduler, &ctx->telemetry);
    cortex_scheduler_set_run_id(scheduler, ctx->run_id);
    cortex_scheduler_set_current_repeat(scheduler, 0);  /* Warmup = repeat 0 */
    
    /* Step 4: Spawn adapter and perform handshake */
    cortex_device_init_result_t device_result;
    void *calibration_state = NULL;  /* Caller owns memory, frees after scheduler destroy */
    if (spawn_adapter(plugin_name, plugin_cfg, ctx->run_cfg.dataset.sample_rate_hz, &device_result, &calibration_state) != 0) {
        fprintf(stderr, "[harness] failed to spawn adapter for '%s'\n", plugin_name);
        cortex_scheduler_destroy(scheduler);
        return -1;
    }

    /* Step 5: Register device with scheduler */
    cortex_scheduler_device_info_t device_info = {0};
    device_info.device_handle = device_result.handle;
    device_info.output_window_length_samples = device_result.output_window_length_samples;
    device_info.output_channels = device_result.output_channels;
    strncpy(device_info.adapter_name, device_result.adapter_name, sizeof(device_info.adapter_name) - 1);
    strncpy(device_info.plugin_name, plugin_name, sizeof(device_info.plugin_name) - 1);

    if (cortex_scheduler_register_device(scheduler, &device_info, plugin_cfg->runtime.window_length_samples, plugin_cfg->runtime.channels) != 0) {
        fprintf(stderr, "[harness] failed to register device for '%s'\n", plugin_name);
        device_comm_teardown(device_result.handle);
        free(calibration_state);
        cortex_scheduler_destroy(scheduler);
        return -1;
    }

    /* Step 6: Set ctx->scheduler to new scheduler */
    ctx->scheduler = scheduler;
    
    /* Step 7: Call run_once() for warmup (ensures reproducible measurements per plugin) */
    if (ctx->run_cfg.benchmark.parameters.warmup_seconds > 0) {
        printf("[harness] Warmup phase for plugin '%s' (%u seconds)\n", plugin_name, ctx->run_cfg.benchmark.parameters.warmup_seconds);
        if (run_once(ctx, ctx->run_cfg.benchmark.parameters.warmup_seconds, plugin_cfg) != 0) {
            fprintf(stderr, "[harness] warmup failed for plugin '%s'\n", plugin_name);
            cortex_scheduler_destroy(scheduler);
            free(calibration_state);
            device_comm_teardown(device_result.handle);
            ctx->scheduler = NULL;
            return -1;
        }
    }
    
    /* Step 8: Loop: call run_once() for each repeat */
    int repeat_failed = 0;
    for (uint32_t r = 1; r <= ctx->run_cfg.benchmark.parameters.repeats; r++) {
        printf("[harness] Repeat %u/%u for plugin '%s'\n", r, ctx->run_cfg.benchmark.parameters.repeats, plugin_name);
        fflush(stdout);

        /* Update scheduler's current_repeat field */
        cortex_scheduler_set_current_repeat(ctx->scheduler, r);

        if (run_once(ctx, ctx->run_cfg.benchmark.parameters.duration_seconds, plugin_cfg) != 0) {
            fprintf(stderr, "[harness] repeat %u failed for plugin '%s'\n", r, plugin_name);

            /* If failure was due to shutdown signal, flush telemetry before exiting */
            if (cortex_should_shutdown()) {
                fprintf(stderr, "[harness] Shutdown signal received, preserving telemetry data\n");
                repeat_failed = 1;
                break;  /* Exit loop but continue to telemetry writing */
            }

            /* Non-shutdown failure - cleanup and return immediately */
            cortex_scheduler_destroy(scheduler);
            free(calibration_state);
            device_comm_teardown(device_result.handle);
            ctx->scheduler = NULL;
            return -1;
        }
    }

    /* Step 9: Cleanup */
    cortex_scheduler_destroy(scheduler);  /* Must destroy scheduler before tearing down adapter */
    ctx->scheduler = NULL;
    free(calibration_state);  /* Free state buffer (adapter made copy during handshake) */
    device_comm_teardown(device_result.handle);  /* CRITICAL: Teardown adapter and reap process */

    /* Step 9: Write this plugin's telemetry to per-plugin output directory */
    size_t telemetry_end_count = ctx->telemetry.count;

    if (telemetry_end_count > telemetry_start_count) {
        cortex_system_info_t sysinfo;
        if (cortex_collect_system_info(&sysinfo) != 0) {
            memset(&sysinfo, 0, sizeof(sysinfo));
        }

        /* Add device system info from HELLO frame */
        strncpy(sysinfo.device_hostname, device_result.device_hostname, sizeof(sysinfo.device_hostname) - 1);
        sysinfo.device_hostname[sizeof(sysinfo.device_hostname) - 1] = '\0';
        strncpy(sysinfo.device_cpu, device_result.device_cpu, sizeof(sysinfo.device_cpu) - 1);
        sysinfo.device_cpu[sizeof(sysinfo.device_cpu) - 1] = '\0';
        strncpy(sysinfo.device_os, device_result.device_os, sizeof(sysinfo.device_os) - 1);
        sysinfo.device_os[sizeof(sysinfo.device_os) - 1] = '\0';

        const char *format = ctx->run_cfg.output.format;
        const char *ext = (strcmp(format, "ndjson") == 0) ? "ndjson" : "csv";

        char telemetry_output_path[1024];
        snprintf(telemetry_output_path, sizeof(telemetry_output_path),
                 "%s/telemetry.%s", plugin_output_dir, ext);

        printf("[harness] Writing telemetry: %s (%zu records)\n",
               telemetry_output_path, telemetry_end_count - telemetry_start_count);
        fflush(stdout);

        if (strcmp(format, "ndjson") == 0) {
            cortex_telemetry_write_ndjson_filtered(telemetry_output_path, &ctx->telemetry,
                                                   telemetry_start_count, telemetry_end_count,
                                                   &sysinfo);
        } else {
            cortex_telemetry_write_csv_filtered(telemetry_output_path, &ctx->telemetry,
                                                telemetry_start_count, telemetry_end_count,
                                                &sysinfo);
        }
    }

    /* Step 10: Keep buffer for report generation (don't reset) */
    /* Buffer accumulates records from all plugins for combined report */

    if (repeat_failed) {
        fprintf(stderr, "[harness] Plugin '%s' interrupted, telemetry preserved\n", plugin_name);
        return -1;  /* Signal interruption to caller */
    }

    printf("[harness] Completed plugin: %s\n", plugin_name);
    return 0;
}

static void print_usage(const char *argv0) {
    fprintf(stderr, "Usage: %s run <config.yaml>\n", argv0);
}

int main(int argc, char **argv) {
    if (argc < 3 || strcmp(argv[1], "run") != 0) {
        print_usage(argv[0]);
        return 1;
    }

    const char *config_path = argv[2];
    harness_context_t ctx;
    memset(&ctx, 0, sizeof(ctx));

    if (cortex_config_load(config_path, &ctx.run_cfg) != 0) {
        fprintf(stderr, "failed to load config: %s\n", config_path);
        return 1;
    }

    /* Allow environment variable to override output directory */
    /* This lets the Python runner pass the run-specific output path */
    const char *output_dir_override = getenv("CORTEX_OUTPUT_DIR");
    if (output_dir_override && strlen(output_dir_override) > 0) {
        strncpy(ctx.run_cfg.output.directory, output_dir_override,
                sizeof(ctx.run_cfg.output.directory) - 1);
        ctx.run_cfg.output.directory[sizeof(ctx.run_cfg.output.directory) - 1] = '\0';
    }

    char err[128];
    if (cortex_config_validate(&ctx.run_cfg, err, sizeof(err)) != 0) {
        fprintf(stderr, "invalid config: %s\n", err);
        return 1;
    }

    cortex_generate_run_id(ctx.run_id);
    if (cortex_telemetry_init(&ctx.telemetry, 2048) != 0) {
        fprintf(stderr, "failed to init telemetry buffer\n");
        return 1;
    }

    /* Install signal handlers for graceful shutdown on Ctrl+C */
    cortex_install_signal_handlers();

    /* Ignore SIGPIPE (prevent crashes on broken pipe during adapter communication) */
    signal(SIGPIPE, SIG_IGN);

    /* Track if we were interrupted by a signal */
    int was_interrupted = 0;

    /* Auto-detect kernels if not explicitly specified */
    if (ctx.run_cfg.auto_detect_kernels) {
        printf("[harness] No plugins specified in config, auto-detecting kernels...\n");
        int discovered = cortex_discover_kernels(&ctx.run_cfg);
        if (discovered < 0) {
            fprintf(stderr, "[harness] kernel auto-detection failed\n");
            return 1;
        }
        if (discovered == 0) {
            fprintf(stderr, "[harness] warning: no built kernels found in primitives/kernels/\n");
            fprintf(stderr, "[harness] hint: run 'cortex build' to build available kernels\n");
            /* Not a fatal error - allow harness to run with no plugins */
        } else {
            printf("[harness] auto-detected %d built kernel(s)\n", discovered);
        }

        /* Load kernel specs for all auto-detected kernels */
        for (size_t i = 0; i < ctx.run_cfg.plugin_count; i++) {
            cortex_plugin_entry_cfg_t *plugin = &ctx.run_cfg.plugins[i];
            if (strcmp(plugin->status, "ready") != 0) continue;

            if (cortex_load_kernel_spec(plugin->spec_uri, ctx.run_cfg.dataset.channels,
                                        &plugin->runtime) != 0) {
                fprintf(stderr, "[harness] warning: failed to load spec for %s, skipping\n",
                        plugin->name);
                strncpy(plugin->status, "skip", sizeof(plugin->status) - 1);
                continue;
            }
        }

        /* Re-validate config with auto-detected kernels */
        if (cortex_config_validate(&ctx.run_cfg, err, sizeof(err)) != 0) {
            fprintf(stderr, "invalid config after auto-detection: %s\n", err);
            return 1;
        }
    }

    /* Apply CORTEX_KERNEL_FILTER to final plugin list (works for both sources) */
    const char *kernel_filter = getenv("CORTEX_KERNEL_FILTER");
    if (kernel_filter && strlen(kernel_filter) > 0) {
        printf("[harness] Applying kernel filter: %s\n", kernel_filter);
        if (cortex_apply_kernel_filter(&ctx.run_cfg, kernel_filter) != 0) {
            fprintf(stderr, "[harness] Failed to apply kernel filter\n");
            return 1;
        }
        printf("[harness] Filtered to %zu kernel(s)\n", ctx.run_cfg.plugin_count);
    }

    /* Sequential plugin execution */
    for (size_t i = 0; i < ctx.run_cfg.plugin_count; i++) {
        /* Check for shutdown signal before starting next plugin */
        if (cortex_should_shutdown()) {
            fprintf(stderr, "[harness] Shutdown requested, skipping remaining plugins\n");
            was_interrupted = 1;
            break;
        }

        if (strcmp(ctx.run_cfg.plugins[i].status, "ready") != 0) {
            continue;
        }
        printf("[harness] Running plugin: %s\n", ctx.run_cfg.plugins[i].name);
        if (run_plugin(&ctx, i) != 0) {
            fprintf(stderr, "Plugin %s failed\n", ctx.run_cfg.plugins[i].name);

            /* If failure was due to shutdown signal, stop immediately */
            if (cortex_should_shutdown()) {
                fprintf(stderr, "[harness] Shutdown signal detected during plugin execution\n");
                was_interrupted = 1;
                break;
            }

            // For now: continue to next plugin (collect partial results)
            // Future: add benchmark.fail_fast config option to abort on first failure
        }
    }

    /* Check for shutdown one final time before report generation */
    if (cortex_should_shutdown() && !was_interrupted) {
        fprintf(stderr, "[harness] Shutdown requested before report generation\n");
        was_interrupted = 1;
    }

    /* Write all telemetry data ONCE after all plugins complete */
    if (ctx.telemetry.count > 0) {
        cortex_system_info_t sysinfo;
        if (cortex_collect_system_info(&sysinfo) != 0) {
            memset(&sysinfo, 0, sizeof(sysinfo));
        }

        const char *format = ctx.run_cfg.output.format;
        const char *ext = (strcmp(format, "ndjson") == 0) ? "ndjson" : "csv";

        char telemetry_output_path[1024];
        snprintf(telemetry_output_path, sizeof(telemetry_output_path),
                 "%s/telemetry.%s",
                 ctx.run_cfg.output.directory, ext);

        if (cortex_create_directories(ctx.run_cfg.output.directory) == 0) {
            printf("[harness] Writing telemetry: %s (%zu records)\n",
                   telemetry_output_path, ctx.telemetry.count);
            fflush(stdout);

            if (strcmp(format, "ndjson") == 0) {
                cortex_telemetry_write_ndjson(telemetry_output_path, &ctx.telemetry, &sysinfo);
            } else {
                cortex_telemetry_write_csv(telemetry_output_path, &ctx.telemetry, &sysinfo);
            }
        }
    }

    /* Generate HTML report after all plugins complete (skip if interrupted) */
    if (!was_interrupted) {
        /* Ensure output directory exists */
        if (cortex_create_directories(ctx.run_cfg.output.directory) == 0) {
            char report_path[1024];
            snprintf(report_path, sizeof(report_path), "%s/report.html",
                     ctx.run_cfg.output.directory);

            printf("[harness] Generating HTML report: %s\n", report_path);
            fflush(stdout);
            if (cortex_report_generate(report_path, &ctx.telemetry, ctx.run_id) == 0) {
                printf("[harness] Report generated successfully\n");
                fflush(stdout);
            } else {
                fprintf(stderr, "[harness] Failed to generate report\n");
            }
        }
    } else {
        fprintf(stderr, "[harness] Report generation skipped due to shutdown signal\n");
    }

    /* Check if shutdown was requested during report generation */
    if (cortex_should_shutdown() && !was_interrupted) {
        fprintf(stderr, "[harness] Shutdown requested during report generation\n");
        was_interrupted = 1;
    }

    cortex_telemetry_free(&ctx.telemetry);

    /* Return error code if interrupted, success otherwise */
    return was_interrupted ? 1 : 0;
}


