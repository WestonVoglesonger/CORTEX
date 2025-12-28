/*
 * CORTEX Kernel Parameter Accessor Implementation
 *
 * Simple key-value parser supporting two formats:
 *  1. YAML-style: "key1: value1\nkey2: value2\n"
 *  2. URL-style:  "key1=value1,key2=value2" or "key1=value1&key2=value2"
 */

#include "cortex_params.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <errno.h>
#include <math.h>

/* Internal helper: find value for key in params string */
static const char* find_value(const char *params, const char *key, char *value_buf, size_t buf_size) {
    if (!params || !key || !value_buf || buf_size == 0) {
        return NULL;
    }

    const size_t key_len = strlen(key);
    const char *p = params;

    while (*p) {
        /* Skip whitespace */
        while (*p && isspace((unsigned char)*p)) p++;
        if (*p == '\0') break;

        /* Check if this line starts with our key */
        if (strncmp(p, key, key_len) == 0) {
            p += key_len;

            /* Skip whitespace after key */
            while (*p && isspace((unsigned char)*p)) p++;

            /* Check for separator: ':' or '=' */
            if (*p == ':' || *p == '=') {
                p++;  /* Skip separator */

                /* Skip whitespace after separator */
                while (*p && isspace((unsigned char)*p)) p++;

                /* Extract value until newline, comma, ampersand, or end */
                size_t i = 0;
                while (*p && *p != '\n' && *p != ',' && *p != '&') {
                    if (i >= buf_size - 1) break;  /* Ensure room for null terminator */
                    value_buf[i++] = *p++;
                }
                value_buf[i] = '\0';

                /* Trim trailing whitespace */
                while (i > 0 && isspace((unsigned char)value_buf[i-1])) {
                    value_buf[--i] = '\0';
                }

                /* Remove quotes if present */
                if (i >= 2 && ((value_buf[0] == '"' && value_buf[i-1] == '"') ||
                               (value_buf[0] == '\'' && value_buf[i-1] == '\''))) {
                    value_buf[i-1] = '\0';
                    memmove(value_buf, value_buf + 1, i - 1);
                }

                return value_buf;
            }
        }

        /* Move to next line or next key-value pair */
        while (*p && *p != '\n' && *p != ',' && *p != '&') p++;
        if (*p) p++;  /* Skip delimiter */
    }

    return NULL;  /* Key not found */
}

/* Get floating-point parameter */
double cortex_param_float(const char *params, const char *key, double default_value) {
    if (!params || !key) {
        return default_value;
    }

    char value_buf[256];
    const char *value_str = find_value(params, key, value_buf, sizeof(value_buf));

    if (!value_str) {
        return default_value;
    }

    /* Parse as double */
    char *endptr = NULL;
    errno = 0;
    double result = strtod(value_str, &endptr);

    /* Check for parse errors */
    if (errno != 0 || endptr == value_str || *endptr != '\0') {
        /* Parse failed, return default */
        return default_value;
    }

    /* Check for NaN or Inf (considered invalid) */
    if (isnan(result) || isinf(result)) {
        return default_value;
    }

    return result;
}

/* Get integer parameter */
int64_t cortex_param_int(const char *params, const char *key, int64_t default_value) {
    if (!params || !key) {
        return default_value;
    }

    char value_buf[256];
    const char *value_str = find_value(params, key, value_buf, sizeof(value_buf));

    if (!value_str) {
        return default_value;
    }

    /* Parse as int64 */
    char *endptr = NULL;
    errno = 0;
    int64_t result = strtoll(value_str, &endptr, 10);

    /* Check for parse errors */
    if (errno != 0 || endptr == value_str || *endptr != '\0') {
        /* Parse failed, return default */
        return default_value;
    }

    return result;
}

/* Get string parameter */
const char* cortex_param_string(const char *params,
                                const char *key,
                                char *buf,
                                size_t buf_size,
                                const char *default_value) {
    if (!buf || buf_size == 0) {
        return default_value;
    }

    if (!params || !key) {
        /* Copy default to buffer */
        if (default_value) {
            strncpy(buf, default_value, buf_size - 1);
            buf[buf_size - 1] = '\0';
            return buf;
        }
        buf[0] = '\0';
        return buf;
    }

    const char *value_str = find_value(params, key, buf, buf_size);

    if (!value_str) {
        /* Key not found, use default */
        if (default_value) {
            strncpy(buf, default_value, buf_size - 1);
            buf[buf_size - 1] = '\0';
            return buf;
        }
        buf[0] = '\0';
        return buf;
    }

    return buf;  /* Value already in buf from find_value */
}

/* Get boolean parameter */
int cortex_param_bool(const char *params, const char *key, int default_value) {
    if (!params || !key) {
        return default_value;
    }

    char value_buf[256];
    const char *value_str = find_value(params, key, value_buf, sizeof(value_buf));

    if (!value_str) {
        return default_value;
    }

    /* Convert to lowercase for case-insensitive comparison */
    char lower_buf[256];
    size_t i;
    for (i = 0; value_str[i] && i < sizeof(lower_buf) - 1; i++) {
        lower_buf[i] = tolower((unsigned char)value_str[i]);
    }
    lower_buf[i] = '\0';

    /* Check for true values */
    if (strcmp(lower_buf, "true") == 0 ||
        strcmp(lower_buf, "yes") == 0 ||
        strcmp(lower_buf, "1") == 0 ||
        strcmp(lower_buf, "on") == 0) {
        return 1;
    }

    /* Check for false values */
    if (strcmp(lower_buf, "false") == 0 ||
        strcmp(lower_buf, "no") == 0 ||
        strcmp(lower_buf, "0") == 0 ||
        strcmp(lower_buf, "off") == 0) {
        return 0;
    }

    /* Unrecognized value, return default */
    return default_value;
}
