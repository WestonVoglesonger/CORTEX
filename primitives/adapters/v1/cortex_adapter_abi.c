/*
 * CORTEX Adapter ABI Version Implementation
 *
 * This file provides the real (non-inline) cortex_adapter_abi_version()
 * function that harness can discover via dlsym().  It is compiled ONCE
 * at the top level and linked into all adapter shared libraries to avoid
 * build race conditions.
 *
 * Rationale: inline functions in headers may not emit discoverable symbols.
 * By compiling this as a separate object, we guarantee a real exported
 * symbol that dynamic loaders can find.
 *
 * Usage Pattern:
 *   1. Harness loads adapter: dlopen("adapter.so", RTLD_NOW)
 *   2. Harness checks ABI: dlsym(handle, "cortex_adapter_abi_version")
 *   3. If version matches, proceed to cortex_adapter_get_v1()
 *   4. If mismatch, dlclose() and return error
 */

#include "cortex_adapter.h"

uint32_t cortex_adapter_abi_version(void) {
    return CORTEX_ADAPTER_ABI_VERSION;
}
