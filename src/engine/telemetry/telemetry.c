#define _DEFAULT_SOURCE  /* For gethostname on Linux */
#define _POSIX_C_SOURCE 200112L

#ifdef __APPLE__
#define _DARWIN_C_SOURCE  /* For BSD types (u_int, u_char, etc.) on macOS */
#endif

#include "telemetry.h"
#include "../harness/util/util.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/utsname.h>

#ifdef __APPLE__
#include <sys/sysctl.h>
#endif

#ifdef __linux__
#include <sys/sysinfo.h>
#endif

int cortex_telemetry_init(cortex_telemetry_buffer_t *tb, size_t initial_capacity) {
    if (!tb) return -1;
    memset(tb, 0, sizeof(*tb));
    if (initial_capacity == 0) initial_capacity = 1024;
    tb->records = (cortex_telemetry_record_t *)calloc(initial_capacity, sizeof(*tb->records));
    if (!tb->records) return -1;
    tb->capacity = initial_capacity;
    tb->count = 0;
    return 0;
}

void cortex_telemetry_free(cortex_telemetry_buffer_t *tb) {
    if (!tb) return;
    free(tb->records);
    memset(tb, 0, sizeof(*tb));
}

int cortex_telemetry_add(cortex_telemetry_buffer_t *tb, const cortex_telemetry_record_t *rec) {
    if (!tb || !rec) return -1;
    if (tb->count >= tb->capacity) {
        /* Check for overflow in capacity doubling */
        size_t new_cap, alloc_size;
        if (cortex_mul_size_overflow(tb->capacity, 2, &new_cap)) {
            fprintf(stderr, "[telemetry] Integer overflow: capacity=%zu * 2 exceeds SIZE_MAX\n", tb->capacity);
            errno = EOVERFLOW;
            return -1;
        }
        /* Check for overflow in allocation size calculation */
        if (cortex_mul_size_overflow(new_cap, sizeof(*tb->records), &alloc_size)) {
            fprintf(stderr, "[telemetry] Integer overflow: new_cap=%zu * sizeof(record)=%zu exceeds SIZE_MAX\n",
                    new_cap, sizeof(*tb->records));
            errno = EOVERFLOW;
            return -1;
        }

        cortex_telemetry_record_t *new_recs = (cortex_telemetry_record_t *)realloc(tb->records, alloc_size);
        if (!new_recs) return -1;
        tb->records = new_recs;
        tb->capacity = new_cap;
    }
    tb->records[tb->count++] = *rec;
    return 0;
}

int cortex_telemetry_write_csv(const char *path, const cortex_telemetry_buffer_t *tb,
                                 const cortex_system_info_t *sysinfo) {
    if (!path || !tb) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;

    /* Write system info as comment header */
    if (sysinfo) {
        fprintf(f, "# System Information\n");
        fprintf(f, "# OS: %s\n", sysinfo->os);
        fprintf(f, "# CPU: %s\n", sysinfo->cpu_model);
        fprintf(f, "# Hostname: %s\n", sysinfo->hostname);
        fprintf(f, "# CPU Cores: %u\n", sysinfo->cpu_count);
        fprintf(f, "# Total RAM: %llu MB\n", (unsigned long long)sysinfo->total_ram_mb);
        if (sysinfo->thermal_celsius >= 0.0f) {
            fprintf(f, "# Thermal: %.1f°C\n", sysinfo->thermal_celsius);
        } else {
            fprintf(f, "# Thermal: unavailable\n");
        }
        fprintf(f, "#\n");
    }

    fprintf(f, "run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat,device_tin_ns,device_tstart_ns,device_tend_ns,device_tfirst_tx_ns,device_tlast_tx_ns,adapter_name,window_failed,error_code\n");
    for (size_t i = 0; i < tb->count; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];
        fprintf(f, "%s,%s,%u,%llu,%llu,%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%llu,%llu,%llu,%llu,%llu,%s,%u,%d\n",
                r->run_id,
                r->plugin_name,
                r->window_index,
                (unsigned long long)r->release_ts_ns,
                (unsigned long long)r->deadline_ts_ns,
                (unsigned long long)r->start_ts_ns,
                (unsigned long long)r->end_ts_ns,
                (unsigned)r->deadline_missed,
                r->W, r->H, r->C, r->Fs,
                (unsigned)r->warmup,
                r->repeat,
                (unsigned long long)r->device_tin_ns,
                (unsigned long long)r->device_tstart_ns,
                (unsigned long long)r->device_tend_ns,
                (unsigned long long)r->device_tfirst_tx_ns,
                (unsigned long long)r->device_tlast_tx_ns,
                r->adapter_name,
                (unsigned)r->window_failed,
                r->error_code);
    }
    fclose(f);
    return 0;
}

int cortex_telemetry_write_csv_filtered(const char *path, const cortex_telemetry_buffer_t *tb,
                                         size_t start_idx, size_t end_idx,
                                         const cortex_system_info_t *sysinfo) {
    if (!path || !tb) return -1;
    if (start_idx > end_idx || end_idx > tb->count) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;

    /* Write system info as comment header */
    if (sysinfo) {
        fprintf(f, "# System Information\n");
        fprintf(f, "# OS: %s\n", sysinfo->os);
        fprintf(f, "# CPU: %s\n", sysinfo->cpu_model);
        fprintf(f, "# Hostname: %s\n", sysinfo->hostname);
        fprintf(f, "# CPU Cores: %u\n", sysinfo->cpu_count);
        fprintf(f, "# Total RAM: %llu MB\n", (unsigned long long)sysinfo->total_ram_mb);
        if (sysinfo->thermal_celsius >= 0.0f) {
            fprintf(f, "# Thermal: %.1f°C\n", sysinfo->thermal_celsius);
        } else {
            fprintf(f, "# Thermal: unavailable\n");
        }
        fprintf(f, "#\n");
    }

    fprintf(f, "run_id,plugin,window_index,release_ts_ns,deadline_ts_ns,start_ts_ns,end_ts_ns,deadline_missed,W,H,C,Fs,warmup,repeat,device_tin_ns,device_tstart_ns,device_tend_ns,device_tfirst_tx_ns,device_tlast_tx_ns,adapter_name,window_failed,error_code\n");
    for (size_t i = start_idx; i < end_idx; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];
        fprintf(f, "%s,%s,%u,%llu,%llu,%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%llu,%llu,%llu,%llu,%llu,%s,%u,%d\n",
                r->run_id,
                r->plugin_name,
                r->window_index,
                (unsigned long long)r->release_ts_ns,
                (unsigned long long)r->deadline_ts_ns,
                (unsigned long long)r->start_ts_ns,
                (unsigned long long)r->end_ts_ns,
                (unsigned)r->deadline_missed,
                r->W, r->H, r->C, r->Fs,
                (unsigned)r->warmup,
                r->repeat,
                (unsigned long long)r->device_tin_ns,
                (unsigned long long)r->device_tstart_ns,
                (unsigned long long)r->device_tend_ns,
                (unsigned long long)r->device_tfirst_tx_ns,
                (unsigned long long)r->device_tlast_tx_ns,
                r->adapter_name,
                (unsigned)r->window_failed,
                r->error_code);
    }
    fclose(f);
    return 0;
}

/* Helper: Escape JSON string characters (", \, control chars) */
static void json_escape_string(char *dest, size_t dest_size, const char *src) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j < dest_size - 2; i++) {
        if (src[i] == '"' || src[i] == '\\') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = src[i];
            }
        } else if (src[i] == '\n') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = 'n';
            }
        } else if (src[i] == '\r') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = 'r';
            }
        } else if (src[i] == '\t') {
            if (j < dest_size - 3) {
                dest[j++] = '\\';
                dest[j++] = 't';
            }
        } else if ((unsigned char)src[i] < 32) {
            /* Skip other control characters */
            continue;
        } else {
            dest[j++] = src[i];
        }
    }
    dest[j] = '\0';
}

int cortex_telemetry_write_ndjson(const char *path, const cortex_telemetry_buffer_t *tb,
                                    const cortex_system_info_t *sysinfo) {
    if (!path || !tb) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;

    /* Write system info as first NDJSON line (metadata) */
    if (sysinfo) {
        char os_esc[128], cpu_esc[256], hostname_esc[128];
        json_escape_string(os_esc, sizeof(os_esc), sysinfo->os);
        json_escape_string(cpu_esc, sizeof(cpu_esc), sysinfo->cpu_model);
        json_escape_string(hostname_esc, sizeof(hostname_esc), sysinfo->hostname);

        fprintf(f, "{\"_type\":\"system_info\","
                   "\"os\":\"%s\","
                   "\"cpu\":\"%s\","
                   "\"hostname\":\"%s\","
                   "\"cpu_count\":%u,"
                   "\"total_ram_mb\":%llu",
                os_esc, cpu_esc, hostname_esc,
                sysinfo->cpu_count,
                (unsigned long long)sysinfo->total_ram_mb);

        if (sysinfo->thermal_celsius >= 0.0f) {
            fprintf(f, ",\"thermal_celsius\":%.1f}\n", sysinfo->thermal_celsius);
        } else {
            fprintf(f, ",\"thermal_celsius\":null}\n");
        }
    }

    char run_id_esc[128], plugin_esc[256], adapter_name_esc[64];

    /* Write each record as one JSON object per line (NDJSON format) */
    for (size_t i = 0; i < tb->count; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];

        /* Escape string fields for JSON */
        json_escape_string(run_id_esc, sizeof(run_id_esc), r->run_id);
        json_escape_string(plugin_esc, sizeof(plugin_esc), r->plugin_name);
        json_escape_string(adapter_name_esc, sizeof(adapter_name_esc), r->adapter_name);

        /* Write JSON object (compact, one line per record) */
        fprintf(f,
            "{\"run_id\":\"%s\","
            "\"plugin\":\"%s\","
            "\"window_index\":%u,"
            "\"release_ts_ns\":%llu,"
            "\"deadline_ts_ns\":%llu,"
            "\"start_ts_ns\":%llu,"
            "\"end_ts_ns\":%llu,"
            "\"deadline_missed\":%u,"
            "\"W\":%u,"
            "\"H\":%u,"
            "\"C\":%u,"
            "\"Fs\":%u,"
            "\"warmup\":%u,"
            "\"repeat\":%u,"
            "\"device_tin_ns\":%llu,"
            "\"device_tstart_ns\":%llu,"
            "\"device_tend_ns\":%llu,"
            "\"device_tfirst_tx_ns\":%llu,"
            "\"device_tlast_tx_ns\":%llu,"
            "\"adapter_name\":\"%s\","
            "\"window_failed\":%u,"
            "\"error_code\":%d}\n",
            run_id_esc,
            plugin_esc,
            r->window_index,
            (unsigned long long)r->release_ts_ns,
            (unsigned long long)r->deadline_ts_ns,
            (unsigned long long)r->start_ts_ns,
            (unsigned long long)r->end_ts_ns,
            (unsigned)r->deadline_missed,
            r->W, r->H, r->C, r->Fs,
            (unsigned)r->warmup,
            r->repeat,
            (unsigned long long)r->device_tin_ns,
            (unsigned long long)r->device_tstart_ns,
            (unsigned long long)r->device_tend_ns,
            (unsigned long long)r->device_tfirst_tx_ns,
            (unsigned long long)r->device_tlast_tx_ns,
            adapter_name_esc,
            (unsigned)r->window_failed,
            r->error_code);
    }

    fclose(f);
    return 0;
}

int cortex_telemetry_write_ndjson_filtered(const char *path, const cortex_telemetry_buffer_t *tb,
                                            size_t start_idx, size_t end_idx,
                                            const cortex_system_info_t *sysinfo) {
    if (!path || !tb) return -1;
    if (start_idx > end_idx || end_idx > tb->count) return -1;

    /* Create parent directories */
    if (cortex_create_directories(path) != 0) {
        return -1;
    }

    FILE *f = fopen(path, "w");
    if (!f) return -1;

    /* Write system info as first NDJSON line (metadata) */
    if (sysinfo) {
        char os_esc[128], cpu_esc[256], hostname_esc[128];
        json_escape_string(os_esc, sizeof(os_esc), sysinfo->os);
        json_escape_string(cpu_esc, sizeof(cpu_esc), sysinfo->cpu_model);
        json_escape_string(hostname_esc, sizeof(hostname_esc), sysinfo->hostname);

        fprintf(f, "{\"_type\":\"system_info\","
                   "\"os\":\"%s\","
                   "\"cpu\":\"%s\","
                   "\"hostname\":\"%s\","
                   "\"cpu_count\":%u,"
                   "\"total_ram_mb\":%llu",
                os_esc, cpu_esc, hostname_esc,
                sysinfo->cpu_count,
                (unsigned long long)sysinfo->total_ram_mb);

        if (sysinfo->thermal_celsius >= 0.0f) {
            fprintf(f, ",\"thermal_celsius\":%.1f}\n", sysinfo->thermal_celsius);
        } else {
            fprintf(f, ",\"thermal_celsius\":null}\n");
        }
    }

    char run_id_esc[128], plugin_esc[256], adapter_name_esc[64];

    /* Write only records in range [start_idx, end_idx) */
    for (size_t i = start_idx; i < end_idx; i++) {
        const cortex_telemetry_record_t *r = &tb->records[i];

        /* Escape string fields for JSON */
        json_escape_string(run_id_esc, sizeof(run_id_esc), r->run_id);
        json_escape_string(plugin_esc, sizeof(plugin_esc), r->plugin_name);
        json_escape_string(adapter_name_esc, sizeof(adapter_name_esc), r->adapter_name);

        /* Write JSON object (compact, one line per record) */
        fprintf(f,
            "{\"run_id\":\"%s\","
            "\"plugin\":\"%s\","
            "\"window_index\":%u,"
            "\"release_ts_ns\":%llu,"
            "\"deadline_ts_ns\":%llu,"
            "\"start_ts_ns\":%llu,"
            "\"end_ts_ns\":%llu,"
            "\"deadline_missed\":%u,"
            "\"W\":%u,"
            "\"H\":%u,"
            "\"C\":%u,"
            "\"Fs\":%u,"
            "\"warmup\":%u,"
            "\"repeat\":%u,"
            "\"device_tin_ns\":%llu,"
            "\"device_tstart_ns\":%llu,"
            "\"device_tend_ns\":%llu,"
            "\"device_tfirst_tx_ns\":%llu,"
            "\"device_tlast_tx_ns\":%llu,"
            "\"adapter_name\":\"%s\","
            "\"window_failed\":%u,"
            "\"error_code\":%d}\n",
            run_id_esc,
            plugin_esc,
            r->window_index,
            (unsigned long long)r->release_ts_ns,
            (unsigned long long)r->deadline_ts_ns,
            (unsigned long long)r->start_ts_ns,
            (unsigned long long)r->end_ts_ns,
            (unsigned)r->deadline_missed,
            r->W, r->H, r->C, r->Fs,
            (unsigned)r->warmup,
            r->repeat,
            (unsigned long long)r->device_tin_ns,
            (unsigned long long)r->device_tstart_ns,
            (unsigned long long)r->device_tend_ns,
            (unsigned long long)r->device_tfirst_tx_ns,
            (unsigned long long)r->device_tlast_tx_ns,
            adapter_name_esc,
            (unsigned)r->window_failed,
            r->error_code);
    }

    fclose(f);
    return 0;
}

/* Collect system information for telemetry metadata */
int cortex_collect_system_info(cortex_system_info_t *info) {
    if (!info) return -1;
    memset(info, 0, sizeof(*info));

    /* Get OS info using uname */
    struct utsname uts;
    if (uname(&uts) == 0) {
        snprintf(info->os, sizeof(info->os), "%s %s", uts.sysname, uts.release);
    } else {
        snprintf(info->os, sizeof(info->os), "Unknown");
    }

    /* Get hostname */
    if (gethostname(info->hostname, sizeof(info->hostname)) != 0) {
        snprintf(info->hostname, sizeof(info->hostname), "unknown");
    } else {
        /* Ensure NUL-termination per POSIX (defensive) */
        info->hostname[sizeof(info->hostname) - 1] = '\0';
    }

    /* Platform-specific system info */
#ifdef __APPLE__
    /* macOS: Get CPU model and count using sysctl */
    size_t len = sizeof(info->cpu_model);
    if (sysctlbyname("machdep.cpu.brand_string", info->cpu_model, &len, NULL, 0) != 0) {
        snprintf(info->cpu_model, sizeof(info->cpu_model), "Unknown");
    }

    int cpu_count_val = 0;
    size_t cpu_count_size = sizeof(cpu_count_val);
    if (sysctlbyname("hw.ncpu", &cpu_count_val, &cpu_count_size, NULL, 0) == 0) {
        info->cpu_count = (uint32_t)cpu_count_val;
    }

    uint64_t memsize = 0;
    size_t memsize_len = sizeof(memsize);
    if (sysctlbyname("hw.memsize", &memsize, &memsize_len, NULL, 0) == 0) {
        info->total_ram_mb = (uint64_t)(memsize / (1024 * 1024));
    }

    /* Thermal reading - not easily available on macOS without IOKit */
    info->thermal_celsius = -1.0f;

#elif defined(__linux__)
    /* Linux: Get CPU model from /proc/cpuinfo */
    FILE *cpuinfo = fopen("/proc/cpuinfo", "r");
    if (cpuinfo) {
        char line[256];
        while (fgets(line, sizeof(line), cpuinfo)) {
            if (strncmp(line, "model name", 10) == 0) {
                char *colon = strchr(line, ':');
                if (colon) {
                    colon++;
                    while (*colon == ' ' || *colon == '\t') colon++;
                    /* Remove trailing newline */
                    size_t model_len = strlen(colon);
                    if (model_len > 0 && colon[model_len - 1] == '\n') {
                        colon[model_len - 1] = '\0';
                    }
                    snprintf(info->cpu_model, sizeof(info->cpu_model), "%s", colon);
                }
                break;
            }
        }
        fclose(cpuinfo);
    }
    if (info->cpu_model[0] == '\0') {
        snprintf(info->cpu_model, sizeof(info->cpu_model), "Unknown");
    }

    /* CPU count */
    long cpu_count = sysconf(_SC_NPROCESSORS_ONLN);
    if (cpu_count > 0 && cpu_count <= UINT32_MAX) {
        info->cpu_count = (uint32_t)cpu_count;
    } else {
        info->cpu_count = 0;  /* Mark as unknown on error */
    }

    /* Memory info */
    struct sysinfo si;
    if (sysinfo(&si) == 0) {
        info->total_ram_mb = (uint64_t)((si.totalram * si.mem_unit) / (1024 * 1024));
    }

    /* Thermal reading from thermal zone */
    FILE *thermal = fopen("/sys/class/thermal/thermal_zone0/temp", "r");
    if (thermal) {
        int temp_millicelsius = 0;
        if (fscanf(thermal, "%d", &temp_millicelsius) == 1) {
            info->thermal_celsius = (float)temp_millicelsius / 1000.0f;
        }
        fclose(thermal);
    } else {
        info->thermal_celsius = -1.0f;
    }

#else
    /* Unsupported platform */
    snprintf(info->cpu_model, sizeof(info->cpu_model), "Unknown");
    info->cpu_count = 0;
    info->total_ram_mb = 0;
    info->thermal_celsius = -1.0f;
#endif

    return 0;
}


