#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "config.h"
#include "loader.h"
#include "telemetry.h"
#include "util.h"

#include "../scheduler/scheduler.h"
#include "../replayer/replayer.h"
#include "../../include/cortex_plugin.h"

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

static int make_scheduler(const cortex_run_config_t *cfg, const char *telemetry_dir, cortex_scheduler_t **out_sched) {
    cortex_scheduler_config_t sc = {0};
    sc.sample_rate_hz = cfg->dataset.sample_rate_hz;
    /* Use the first plugin's W/H/C/dtype as canonical for Week 3 */
    if (cfg->plugin_count == 0) return -1;
    sc.window_length_samples = cfg->plugins[0].runtime.window_length_samples;
    sc.hop_samples = cfg->plugins[0].runtime.hop_samples;
    sc.channels = cfg->plugins[0].runtime.channels;
    sc.dtype = cfg->plugins[0].runtime.dtype;
    sc.warmup_seconds = cfg->benchmark.parameters.warmup_seconds;
    sc.realtime_priority = (uint32_t)(cfg->realtime.priority >= 0 ? cfg->realtime.priority : 0);
    sc.cpu_affinity_mask = cfg->realtime.cpu_affinity_mask;
    sc.scheduler_policy = cfg->realtime.scheduler[0] ? cfg->realtime.scheduler : NULL;
    static char telemetry_path[1024];
    if (telemetry_dir && telemetry_dir[0]) {
        snprintf(telemetry_path, sizeof(telemetry_path), "%s/%s_telemetry.csv", telemetry_dir, "run");
        sc.telemetry_path = telemetry_path;
    } else {
        sc.telemetry_path = NULL; /* stdout only */
    }
    *out_sched = cortex_scheduler_create(&sc);
    return (*out_sched) ? 0 : -1;
}

static int register_plugins(harness_context_t *ctx) {
    int loaded_any = 0;
    for (size_t i = 0; i < ctx->run_cfg.plugin_count; i++) {
        /* Only load plugins explicitly marked as ready */
        if (ctx->run_cfg.plugins[i].status[0] && strcmp(ctx->run_cfg.plugins[i].status, "ready") != 0) {
            continue;
        }
        char so_path[512];
        if (cortex_plugin_build_path(ctx->run_cfg.plugins[i].name, so_path, sizeof(so_path)) != 0) {
            fprintf(stderr, "failed to build path for plugin %s\n", ctx->run_cfg.plugins[i].name);
            continue;
        }
        cortex_loaded_plugin_t lp;
        if (cortex_plugin_load(so_path, &lp) != 0) {
            fprintf(stderr, "failed to load plugin %s (%s)\n", ctx->run_cfg.plugins[i].name, so_path);
            continue;
        }

        cortex_plugin_config_t pc = {0};
        pc.abi_version = CORTEX_ABI_VERSION;
        pc.struct_size = (uint32_t)sizeof(pc);
        pc.sample_rate_hz = ctx->run_cfg.dataset.sample_rate_hz;
        pc.window_length_samples = ctx->run_cfg.plugins[i].runtime.window_length_samples;
        pc.hop_samples = ctx->run_cfg.plugins[i].runtime.hop_samples;
        pc.channels = ctx->run_cfg.plugins[i].runtime.channels;
        pc.dtype = ctx->run_cfg.plugins[i].runtime.dtype;
        pc.allow_in_place = ctx->run_cfg.plugins[i].runtime.allow_in_place ? 1 : 0;
        pc.kernel_params = NULL;
        pc.kernel_params_size = 0;

        cortex_scheduler_plugin_api_t api = lp.api;
        int rc = cortex_scheduler_register_plugin(ctx->scheduler, &api, &pc);
        if (rc != 0) {
            fprintf(stderr, "failed to register plugin %s (rc=%d)\n", ctx->run_cfg.plugins[i].name, rc);
            cortex_plugin_unload(&lp);
            continue;
        }
        loaded_any = 1;
        /* Keep lp handle alive if we need to unload later; for Week 3, scheduler teardown will call plugin teardown. */
    }
    if (!loaded_any) {
        fprintf(stderr, "[harness] no plugins loaded (skip or status!=ready)\n");
    }
    return 0;
}

static int run_once(harness_context_t *ctx, uint32_t seconds) {
    cortex_replayer_config_t rcfg = {0};
    rcfg.dataset_path = ctx->run_cfg.dataset.path;
    rcfg.sample_rate_hz = ctx->run_cfg.dataset.sample_rate_hz;
    rcfg.channels = ctx->run_cfg.dataset.channels;
    rcfg.dtype = 1u; /* float32 */
    rcfg.window_length_samples = ctx->run_cfg.plugins[0].runtime.window_length_samples;
    rcfg.hop_samples = ctx->run_cfg.plugins[0].runtime.hop_samples;
    rcfg.enable_dropouts = 0;
    rcfg.load_profile = ctx->run_cfg.benchmark.load_profile;

    if (cortex_replayer_run(&rcfg, on_replayer_chunk, ctx) != 0) {
        fprintf(stderr, "failed to start replayer\n");
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
    cortex_scheduler_flush(ctx->scheduler);
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

    if (make_scheduler(&ctx.run_cfg, ctx.run_cfg.output.directory, &ctx.scheduler) != 0 || !ctx.scheduler) {
        fprintf(stderr, "failed to create scheduler\n");
        return 1;
    }

    if (register_plugins(&ctx) != 0) {
        fprintf(stderr, "failed to register plugins\n");
        return 1;
    }

    /* Warmup phase */
    if (ctx.run_cfg.benchmark.parameters.warmup_seconds > 0) {
        run_once(&ctx, ctx.run_cfg.benchmark.parameters.warmup_seconds);
    }

    /* Measurement repeats */
    for (uint32_t r = 0; r < ctx.run_cfg.benchmark.parameters.repeats; r++) {
        run_once(&ctx, ctx.run_cfg.benchmark.parameters.duration_seconds);
    }

    /* For Week 3: scheduler prints telemetry to stdout; future: hook in buffer and write to file. */

    cortex_scheduler_destroy(ctx.scheduler);
    cortex_telemetry_free(&ctx.telemetry);
    return 0;
}


