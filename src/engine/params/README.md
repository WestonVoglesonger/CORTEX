# CORTEX Kernel Parameter Accessor Library

Generic, type-safe API for kernels to extract runtime parameters from YAML configuration strings.

## Overview

The parameter accessor library provides a clean interface for kernels to receive runtime configuration without coupling the harness to kernel-specific schemas. Parameters are passed as simple key-value strings and parsed on-demand using typed accessor functions.

## Architecture

```
YAML Config → Harness (passes raw string) → Kernel (uses accessor API)
```

- **Harness**: Parses YAML, extracts params as string, passes via `kernel_params` pointer
- **Accessor Library**: Provides typed functions to extract values from string
- **Kernels**: Call accessor functions with key names and defaults

## Usage in Kernels

### 1. Include Header

```c
#include "cortex_plugin.h"
#include "accessor.h"
```

### 2. Extract Parameters in `cortex_init()`

```c
cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    /* Extract params string from config */
    const char *params = (const char *)config->kernel_params;

    /* Use typed accessor functions with defaults */
    double f0_hz = cortex_param_float(params, "f0_hz", 60.0);
    int order = cortex_param_int(params, "order", 129);

    char window[32];
    cortex_param_string(params, "window", window, sizeof(window), "hamming");

    int enabled = cortex_param_bool(params, "enabled", 1);

    /* Use parameters to initialize kernel state... */
}
```

### 3. Link Against Params Library

Update kernel Makefile:

```makefile
CFLAGS = -Wall -Wextra -O2 -g -fPIC -I../../../../src/engine/include -I../../../../src/engine/params
PARAMS_LIB = ../../../../src/engine/params/libcortex_params.a

$(PLUGIN_LIB): $(PLUGIN_OBJ) $(PARAMS_LIB)
	$(CC) $(SOFLAG) -o $@ $(PLUGIN_OBJ) $(PARAMS_LIB) -lm
```

## Supported Parameter Formats

The accessor library supports two formats:

### YAML-Style (Recommended)

```yaml
params:
  f0_hz: 60.0
  Q: 30.0
  enabled: true
  window: hamming
```

Passed as: `"f0_hz: 60.0\nQ: 30.0\nenabled: true\nwindow: hamming\n"`

### URL-Style

```yaml
params: "f0_hz=60.0,Q=30.0,enabled=true,window=hamming"
```

Both formats are equivalent and parsed identically.

## API Reference

### `cortex_param_float()`

```c
double cortex_param_float(const char *params, const char *key, double default_value);
```

Extract floating-point parameter. Returns `default_value` if key not found or unparseable.

**Example:**
```c
double cutoff_hz = cortex_param_float(params, "cutoff_hz", 30.0);
```

**Supports:**
- Scientific notation: `1.5e-5`, `3.2e10`
- Negative values: `-42.5`
- Integer-like values: `60` (parsed as `60.0`)

---

### `cortex_param_int()`

```c
int64_t cortex_param_int(const char *params, const char *key, int64_t default_value);
```

Extract integer parameter. Returns `default_value` if key not found or unparseable.

**Example:**
```c
int64_t order = cortex_param_int(params, "order", 129);
```

**Supports:**
- Positive integers: `42`
- Negative integers: `-10`
- Large values: Up to `INT64_MAX` / `INT64_MIN`

---

### `cortex_param_string()`

```c
const char* cortex_param_string(const char *params, const char *key,
                                char *buf, size_t buf_size,
                                const char *default_value);
```

Extract string parameter into user-provided buffer. Returns pointer to `buf` on success, with `default_value` copied if key not found.

**Example:**
```c
char method[64];
cortex_param_string(params, "method", method, sizeof(method), "welch");
// method now contains "welch" (or value from params)
```

**Supports:**
- Quoted strings: `"my value"` or `'my value'` (quotes removed)
- Unquoted strings: `hamming`
- Whitespace trimming

---

### `cortex_param_bool()`

```c
int cortex_param_bool(const char *params, const char *key, int default_value);
```

Extract boolean parameter. Returns `1` for true, `0` for false, `default_value` if key not found or unparseable.

**Example:**
```c
int enabled = cortex_param_bool(params, "enabled", 1);
```

**Recognizes (case-insensitive):**
- **True**: `true`, `yes`, `1`, `on`
- **False**: `false`, `no`, `0`, `off`

---

## Example: notch_iir Kernel

**YAML Configuration:**

```yaml
plugins:
  - name: "notch_iir"
    spec_uri: "primitives/kernels/v1/notch_iir@f32"
    params:
      f0_hz: 50.0  # European power line (50Hz)
      Q: 35.0      # Quality factor
```

**Kernel Code:**

```c
/* Default parameters */
#define DEFAULT_NOTCH_F0_HZ 60.0
#define DEFAULT_NOTCH_Q 30.0

cortex_init_result_t cortex_init(const cortex_plugin_config_t *config) {
    /* ... ABI validation ... */

    /* Parse parameters */
    const char *params_str = (const char *)config->kernel_params;
    double f0_hz = cortex_param_float(params_str, "f0_hz", DEFAULT_NOTCH_F0_HZ);
    double Q = cortex_param_float(params_str, "Q", DEFAULT_NOTCH_Q);

    /* Use f0_hz and Q to compute filter coefficients */
    compute_notch_coefficients(f0_hz, Q, config->sample_rate_hz, ...);

    /* ... rest of initialization ... */
}
```

**Behavior:**
- If `params` provided with `f0_hz=50.0` → uses 50Hz
- If `params` empty or NULL → uses default 60Hz
- If `params` has `f0_hz=xyz` (invalid) → uses default 60Hz

## Design Principles

1. **Zero Coupling**: Accessor library knows nothing about specific kernels
2. **Type Safety**: Compile-time type checking via typed functions
3. **Default Values**: Always return valid values (never crash on missing params)
4. **Error Tolerance**: Gracefully handle malformed input
5. **No Heap Allocation**: Accessor functions use stack only
6. **Thread-Safe**: Read-only operations on input string

## Implementation Details

- **Language**: Pure C11 with standard library only
- **Dependencies**: None (stdlib, string.h, ctype.h)
- **Binary Size**: ~10 KB (libcortex_params.a)
- **Performance**: O(n) string scan per key lookup (n = params string length)

## Testing

Unit tests cover all accessor functions with various input formats:

```bash
cd tests
make test-param-accessor
```

Expected output:
```
[PASS] test_parse_float_yaml
[PASS] test_parse_float_url
[PASS] test_parse_int
[PASS] test_parse_string
[PASS] test_parse_bool
[PASS] test_whitespace
[PASS] test_scientific_notation
[PASS] test_null_empty
[PASS] test_multiple_separators
[PASS] test_invalid_numbers

All tests passed! (10/10)
```

## Future Enhancements

Potential additions (deferred to maintain simplicity):

- **Array parameters**: `bands: [8, 13, 13, 30]` → `cortex_param_array_float()`
- **Nested structures**: `filter: { type: iir, order: 4 }`
- **Parameter validation**: Min/max ranges, allowed values
- **Better error messages**: Report line numbers, invalid types

For now, keep parameters flat and simple. Complex configurations can be handled via multiple parameters or alternative approaches.

## References

- **ABI Specification**: `src/engine/include/cortex_plugin.h`
- **Unit Tests**: `tests/test_param_accessor.c`
- **Example Usage**: `primitives/kernels/v1/notch_iir@f32/notch_iir.c`
- **Config Format**: `docs/reference/configuration.md`
