#include "config.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <dirent.h>      /* for readdir() */
#include <sys/stat.h>    /* for stat() */
#include <unistd.h>      /* for access() */

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

/* Load kernel spec from spec.yaml and populate runtime config */
int cortex_load_kernel_spec(const char *spec_uri, uint32_t dataset_channels, cortex_plugin_runtime_cfg_t *runtime) {
    if (!spec_uri || !runtime) return -1;

    /* Build spec path: primitives/kernels/v1/{name}@{dtype}/spec.yaml */
    char spec_path[512];
    snprintf(spec_path, sizeof(spec_path), "%s/spec.yaml", spec_uri);

    FILE *f = fopen(spec_path, "r");
    if (!f) {
        /* Spec not found, return defaults based on dataset */
        runtime->window_length_samples = 160;
        runtime->hop_samples = 80;
        runtime->channels = dataset_channels;  /* Use dataset channels */
        runtime->dtype = 1; /* float32 */
        runtime->allow_in_place = 0;
        return 0;
    }

    char line[1024];
    char dtype_str[32] = "";
    uint32_t window_length = 160; /* Default W */

    /* Simple spec parser - look for key fields */
    while (fgets(line, sizeof(line), f)) {
        trim(line);
        if (line[0] == '\0' || line[0] == '#') continue;

        if (starts_with(line, "  dtype:")) {
            const char *v = line + strlen("  dtype:");
            while (*v == ' ') v++;
            char tmp[32]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0';
            trim(tmp); unquote(tmp);
            strncpy(dtype_str, tmp, sizeof(dtype_str)-1);
        }
        else if (starts_with(line, "  input_shape:")) {
            /* Parse [W, null] format - extract W only, ignore C (comes from dataset) */
            const char *v = line + strlen("  input_shape:");
            while (*v == ' ') v++;
            if (*v == '[') {
                v++;
                window_length = (uint32_t)strtoul(v, (char**)&v, 10);
            }
        }
    }

    fclose(f);

    /* Set runtime config from spec, using dataset channels */
    runtime->window_length_samples = window_length;
    runtime->hop_samples = window_length / 2; /* Default: 50% overlap */
    runtime->channels = dataset_channels;     /* Always use dataset channels */
    runtime->dtype = map_dtype(dtype_str[0] ? dtype_str : "float32");
    runtime->allow_in_place = 1; /* Most kernels can be in-place */

    return 0;
}

/* Comparison function for qsort - sort plugins alphabetically by name
 *
 * TODO(Spring 2026 - Quantization): When multiple dtypes exist (f32/q15/q7),
 * this sorting may produce inconsistent ordering across runs. Should implement
 * secondary sort by dtype priority: f32 > q15 > q7.
 * Currently safe because only @f32 variants exist.
 */
static int compare_plugin_names(const void *a, const void *b) {
    const cortex_plugin_entry_cfg_t *pa = (const cortex_plugin_entry_cfg_t *)a;
    const cortex_plugin_entry_cfg_t *pb = (const cortex_plugin_entry_cfg_t *)b;
    return strcmp(pa->name, pb->name);
}

/*
 * Discover built kernels in primitives/kernels/ directory.
 * Scans for v star slash name at dtype directories with built shared libraries.
 * Returns number of kernels discovered (may be 0), or -1 on error.
 */
int cortex_discover_kernels(cortex_run_config_t *cfg) {
    if (!cfg) return -1;

    /* Scan primitives/kernels/ for version directories */
    const char *kernels_base = "primitives/kernels";
    DIR *base_dir = opendir(kernels_base);
    if (!base_dir) {
        fprintf(stderr, "[discovery] warning: cannot open %s\n", kernels_base);
        return 0;  /* Not a fatal error - just no kernels */
    }

    size_t kernel_count = 0;
    struct dirent *version_entry;

    /* Iterate version directories (v1, v2, etc.) */
    while ((version_entry = readdir(base_dir)) != NULL) {
        if (version_entry->d_name[0] == '.') continue;  /* Skip hidden */
        if (version_entry->d_name[0] != 'v') continue;  /* Skip non-version dirs */

        char version_path[512];
        snprintf(version_path, sizeof(version_path), "%s/%s",
                 kernels_base, version_entry->d_name);

        /* Check if it's a directory */
        struct stat st;
        if (stat(version_path, &st) != 0 || !S_ISDIR(st.st_mode)) continue;

        DIR *version_dir = opendir(version_path);
        if (!version_dir) continue;

        struct dirent *kernel_entry;

        /* Iterate kernel@dtype directories */
        while ((kernel_entry = readdir(version_dir)) != NULL) {
            if (kernel_entry->d_name[0] == '.') continue;

            /* Parse {name}@{dtype} format */
            char *at_sign = strchr(kernel_entry->d_name, '@');
            if (!at_sign) continue;

            /* Extract kernel name and dtype */
            size_t name_len = at_sign - kernel_entry->d_name;
            if (name_len == 0 || name_len >= 64) continue;

            char kernel_name[64];
            strncpy(kernel_name, kernel_entry->d_name, name_len);
            kernel_name[name_len] = '\0';

            const char *dtype = at_sign + 1;

            /* Build kernel directory path */
            char kernel_path[768];
            snprintf(kernel_path, sizeof(kernel_path), "%s/%s",
                     version_path, kernel_entry->d_name);

            /* Check if built (has shared library) */
            char lib_path_dylib[900];
            char lib_path_so[900];
            snprintf(lib_path_dylib, sizeof(lib_path_dylib),
                     "%s/lib%s.dylib", kernel_path, kernel_name);
            snprintf(lib_path_so, sizeof(lib_path_so),
                     "%s/lib%s.so", kernel_path, kernel_name);

            int is_built = (access(lib_path_dylib, F_OK) == 0) ||
                          (access(lib_path_so, F_OK) == 0);

            if (!is_built) {
                continue;  /* Skip unbuilt kernels silently for clean output */
            }

            /* Check implementation exists */
            char impl_path[900];
            snprintf(impl_path, sizeof(impl_path), "%s/%s.c",
                     kernel_path, kernel_name);
            if (access(impl_path, F_OK) != 0) {
                continue;  /* Skip if no .c file */
            }

            /* Add to plugin list */
            if (kernel_count >= CORTEX_MAX_PLUGINS) {
                fprintf(stderr, "[discovery] warning: max plugins reached (%d)\n",
                        CORTEX_MAX_PLUGINS);
                closedir(version_dir);
                closedir(base_dir);
                cfg->plugin_count = kernel_count;
                return kernel_count;
            }

            cortex_plugin_entry_cfg_t *plugin = &cfg->plugins[kernel_count];
            memset(plugin, 0, sizeof(*plugin));

            /* Set plugin name */
            strncpy(plugin->name, kernel_name, sizeof(plugin->name) - 1);
            plugin->name[sizeof(plugin->name) - 1] = '\0';

            /* Set status to ready (auto-detected kernels are assumed ready) */
            strncpy(plugin->status, "ready", sizeof(plugin->status) - 1);
            plugin->status[sizeof(plugin->status) - 1] = '\0';

            /* Set spec_uri (kernel directory path) */
            snprintf(plugin->spec_uri, sizeof(plugin->spec_uri), "%s", kernel_path);
            plugin->spec_uri[sizeof(plugin->spec_uri) - 1] = '\0';

            /* Load spec version if spec.yaml exists */
            char spec_path[900];
            snprintf(spec_path, sizeof(spec_path), "%s/spec.yaml", kernel_path);
            FILE *spec_file = fopen(spec_path, "r");
            if (spec_file) {
                /* Simple version extraction from spec.yaml */
                char line[256];
                while (fgets(line, sizeof(line), spec_file)) {
                    if (strstr(line, "version:")) {
                        /* Extract version value */
                        char *colon = strchr(line, ':');
                        if (colon) {
                            const char *v = colon + 1;
                            while (*v == ' ' || *v == '"' || *v == '\'') v++;
                            char tmp[32];
                            strncpy(tmp, v, sizeof(tmp) - 1);
                            tmp[sizeof(tmp) - 1] = '\0';
                            trim(tmp);
                            if (strlen(tmp) > 0 && tmp[0] != '\0') {
                                strncpy(plugin->spec_version, tmp,
                                        sizeof(plugin->spec_version) - 1);
                                plugin->spec_version[sizeof(plugin->spec_version) - 1] = '\0';
                                break;
                            }
                        }
                    }
                }
                fclose(spec_file);
            }

            /* Default spec version if not found */
            if (plugin->spec_version[0] == '\0') {
                strncpy(plugin->spec_version, "1.0.0", sizeof(plugin->spec_version) - 1);
            }

            /* TODO(Spring 2026 - Quantization): Display full {name}@{dtype} instead of
             * just kernel_name to disambiguate when multiple dtypes exist.
             * Currently safe because only @f32 variants exist.
             */
            printf("[discovery] auto-detected kernel: %s (%s) at %s\n",
                   kernel_name, dtype, kernel_path);

            kernel_count++;
        }

        closedir(version_dir);
    }

    closedir(base_dir);

    cfg->plugin_count = kernel_count;

    /* Sort kernels alphabetically for reproducible ordering */
    if (kernel_count > 0) {
        qsort(cfg->plugins, kernel_count, sizeof(cortex_plugin_entry_cfg_t),
              compare_plugin_names);
    }

    return kernel_count;
}

/* Check if next line is indented (peek without consuming) */
static int peek_next_line_indented(FILE *fp) {
    if (!fp) return 0;

    long pos = ftell(fp);
    if (pos < 0) return 0;  /* ftell error */

    char line[1024];
    int is_indented = 0;

    if (fgets(line, sizeof(line), fp)) {
        /* Indented if starts with space or tab */
        is_indented = (line[0] == ' ' || line[0] == '\t');
    }
    /* Else: EOF or error → treat as not indented (is_indented stays 0) */

    /* Restore file position */
    fseek(fp, pos, SEEK_SET);
    return is_indented;
}

/* Strip leading indentation from line (modifies in place) */
static void strip_indent(char *line) {
    if (!line) return;

    char *p = line;
    while (*p == ' ' || *p == '\t') p++;

    if (p != line) {
        memmove(line, p, strlen(p) + 1);
    }
}

int cortex_config_load(const char *path, cortex_run_config_t *out) {
    if (!path || !out) return -1;
    memset(out, 0, sizeof(*out));
    out->auto_detect_kernels = 1;  /* Default to auto-detect mode */

    FILE *f = fopen(path, "r");
    if (!f) return -1;

    char line[1024];
    enum { TOP, IN_DATASET, IN_REALTIME, IN_BENCH, IN_BENCH_PARAMS, IN_OUTPUT, IN_PLUGINS, IN_PLUGIN } st = TOP;
    size_t plugin_index = 0;

    while (fgets(line, sizeof(line), f)) {
        char raw[1024];
        strncpy(raw, line, sizeof(raw)-1); raw[sizeof(raw)-1] = '\0';

        /* Strip inline comments before trimming (YAML standard behavior) */
        char *comment_pos = strchr(raw, '#');
        if (comment_pos) {
            *comment_pos = '\0';
        }

        trim(raw);
        if (raw[0] == '\0') continue;

        if (strcmp(raw, "dataset:") == 0) { st = IN_DATASET; continue; }
        if (strcmp(raw, "realtime:") == 0) { st = IN_REALTIME; continue; }
        if (strcmp(raw, "benchmark:") == 0) { st = IN_BENCH; continue; }
        if (strcmp(raw, "output:") == 0) { st = IN_OUTPUT; continue; }
        if (strcmp(raw, "plugins:") == 0) {
            st = IN_PLUGINS;
            out->auto_detect_kernels = 0;  /* Explicit plugins specified */
            continue;
        }

        if (st == IN_PLUGINS) {
            if (starts_with(raw, "- name:")) {
                if (plugin_index >= CORTEX_MAX_PLUGINS) break;
                memset(&out->plugins[plugin_index], 0, sizeof(out->plugins[plugin_index]));
                const char *v = raw + strlen("- name:");
                while (*v == ' ' ) v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].name, tmp, sizeof(out->plugins[plugin_index].name)-1);
                out->plugins[plugin_index].name[sizeof(out->plugins[plugin_index].name)-1] = '\0';
                st = IN_PLUGIN;
                continue;
            }
        }

        if (st == IN_PLUGIN) {
            if (starts_with(raw, "status:")) {
                const char *v = raw + strlen("status:"); while (*v==' ') v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].status, tmp, sizeof(out->plugins[plugin_index].status)-1);
                out->plugins[plugin_index].status[sizeof(out->plugins[plugin_index].status)-1] = '\0';
                continue;
            }
            if (starts_with(raw, "spec_uri:")) {
                const char *v = raw + strlen("spec_uri:"); while (*v==' ') v++;
                char tmp[256]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].spec_uri, tmp, sizeof(out->plugins[plugin_index].spec_uri)-1);
                out->plugins[plugin_index].spec_uri[sizeof(out->plugins[plugin_index].spec_uri)-1] = '\0';

                /* Note: spec loading deferred until after dataset parsing */
                continue;
            }
            if (starts_with(raw, "spec_version:")) {
                const char *v = raw + strlen("spec_version:"); while (*v==' ') v++;
                char tmp[32]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].spec_version, tmp, sizeof(out->plugins[plugin_index].spec_version)-1);
                out->plugins[plugin_index].spec_version[sizeof(out->plugins[plugin_index].spec_version)-1] = '\0';
                continue;
            }
            if (starts_with(raw, "params:")) {
                /* Parse kernel-specific parameters (supports block-style and inline) */
                const char *rest = raw + strlen("params:");
                while (*rest == ' ') rest++;

                char params_buffer[4096] = {0};

                if (*rest == '\0' || *rest == '\n') {
                    /* Block-style: read subsequent indented lines */
                    while (peek_next_line_indented(f)) {
                        char indented_line[1024];
                        if (!fgets(indented_line, sizeof(indented_line), f)) break;

                        strip_indent(indented_line);

                        /* Remove trailing newline */
                        size_t len = strlen(indented_line);
                        if (len > 0 && indented_line[len-1] == '\n') {
                            indented_line[len-1] = '\0';
                            len--;
                        }

                        /* Skip empty lines and comments */
                        if (len == 0 || indented_line[0] == '#') {
                            continue;
                        }

                        /* Append to buffer with newline separator */
                        size_t current_len = strlen(params_buffer);
                        if (current_len + len + 2 < sizeof(params_buffer)) {
                            if (current_len > 0) {
                                strcat(params_buffer, "\n");
                            }
                            strcat(params_buffer, indented_line);
                        }
                    }
                } else {
                    /* Inline-style: "f0_hz: 50.0, Q: 35.0" */
                    strncpy(params_buffer, rest, sizeof(params_buffer) - 1);
                    params_buffer[sizeof(params_buffer) - 1] = '\0';
                }

                /* Store params */
                trim(params_buffer);
                strncpy(out->plugins[plugin_index].params, params_buffer,
                        sizeof(out->plugins[plugin_index].params) - 1);
                out->plugins[plugin_index].params[sizeof(out->plugins[plugin_index].params) - 1] = '\0';
                continue;
            }
            /* runtime: no longer parsed - loaded from spec.yaml */
            if (starts_with(raw, "- name:")) { /* next plugin */
                plugin_index++;
                if (plugin_index >= CORTEX_MAX_PLUGINS) break;
                memset(&out->plugins[plugin_index], 0, sizeof(out->plugins[plugin_index]));
                const char *v = raw + strlen("- name:"); while (*v==' ') v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].name, tmp, sizeof(out->plugins[plugin_index].name)-1);
                out->plugins[plugin_index].name[sizeof(out->plugins[plugin_index].name)-1] = '\0';
                continue;
            }
        }

            /* Runtime config now loaded from spec.yaml, not YAML */
            if (starts_with(raw, "- name:")) {
                plugin_index++;  /* Move to next plugin slot */
                if (plugin_index >= CORTEX_MAX_PLUGINS) break;
                memset(&out->plugins[plugin_index], 0, sizeof(out->plugins[plugin_index]));
                const char *v = raw + strlen("- name:"); while (*v == ' ') v++;
                char tmp[64]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1] = '\0'; trim(tmp); unquote(tmp);
                strncpy(out->plugins[plugin_index].name, tmp, sizeof(out->plugins[plugin_index].name)-1);
                out->plugins[plugin_index].name[sizeof(out->plugins[plugin_index].name)-1] = '\0';
                st = IN_PLUGIN;  /* Start parsing the new plugin */
                continue;
            }

        if (st == IN_DATASET) {
            if (starts_with(raw, "path:")) { const char *v = raw + strlen("path:"); while (*v==' ') v++; char tmp[512]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->dataset.path, tmp, sizeof(out->dataset.path)-1); out->dataset.path[sizeof(out->dataset.path)-1] = '\0'; continue; }
            if (starts_with(raw, "format:")) { const char *v = raw + strlen("format:"); while (*v==' ') v++; char tmp[32]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->dataset.format, tmp, sizeof(out->dataset.format)-1); out->dataset.format[sizeof(out->dataset.format)-1] = '\0'; continue; }
            if (starts_with(raw, "channels:")) { const char *v = raw + strlen("channels:"); while (*v==' ') v++; out->dataset.channels = parse_u32(v); continue; }
            if (starts_with(raw, "sample_rate_hz:")) { const char *v = raw + strlen("sample_rate_hz:"); while (*v==' ') v++; out->dataset.sample_rate_hz = parse_u32(v); continue; }
        }

        if (st == IN_REALTIME) {
            if (starts_with(raw, "scheduler:")) { const char *v = raw + strlen("scheduler:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->realtime.scheduler, tmp, sizeof(out->realtime.scheduler)-1); out->realtime.scheduler[sizeof(out->realtime.scheduler)-1] = '\0'; continue; }
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
            if (starts_with(raw, "load_profile:")) { const char *v = raw + strlen("load_profile:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->benchmark.load_profile, tmp, sizeof(out->benchmark.load_profile)-1); out->benchmark.load_profile[sizeof(out->benchmark.load_profile)-1] = '\0'; continue; }
            if (strcmp(raw, "parameters:") == 0) { st = IN_BENCH_PARAMS; continue; }
        }
        if (st == IN_BENCH_PARAMS) {
            if (starts_with(raw, "duration_seconds:")) { const char *v = raw + strlen("duration_seconds:"); while (*v==' ') v++; out->benchmark.parameters.duration_seconds = parse_u32(v); continue; }
            if (starts_with(raw, "repeats:")) { const char *v = raw + strlen("repeats:"); while (*v==' ') v++; out->benchmark.parameters.repeats = parse_u32(v); continue; }
            if (starts_with(raw, "warmup_seconds:")) { const char *v = raw + strlen("warmup_seconds:"); while (*v==' ') v++; out->benchmark.parameters.warmup_seconds = parse_u32(v); continue; }
            /* load_profile can appear after parameters block, so parse it here too */
            if (starts_with(raw, "load_profile:")) { const char *v = raw + strlen("load_profile:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->benchmark.load_profile, tmp, sizeof(out->benchmark.load_profile)-1); out->benchmark.load_profile[sizeof(out->benchmark.load_profile)-1] = '\0'; continue; }
        }

        if (st == IN_OUTPUT) {
            if (starts_with(raw, "directory:")) { const char *v = raw + strlen("directory:"); while (*v==' ') v++; char tmp[512]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->output.directory, tmp, sizeof(out->output.directory)-1); out->output.directory[sizeof(out->output.directory)-1] = '\0'; continue; }
            if (starts_with(raw, "format:")) { const char *v = raw + strlen("format:"); while (*v==' ') v++; char tmp[16]; strncpy(tmp, v, sizeof(tmp)-1); tmp[sizeof(tmp)-1]='\0'; trim(tmp); unquote(tmp); strncpy(out->output.format, tmp, sizeof(out->output.format)-1); out->output.format[sizeof(out->output.format)-1] = '\0'; continue; }
            if (starts_with(raw, "include_raw_data:")) { const char *v = raw + strlen("include_raw_data:"); while (*v==' ') v++; out->output.include_raw_data = parse_bool(v); continue; }
        }
    }

    if (st == IN_PLUGIN) {
        plugin_index++;
    }
    out->plugin_count = plugin_index;

    /* Set default output format if not specified */
    if (out->output.format[0] == '\0') {
        strncpy(out->output.format, "ndjson", sizeof(out->output.format) - 1);
        out->output.format[sizeof(out->output.format) - 1] = '\0';
    }

    /* Load kernel specs for all plugins now that we have dataset info */
    for (size_t i = 0; i < out->plugin_count; i++) {
        if (out->plugins[i].spec_uri[0] != '\0') {
            cortex_load_kernel_spec(out->plugins[i].spec_uri, out->dataset.channels, &out->plugins[i].runtime);
        } else {
            /* No spec provided, use defaults */
            out->plugins[i].runtime.window_length_samples = 160;
            out->plugins[i].runtime.hop_samples = 80;
            out->plugins[i].runtime.channels = out->dataset.channels;
            out->plugins[i].runtime.dtype = 1; /* float32 */
            out->plugins[i].runtime.allow_in_place = 0;
        }
    }

    fclose(f);
    return 0;
}

int cortex_config_validate(const cortex_run_config_t *cfg, char *err, size_t err_sz) {
    if (!cfg) { if (err && err_sz) snprintf(err, err_sz, "null cfg"); return -1; }
    if (cfg->dataset.sample_rate_hz == 0) { if (err && err_sz) snprintf(err, err_sz, "Fs must be > 0"); return -1; }
    if (cfg->dataset.channels == 0) { if (err && err_sz) snprintf(err, err_sz, "C must be > 0"); return -1; }

    for (size_t i = 0; i < cfg->plugin_count; i++) {
        const cortex_plugin_entry_cfg_t *p = &cfg->plugins[i];

        /* Check that ready plugins have spec_uri */
        if (strcmp(p->status, "ready") == 0 && strlen(p->spec_uri) == 0) {
            if (err && err_sz) snprintf(err, err_sz, "plugin %zu status=ready but no spec_uri", i);
            return -1;
        }

        /* Validate runtime config from spec */
        if (p->runtime.window_length_samples == 0) {
            if (err && err_sz) snprintf(err, err_sz, "plugin %zu window length must be > 0", i);
            return -1;
        }
        if (p->runtime.hop_samples == 0 || p->runtime.hop_samples > p->runtime.window_length_samples) {
            if (err && err_sz) snprintf(err, err_sz, "plugin %zu invalid hop/window", i);
            return -1;
        }
        if (p->runtime.channels != cfg->dataset.channels) {
            if (err && err_sz) snprintf(err, err_sz, "plugin %zu channels mismatch dataset", i);
            return -1;
        }

        /* Check deadline calculation is valid */
        if (cfg->dataset.sample_rate_hz > 0 && p->runtime.hop_samples > 0) {
            double expected_deadline_ms = 1000.0 * p->runtime.hop_samples / cfg->dataset.sample_rate_hz;
            if (cfg->realtime.deadline_ms > 0 && cfg->realtime.deadline_ms < expected_deadline_ms) {
                if (err && err_sz) snprintf(err, err_sz, "plugin %zu deadline too tight (%.1f ms needed)", i, expected_deadline_ms);
                return -1;
            }
        }
    }
    return 0;
}


