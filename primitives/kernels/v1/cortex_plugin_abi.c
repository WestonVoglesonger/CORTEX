/*
 * CORTEX Plugin ABI Version Implementation
 *
 * This file provides the real (non-inline) cortex_plugin_abi_version()
 * function that adapters can discover via dlsym().  It is compiled ONCE
 * at the top level and linked into all kernel shared libraries to avoid
 * build race conditions.
 *
 * Rationale: inline functions in headers may not emit discoverable symbols.
 * By compiling this as a separate object, we guarantee a real exported
 * symbol that dynamic loaders can find.
 */

#include "cortex_plugin.h"

uint32_t cortex_plugin_abi_version(void) {
    return CORTEX_ABI_VERSION;
}
