/*
 * Unit tests for CORTEX parameter accessor library
 */

#include "cortex_params.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <math.h>

/* Test helpers */
#define ASSERT_EQ(a, b) assert((a) == (b))
#define ASSERT_FLOAT_EQ(a, b) assert(fabs((a) - (b)) < 1e-9)
#define ASSERT_STR_EQ(a, b) assert(strcmp((a), (b)) == 0)

/* Test 1: Parse simple floats (YAML style) */
static int test_parse_float_yaml() {
    const char *params = "f0_hz: 60.0\nQ: 30.5\n";

    double f0 = cortex_param_float(params, "f0_hz", 0.0);
    ASSERT_FLOAT_EQ(f0, 60.0);

    double Q = cortex_param_float(params, "Q", 0.0);
    ASSERT_FLOAT_EQ(Q, 30.5);

    /* Missing key should return default */
    double missing = cortex_param_float(params, "missing", 99.9);
    ASSERT_FLOAT_EQ(missing, 99.9);

    printf("[PASS] test_parse_float_yaml\n");
    return 0;
}

/* Test 2: Parse floats (URL style) */
static int test_parse_float_url() {
    const char *params = "f0_hz=60.0,Q=30.5";

    double f0 = cortex_param_float(params, "f0_hz", 0.0);
    ASSERT_FLOAT_EQ(f0, 60.0);

    double Q = cortex_param_float(params, "Q", 0.0);
    ASSERT_FLOAT_EQ(Q, 30.5);

    printf("[PASS] test_parse_float_url\n");
    return 0;
}

/* Test 3: Parse integers (both styles) */
static int test_parse_int() {
    const char *params_yaml = "order: 129\nchannels: 64\n";
    const char *params_url = "order=129,channels=64";

    /* YAML style */
    int64_t order = cortex_param_int(params_yaml, "order", 0);
    ASSERT_EQ(order, 129);

    int64_t channels = cortex_param_int(params_yaml, "channels", 0);
    ASSERT_EQ(channels, 64);

    /* URL style */
    order = cortex_param_int(params_url, "order", 0);
    ASSERT_EQ(order, 129);

    channels = cortex_param_int(params_url, "channels", 0);
    ASSERT_EQ(channels, 64);

    /* Negative integers */
    const char *negative = "value: -42\n";
    int64_t neg = cortex_param_int(negative, "value", 0);
    ASSERT_EQ(neg, -42);

    printf("[PASS] test_parse_int\n");
    return 0;
}

/* Test 4: Parse strings (both styles) */
static int test_parse_string() {
    const char *params_yaml = "window: hamming\nmethod: welch\n";
    const char *params_url = "window=hamming,method=welch";

    char buf[64];

    /* YAML style */
    cortex_param_string(params_yaml, "window", buf, sizeof(buf), "default");
    ASSERT_STR_EQ(buf, "hamming");

    cortex_param_string(params_yaml, "method", buf, sizeof(buf), "default");
    ASSERT_STR_EQ(buf, "welch");

    /* URL style */
    cortex_param_string(params_url, "window", buf, sizeof(buf), "default");
    ASSERT_STR_EQ(buf, "hamming");

    /* Missing key should use default */
    cortex_param_string(params_yaml, "missing", buf, sizeof(buf), "default_value");
    ASSERT_STR_EQ(buf, "default_value");

    /* Quoted strings */
    const char *quoted = "name: \"my kernel\"\n";
    cortex_param_string(quoted, "name", buf, sizeof(buf), "");
    ASSERT_STR_EQ(buf, "my kernel");

    printf("[PASS] test_parse_string\n");
    return 0;
}

/* Test 5: Parse booleans */
static int test_parse_bool() {
    const char *params = "enabled: true\ndisabled: false\nyes_val: yes\nno_val: no\none: 1\nzero: 0\n";

    ASSERT_EQ(cortex_param_bool(params, "enabled", 0), 1);
    ASSERT_EQ(cortex_param_bool(params, "disabled", 1), 0);
    ASSERT_EQ(cortex_param_bool(params, "yes_val", 0), 1);
    ASSERT_EQ(cortex_param_bool(params, "no_val", 1), 0);
    ASSERT_EQ(cortex_param_bool(params, "one", 0), 1);
    ASSERT_EQ(cortex_param_bool(params, "zero", 1), 0);

    /* Case insensitive */
    const char *upper = "flag: TRUE\n";
    ASSERT_EQ(cortex_param_bool(upper, "flag", 0), 1);

    /* Missing key returns default */
    ASSERT_EQ(cortex_param_bool(params, "missing", 42), 42);

    /* Invalid value returns default */
    const char *invalid = "bad: maybe\n";
    ASSERT_EQ(cortex_param_bool(invalid, "bad", 7), 7);

    printf("[PASS] test_parse_bool\n");
    return 0;
}

/* Test 6: Whitespace tolerance */
static int test_whitespace() {
    const char *params = "  key1  :  value1  \n  key2:value2\nkey3 : value3\n";

    char buf[64];
    cortex_param_string(params, "key1", buf, sizeof(buf), "");
    ASSERT_STR_EQ(buf, "value1");

    cortex_param_string(params, "key2", buf, sizeof(buf), "");
    ASSERT_STR_EQ(buf, "value2");

    cortex_param_string(params, "key3", buf, sizeof(buf), "");
    ASSERT_STR_EQ(buf, "value3");

    printf("[PASS] test_whitespace\n");
    return 0;
}

/* Test 7: Scientific notation for floats */
static int test_scientific_notation() {
    const char *params = "small: 1.5e-5\nlarge: 3.2e10\n";

    double small = cortex_param_float(params, "small", 0.0);
    ASSERT_FLOAT_EQ(small, 1.5e-5);

    double large = cortex_param_float(params, "large", 0.0);
    ASSERT_FLOAT_EQ(large, 3.2e10);

    printf("[PASS] test_scientific_notation\n");
    return 0;
}

/* Test 8: NULL and empty params handling */
static int test_null_empty() {
    /* NULL params should return defaults */
    double f = cortex_param_float(NULL, "key", 123.45);
    ASSERT_FLOAT_EQ(f, 123.45);

    int64_t i = cortex_param_int(NULL, "key", 999);
    ASSERT_EQ(i, 999);

    char buf[64];
    cortex_param_string(NULL, "key", buf, sizeof(buf), "default");
    ASSERT_STR_EQ(buf, "default");

    int b = cortex_param_bool(NULL, "key", 1);
    ASSERT_EQ(b, 1);

    /* Empty params should return defaults */
    f = cortex_param_float("", "key", 123.45);
    ASSERT_FLOAT_EQ(f, 123.45);

    printf("[PASS] test_null_empty\n");
    return 0;
}

/* Test 9: Multiple separators (commas and ampersands) */
static int test_multiple_separators() {
    const char *params1 = "a=1,b=2,c=3";
    const char *params2 = "a=1&b=2&c=3";

    ASSERT_EQ(cortex_param_int(params1, "a", 0), 1);
    ASSERT_EQ(cortex_param_int(params1, "b", 0), 2);
    ASSERT_EQ(cortex_param_int(params1, "c", 0), 3);

    ASSERT_EQ(cortex_param_int(params2, "a", 0), 1);
    ASSERT_EQ(cortex_param_int(params2, "b", 0), 2);
    ASSERT_EQ(cortex_param_int(params2, "c", 0), 3);

    printf("[PASS] test_multiple_separators\n");
    return 0;
}

/* Test 10: Invalid float/int handling */
static int test_invalid_numbers() {
    const char *params = "bad_float: not_a_number\nbad_int: xyz\n";

    /* Invalid values should return defaults */
    double f = cortex_param_float(params, "bad_float", 42.0);
    ASSERT_FLOAT_EQ(f, 42.0);

    int64_t i = cortex_param_int(params, "bad_int", 99);
    ASSERT_EQ(i, 99);

    printf("[PASS] test_invalid_numbers\n");
    return 0;
}

/* Main test runner */
int main() {
    printf("Running CORTEX parameter accessor tests...\n");
    printf("==========================================\n\n");

    test_parse_float_yaml();
    test_parse_float_url();
    test_parse_int();
    test_parse_string();
    test_parse_bool();
    test_whitespace();
    test_scientific_notation();
    test_null_empty();
    test_multiple_separators();
    test_invalid_numbers();

    printf("\n==========================================\n");
    printf("All tests passed! (10/10)\n");

    return 0;
}
