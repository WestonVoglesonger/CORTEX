#include <string.h>
#include <stdio.h>

#ifdef __APPLE__
#include <sys/sysctl.h>
#include <sys/utsname.h>
#elif __linux__
#include <sys/utsname.h>
#endif

/*
 * cortex_get_device_hostname - Get device hostname
 *
 * Args:
 *   out_hostname: Buffer to store hostname (must be [32] bytes)
 */
void cortex_get_device_hostname(char *out_hostname) {
    struct utsname uts;
    if (uname(&uts) == 0) {
        snprintf(out_hostname, 32, "%s", uts.nodename);
    } else {
        snprintf(out_hostname, 32, "unknown");
    }
    out_hostname[31] = '\0';
}

/*
 * cortex_get_device_cpu - Get device CPU description
 *
 * Args:
 *   out_cpu: Buffer to store CPU info (must be [32] bytes)
 */
void cortex_get_device_cpu(char *out_cpu) {
#ifdef __APPLE__
    char brand[64];
    size_t size = sizeof(brand);
    if (sysctlbyname("machdep.cpu.brand_string", brand, &size, NULL, 0) == 0) {
        snprintf(out_cpu, 32, "%s", brand);
    } else {
        snprintf(out_cpu, 32, "Apple Silicon");
    }
#elif __linux__
    /* Try to read from /proc/cpuinfo */
    FILE *fp = fopen("/proc/cpuinfo", "r");
    if (fp) {
        char line[256];
        int found = 0;
        while (fgets(line, sizeof(line), fp)) {
            if (strncmp(line, "model name", 10) == 0) {
                char *colon = strchr(line, ':');
                if (colon) {
                    colon++;  /* Skip ':' */
                    while (*colon == ' ' || *colon == '\t') colon++;  /* Skip whitespace */
                    /* Remove trailing newline */
                    char *newline = strchr(colon, '\n');
                    if (newline) *newline = '\0';
                    snprintf(out_cpu, 32, "%s", colon);
                    found = 1;
                    break;
                }
            }
            /* ARM devices might have "Hardware" instead */
            if (strncmp(line, "Hardware", 8) == 0) {
                char *colon = strchr(line, ':');
                if (colon) {
                    colon++;
                    while (*colon == ' ' || *colon == '\t') colon++;
                    char *newline = strchr(colon, '\n');
                    if (newline) *newline = '\0';
                    snprintf(out_cpu, 32, "%s", colon);
                    found = 1;
                    break;
                }
            }
        }
        fclose(fp);
        if (!found) {
            struct utsname uts;
            if (uname(&uts) == 0) {
                snprintf(out_cpu, 32, "%s", uts.machine);
            } else {
                snprintf(out_cpu, 32, "unknown");
            }
        }
    } else {
        snprintf(out_cpu, 32, "unknown");
    }
#else
    snprintf(out_cpu, 32, "unknown");
#endif
    out_cpu[31] = '\0';
}

/*
 * cortex_get_device_os - Get device OS description
 *
 * Args:
 *   out_os: Buffer to store OS info (must be [32] bytes)
 */
void cortex_get_device_os(char *out_os) {
    struct utsname uts;
    if (uname(&uts) == 0) {
        snprintf(out_os, 32, "%s %s", uts.sysname, uts.release);
    } else {
        snprintf(out_os, 32, "unknown");
    }
    out_os[31] = '\0';
}
