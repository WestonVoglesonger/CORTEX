#include "config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

/*
 * Minimal, line-oriented parser for our known YAML structure.
 * Assumes simple key: value lines and indented blocks for plugins.
 * This is sufficient for Week 3 without bringing in a YAML dependency.
 */

static int starts_with(const char *s, const char *prefix) {
    return strncmp(s, prefix, strlen(prefix)) == 0;
}

static void trim(char *s) {
    size_t n = strlen(s);
    while (n > 0 && (s[n-1] == '\n' || s[n-1] == '\r' || isspace((unsigned char)s[n-1]))) {
        s[--n] = '\0';
    }
    size_t i = 0;
    while (s[i] && isspace((unsigned char)s[i])) {
        i++;
    }
    if (i > 0) {
        memmove(s, s + i, n - i + 1);
    }
}

static uint32_t parse_u32(const char *v) { return (uint32_t)strtoul(v, NULL, 10); }
static int parse_bool(const char *v) { return (starts_with(v, "true") || starts_with(v, "1")) ? 1 : 0; }

static void unquote(char *s) {
    size_t n = strlen(s);
    if (n >= 2) {
        if ((s[0] == '"' && s[n-1] == '"') || (s[0] == '\'' && s[n-1] == '\'')) {
            s[n-1] = '\0';
            memmove(s, s + 1, n - 1);
        }
    }
}

/* map dtype string to bitmask value used in cortex_plugin.h enum */
static uint32_t map_dtype(const char *s) {
    if (strcmp(s, "float32") == 0) return 1u; /* CORTEX_DTYPE_FLOAT32 */
    if (strcmp(s, "q15") == 0) return 2u;     /* CORTEX_DTYPE_Q15 */
    if (strcmp(s, "q7") == 0) return 4u;      /* CORTEX_DTYPE_Q7 */
    return 1u; /* default float32 */
}

int cortex_config_load(const char *path, cortex_run_config_t *out) {
    if (!path || !out) return -1;
    memset(out, 0, sizeof(*out));

    FILE *f = fopen(path, "r");
    if (!f) return -1;

    char line[1024];
    enum { TOP, IN_DATASET, IN_REALTIME, IN_BENCH, IN_BENCH_PARAMS, IN_OUTPUT, IN_PLUGINS, IN_PLUGIN, IN_PLUGIN_RUNTIME } st = TOP;
    size_t plugin_index = 0;

    while (fgets(line, sizeof(line), f)) {
        char raw[1024];
        strncpy(raw, line, sizeof(raw)-1); raw[sizeof(raw)-1] = '\0';
        trim(raw);
        if (raw[0] == '\0' || raw[0] == '#') continue;

        if (strcmp(raw, "dataset:") == 0) { st = IN_DATASET; continue; }
        if (strcmp(raw, "realtime:") == 0) { st = IN_REALTIME; continue; }
        if (strcmp(raw, "benchmark:") == 0) { st = IN_BENCH; continue; }
        if (strcmp(raw, "output:") == 0) { st = IN_OUTPUT; continue; }
        if (strcmp(raw, "plugins:") == 0) { st = IN_PLUGINS; continue; }

        if (st == IN_PLUGINS) {
            if (starts_with(raw, "- name:")) {
                if (plugin_index >= CORTEX_MAX_PLUGINS) break;
                memset(&out->plugins[plugin_index], 0, sizeof(out->plugins[plugin_index]));
                const char *v = raw + strlen("- name:");
                while (*v == ' ' ) v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].name, tmp, sizeof(out->plugins[plugin_index].name)-1);
                st = IN_PLUGIN;
                continue;
            }
        }

        if (st == IN_PLUGIN) {
            if (starts_with(raw, "status:")) {
                const char *v = raw + strlen("status:"); while (*v==' ') v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].status, tmp, sizeof(out->plugins[plugin_index].status)-1);
                continue;
            }
            if (starts_with(raw, "spec_uri:")) {
                const char *v = raw + strlen("spec_uri:"); while (*v==' ') v++;
                char tmp[256]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].spec_uri, tmp, sizeof(out->plugins[plugin_index].spec_uri)-1);
                continue;
            }
            if (starts_with(raw, "spec_version:")) {
                const char *v = raw + strlen("spec_version:"); while (*v==' ') v++;
                char tmp[32]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].spec_version, tmp, sizeof(out->plugins[plugin_index].spec_version)-1);
                continue;
            }
            if (strcmp(raw, "runtime:") == 0) { st = IN_PLUGIN_RUNTIME; continue; }
            if (starts_with(raw, "- name:")) { /* next plugin */
                plugin_index++;
                if (plugin_index >= CORTEX_MAX_PLUGINS) break;
                memset(&out->plugins[plugin_index], 0, sizeof(out->plugins[plugin_index]));
                const char *v = raw + strlen("- name:"); while (*v==' ') v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].name, tmp, sizeof(out->plugins[plugin_index].name)-1);
                continue;
            }
        }

        if (st == IN_PLUGIN_RUNTIME) {
            if (starts_with(raw, "window_length_samples:")) {
                const char *v = raw + strlen("window_length_samples:"); while (*v==' ') v++;
                out->plugins[plugin_index].runtime.window_length_samples = parse_u32(v);
                continue;
            }
            if (starts_with(raw, "hop_samples:")) {
                const char *v = raw + strlen("hop_samples:"); while (*v==' ') v++;
                out->plugins[plugin_index].runtime.hop_samples = parse_u32(v);
                continue;
            }
            if (starts_with(raw, "channels:")) {
                const char *v = raw + strlen("channels:"); while (*v==' ') v++;
                out->plugins[plugin_index].runtime.channels = parse_u32(v);
                continue;
            }
            if (starts_with(raw, "dtype:")) {
                const char *v = raw + strlen("dtype:"); while (*v==' ') v++;
                char tmp[32]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp);
                out->plugins[plugin_index].runtime.dtype = map_dtype(tmp);
                continue;
            }
            if (starts_with(raw, "allow_in_place:")) {
                const char *v = raw + strlen("allow_in_place:"); while (*v==' ') v++;
                out->plugins[plugin_index].runtime.allow_in_place = (uint8_t)parse_bool(v);
                continue;
            }
            /* Check for new plugin - parse it directly */
            if (starts_with(raw, "- name:")) {
                plugin_index++;  /* Move to next plugin slot */
                if (plugin_index >= CORTEX_MAX_PLUGINS) break;
                memset(&out->plugins[plugin_index], 0, sizeof(out->plugins[plugin_index]));
                const char *v = raw + strlen("- name:"); while (*v == ' ') v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1] = '\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].name, tmp, sizeof(out->plugins[plugin_index].name)-1);
                st = IN_PLUGIN;  /* Start parsing the new plugin */
                continue;
            }
            /* end of runtime block if dedented or new section; handled implicitly */
        }

        if (st == IN_DATASET) {
            if (starts_with(raw, "path:")) { const char *v = raw + strlen("path:"); while (*v==' ') v++; char tmp[512]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->dataset.path, tmp, sizeof(out->dataset.path)-1); continue; }
            if (starts_with(raw, "format:")) { const char *v = raw + strlen("format:"); while (*v==' ') v++; char tmp[32]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->dataset.format, tmp, sizeof(out->dataset.format)-1); continue; }
            if (starts_with(raw, "channels:")) { const char *v = raw + strlen("channels:"); while (*v==' ') v++; out->dataset.channels = parse_u32(v); continue; }
            if (starts_with(raw, "sample_rate_hz:")) { const char *v = raw + strlen("sample_rate_hz:"); while (*v==' ') v++; out->dataset.sample_rate_hz = parse_u32(v); continue; }
        }

        if (st == IN_REALTIME) {
            if (starts_with(raw, "scheduler:")) { const char *v = raw + strlen("scheduler:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->realtime.scheduler, tmp, sizeof(out->realtime.scheduler)-1); continue; }
            if (starts_with(raw, "priority:")) { const char *v = raw + strlen("priority:"); while (*v==' ') v++; out->realtime.priority = (int)strtol(v, NULL, 10); continue; }
            if (starts_with(raw, "cpu_affinity:")) {
                /* parse [0,1,2] -> bitmask */
                const char *v = strchr(raw, '[');
                if (v) {
                    v++;
                    uint64_t mask = 0;
                    while (*v && *v != ']') {
                        while (*v==' '||*v==',') v++;
                        if (isdigit((unsigned char)*v)) {
                            int core = (int)strtol(v, (char**)&v, 10);
                            if (core >= 0 && core < 64) mask |= (1ULL << core);
                        } else {
                            v++;
                        }
                    }
                    out->realtime.cpu_affinity_mask = mask;
                }
                continue;
            }
            if (starts_with(raw, "deadline_ms:")) { const char *v = raw + strlen("deadline_ms:"); while (*v==' ') v++; out->realtime.deadline_ms = parse_u32(v); continue; }
        }

        if (st == IN_BENCH) {
            if (starts_with(raw, "load_profile:")) { const char *v = raw + strlen("load_profile:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->benchmark.load_profile, tmp, sizeof(out->benchmark.load_profile)-1); continue; }
            if (strcmp(raw, "parameters:") == 0) { st = IN_BENCH_PARAMS; continue; }
        }
        if (st == IN_BENCH_PARAMS) {
            if (starts_with(raw, "duration_seconds:")) { const char *v = raw + strlen("duration_seconds:"); while (*v==' ') v++; out->benchmark.parameters.duration_seconds = parse_u32(v); continue; }
            if (starts_with(raw, "repeats:")) { const char *v = raw + strlen("repeats:"); while (*v==' ') v++; out->benchmark.parameters.repeats = parse_u32(v); continue; }
            if (starts_with(raw, "warmup_seconds:")) { const char *v = raw + strlen("warmup_seconds:"); while (*v==' ') v++; out->benchmark.parameters.warmup_seconds = parse_u32(v); continue; }
        }

        if (st == IN_OUTPUT) {
            if (starts_with(raw, "directory:")) { const char *v = raw + strlen("directory:"); while (*v==' ') v++; char tmp[512]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->output.directory, tmp, sizeof(out->output.directory)-1); continue; }
            if (starts_with(raw, "format:")) { const char *v = raw + strlen("format:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->output.format, tmp, sizeof(out->output.format)-1); continue; }
            if (starts_with(raw, "include_raw_data:")) { const char *v = raw + strlen("include_raw_data:"); while (*v==' ') v++; out->output.include_raw_data = parse_bool(v); continue; }
        }
    }

    if (st == IN_PLUGIN || st == IN_PLUGIN_RUNTIME) {
        plugin_index++;
    }
    out->plugin_count = plugin_index;

    fclose(f);
    return 0;
}

int cortex_config_validate(const cortex_run_config_t *cfg, char *err, size_t err_sz) {
    if (!cfg) { if (err && err_sz) snprintf(err, err_sz, "null cfg"); return -1; }
    if (cfg->dataset.sample_rate_hz == 0) { if (err && err_sz) snprintf(err, err_sz, "Fs must be > 0"); return -1; }
    if (cfg->dataset.channels == 0) { if (err && err_sz) snprintf(err, err_sz, "C must be > 0"); return -1; }
    for (size_t i = 0; i < cfg->plugin_count; i++) {
        const cortex_plugin_entry_cfg_t *p = &cfg->plugins[i];
        if (p->runtime.hop_samples == 0 || p->runtime.hop_samples > p->runtime.window_length_samples) {
            if (err && err_sz) snprintf(err, err_sz, "plugin %zu invalid hop/window", i);
            return -1;
        }
        if (p->runtime.channels != cfg->dataset.channels) {
            if (err && err_sz) snprintf(err, err_sz, "plugin %zu channels mismatch", i);
            return -1;
        }
    }
    return 0;
}


