#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "config.h"
#include "loader.h"
#include "telemetry.h"
#include "util.h"
#include "../report/report.h"

#include "../scheduler/scheduler.h"
#include "../replayer/replayer.h"
#include "../include/cortex_plugin.h"

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

static int load_plugin(const char *plugin_name,
                       const cortex_plugin_entry_cfg_t *plugin_cfg,
                       uint32_t sample_rate_hz,
                       cortex_scheduler_t *scheduler,
                       cortex_loaded_plugin_t *out_loaded) {
    /* Build plugin path from spec_uri */
    char plugin_path[1024];
    if (cortex_plugin_build_path(plugin_cfg->spec_uri, plugin_path, sizeof(plugin_path)) != 0) {
        fprintf(stderr, "[harness] failed to build plugin path for '%s'\n", plugin_name);
        return -1;
    }

    /* Load plugin */
    if (cortex_plugin_load(plugin_path, out_loaded) != 0) {
        fprintf(stderr, "[harness] failed to load plugin '%s' from '%s'\n", plugin_name, plugin_path);
        return -1;
    }

    /* Build plugin config */
    cortex_plugin_config_t pc = {0};
    pc.abi_version = CORTEX_ABI_VERSION;
    pc.struct_size = sizeof(cortex_plugin_config_t);
    pc.sample_rate_hz = sample_rate_hz;
    pc.window_length_samples = plugin_cfg->runtime.window_length_samples;
    pc.hop_samples = plugin_cfg->runtime.hop_samples;
    pc.channels = plugin_cfg->runtime.channels;
    pc.dtype = plugin_cfg->runtime.dtype;
    pc.allow_in_place = plugin_cfg->runtime.allow_in_place ? 1 : 0;
    pc.kernel_params = NULL;
    pc.kernel_params_size = 0;

    /* Register plugin with scheduler */
    cortex_scheduler_plugin_api_t api = out_loaded->api;

    if (cortex_scheduler_register_plugin(scheduler, &api, &pc, plugin_name) != 0) {
        fprintf(stderr, "[harness] failed to register plugin '%s' with scheduler\n", plugin_name);
        cortex_plugin_unload(out_loaded);
        return -1;
    }

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

    /* Start background load profile before replayer */
    if (cortex_replayer_start_background_load(rcfg.load_profile) != 0) {
        fprintf(stderr, "[harness] warning: failed to start background load\n");
        /* Continue anyway - not a fatal error */
    }

    if (cortex_replayer_run(&rcfg, on_replayer_chunk, ctx) != 0) {
        fprintf(stderr, "failed to start replayer\n");
        cortex_replayer_stop_background_load();
        return -1;
    }

    /* Run for the specified duration. */
    const uint64_t start = cortex_now_ns();
    const uint64_t end_target = start + (uint64_t)seconds * 1000000000ULL;
    while (cortex_now_ns() < end_target) {
        /* simple sleep-loop; nanosleep inside replayer governs cadence */
        struct timespec ts = { .tv_sec = 0, .tv_nsec = 10000000L };
        nanosleep(&ts, NULL);
    }

    cortex_replayer_stop();
    cortex_replayer_stop_background_load();
    cortex_scheduler_flush(ctx->scheduler);
    return 0;
}

static int run_plugin(harness_context_t *ctx, size_t plugin_idx) {
    const cortex_plugin_entry_cfg_t *plugin_cfg = &ctx->run_cfg.plugins[plugin_idx];
    const char *plugin_name = plugin_cfg->name;

    printf("[harness] Running plugin: %s\n", plugin_name);

    /* Collect system information for telemetry metadata */
    cortex_system_info_t sysinfo;
    if (cortex_collect_system_info(&sysinfo) != 0) {
        fprintf(stderr, "[harness] warning: failed to collect system info\n");
        memset(&sysinfo, 0, sizeof(sysinfo));
    }

    /* Step 1: Get plugin config pointer */
    /* Step 2: Build per-plugin telemetry path */
    /* Track starting telemetry count for this plugin */
    size_t telemetry_start_count = ctx->telemetry.count;

    char telemetry_path[1024];
    snprintf(telemetry_path, sizeof(telemetry_path),
             "%s/telemetry.csv",
             ctx->run_cfg.output.directory);
    
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
    
    /* Step 4: Call load_plugin() to load and register, save handle */
    cortex_loaded_plugin_t loaded_plugin;
    if (load_plugin(plugin_name, plugin_cfg, ctx->run_cfg.dataset.sample_rate_hz, scheduler, &loaded_plugin) != 0) {
        fprintf(stderr, "[harness] failed to load plugin '%s'\n", plugin_name);
        cortex_scheduler_destroy(scheduler);
        return -1;
    }
    
    /* Step 5: Set ctx->scheduler to new scheduler */
    ctx->scheduler = scheduler;
    
    /* Step 6: Call run_once() for warmup (ensures reproducible measurements per plugin) */
    if (ctx->run_cfg.benchmark.parameters.warmup_seconds > 0) {
        printf("[harness] Warmup phase for plugin '%s' (%u seconds)\n", plugin_name, ctx->run_cfg.benchmark.parameters.warmup_seconds);
        if (run_once(ctx, ctx->run_cfg.benchmark.parameters.warmup_seconds, plugin_cfg) != 0) {
            fprintf(stderr, "[harness] warmup failed for plugin '%s'\n", plugin_name);
            cortex_plugin_unload(&loaded_plugin);
            cortex_scheduler_destroy(scheduler);
            ctx->scheduler = NULL;
            return -1;
        }
    }
    
    /* Step 7: Loop: call run_once() for each repeat */
    for (uint32_t r = 1; r <= ctx->run_cfg.benchmark.parameters.repeats; r++) {
        printf("[harness] Repeat %u/%u for plugin '%s'\n", r, ctx->run_cfg.benchmark.parameters.repeats, plugin_name);
        fflush(stdout);

        /* Update scheduler's current_repeat field */
        cortex_scheduler_set_current_repeat(ctx->scheduler, r);
        
        if (run_once(ctx, ctx->run_cfg.benchmark.parameters.duration_seconds, plugin_cfg) != 0) {
            fprintf(stderr, "[harness] repeat %u failed for plugin '%s'\n", r, plugin_name);
            cortex_plugin_unload(&loaded_plugin);
            cortex_scheduler_destroy(scheduler);
            ctx->scheduler = NULL;
            return -1;
        }
    }
    
    /* Step 8: Cleanup */
    cortex_scheduler_destroy(scheduler);  /* Must destroy scheduler before unloading plugin */
    ctx->scheduler = NULL;
    cortex_plugin_unload(&loaded_plugin);  /* CRITICAL: Must unload plugin */
    
    /* Step 9: After all repeats, write only this plugin's records to file */
    size_t telemetry_end_count = ctx->telemetry.count;

    /* Choose output format from config */
    const char *format = ctx->run_cfg.output.format;
    const char *ext = (strcmp(format, "ndjson") == 0) ? "ndjson" : "csv";

    /* Write telemetry to output directory */
    char telemetry_output_path[1024];
    snprintf(telemetry_output_path, sizeof(telemetry_output_path),
             "%s/telemetry.%s",
             ctx->run_cfg.output.directory, ext);

    /* Ensure output directory exists */
    if (cortex_create_directories(ctx->run_cfg.output.directory) == 0) {
        if (strcmp(format, "ndjson") == 0) {
            cortex_telemetry_write_ndjson_filtered(telemetry_output_path, &ctx->telemetry,
                                                   telemetry_start_count, telemetry_end_count,
                                                   &sysinfo);
        } else {
            /* Default to CSV for unknown formats or explicit "csv" */
            cortex_telemetry_write_csv_filtered(telemetry_output_path, &ctx->telemetry,
                                                telemetry_start_count, telemetry_end_count,
                                                &sysinfo);
        }
    }
    
    /* Step 10: Keep buffer for report generation (don't reset) */
    /* Buffer will accumulate records from all plugins */
    
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

    /* Sequential plugin execution */
    for (size_t i = 0; i < ctx.run_cfg.plugin_count; i++) {
        if (strcmp(ctx.run_cfg.plugins[i].status, "ready") != 0) {
            continue;
        }
        printf("[harness] Running plugin: %s\n", ctx.run_cfg.plugins[i].name);
        if (run_plugin(&ctx, i) != 0) {
            fprintf(stderr, "Plugin %s failed\n", ctx.run_cfg.plugins[i].name);
            // For now: continue to next plugin (collect partial results)
            // Future: add benchmark.fail_fast config option to abort on first failure
        }
    }

    /* Generate HTML report after all plugins complete */
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

    cortex_telemetry_free(&ctx.telemetry);
    return 0;
}


