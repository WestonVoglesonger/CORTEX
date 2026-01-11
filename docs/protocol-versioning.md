# CORTEX Adapter Protocol Versioning

## Current Version

**Protocol Version:** v1
**Defined in:** `sdk/adapter/include/cortex_protocol.h` → `CORTEX_PROTOCOL_VERSION`

## Version Compatibility Policy

### v1 (Current)

**Compatibility:** Exact match required

- Harness and adapter **must** use identical protocol versions
- Version mismatch results in connection failure with error:
  ```
  [protocol] Version mismatch: received vX, expected v1
  [protocol] Protocol versions must match exactly. Rebuild adapter or harness.
  ```

**Why strict matching?**
- Wire format is not forward/backward compatible in v1
- Frame types, payload structures may change between versions
- No negotiation mechanism implemented in v1

### Version Check Location

Version validation occurs in `cortex_protocol_recv_frame()`:
- Every received frame header includes protocol version field
- Mismatch triggers `CORTEX_EPROTO_VERSION_MISMATCH` error
- Connection terminates immediately

**Code:**
```c
// sdk/adapter/lib/protocol/protocol.c:169-174
if (version != CORTEX_PROTOCOL_VERSION) {
    fprintf(stderr, "[protocol] Version mismatch: received v%u, expected v%u\n",
            version, CORTEX_PROTOCOL_VERSION);
    fprintf(stderr, "[protocol] Protocol versions must match exactly. Rebuild adapter or harness.\n");
    return CORTEX_EPROTO_VERSION_MISMATCH;
}
```

---

## Troubleshooting Version Mismatches

### Error Symptoms

**Harness-side:**
```
Failed to connect to adapter
Error: CORTEX_EPROTO_VERSION_MISMATCH
```

**Adapter-side:**
```
[protocol] Version mismatch: received v2, expected v1
[protocol] Protocol versions must match exactly. Rebuild adapter or harness.
```

### Resolution Steps

1. **Check versions:**
   ```bash
   # Harness version
   grep CORTEX_PROTOCOL_VERSION sdk/adapter/include/cortex_protocol.h

   # Adapter version (from build logs)
   make -C primitives/adapters/v1/native clean && make -C primitives/adapters/v1/native V=1
   ```

2. **Rebuild both components:**
   ```bash
   # Clean rebuild
   make clean
   make all

   # Redeploy to remote device (if using SSH deployer)
   cortex run --device user@host --kernel noop
   ```

3. **Verify matching versions:**
   - Ensure harness and adapter binaries are from same commit
   - Check git status for uncommitted changes
   - Verify remote device has latest adapter binary

### Common Causes

| Cause | Solution |
|-------|----------|
| **Partial rebuild** | Run `make clean && make all` |
| **Old adapter binary on device** | Redeploy via `cortex run --device ...` |
| **Mixed source versions** | `git status` → commit or stash changes |
| **Cached build artifacts** | `find . -name '*.o' -delete && make all` |

---

## Future: Version Negotiation (v2+)

**Planned for v2:**

- Version range negotiation during HELLO/CONFIG exchange
- Adapter advertises: `min_version=1, max_version=2`
- Harness selects: highest common version
- Downgrade protocol features if needed

**Wire format changes (v2 proposal):**
```c
// In HELLO frame payload:
typedef struct {
    uint8_t  protocol_version_min;  // Minimum supported version
    uint8_t  protocol_version_max;  // Maximum supported version
    uint8_t  protocol_version_pref; // Preferred version
    ...
} cortex_wire_hello_v2_t;

// Negotiation:
if (harness_version >= adapter_min && harness_version <= adapter_max) {
    negotiated_version = harness_version;
    // Use features from negotiated_version
}
```

**Benefits:**
- Rolling updates: upgrade harness, then adapters
- Backward compatibility: v2 harness works with v1 adapters
- Gradual migration: deprecate old versions over time

**Status:** Not implemented (v1 uses exact matching)

---

## Version History

| Version | Released | Features | Breaking Changes |
|---------|----------|----------|------------------|
| **v1** | 2025-01 | Initial protocol: HELLO, CONFIG, WINDOW, RESULT, ACK, ERROR frames. CRC32 validation, chunking, endian-safe serialization. | N/A (initial release) |
| **v2** | TBD | Version negotiation, heartbeat frame, extended error codes. | Frame payload structures extended (backward compatible via negotiation) |

---

## Developer Guidelines

### Adding New Frame Types

**If adding to v1 (not recommended):**
- Breaks compatibility → requires version bump to v2
- All existing adapters become incompatible

**Better approach:**
- Plan changes for v2 release
- Document migration path
- Implement negotiation first, then new features

### Deprecation Policy

- Support N-1 versions (v2 supports v1 via downgrade)
- Announce deprecation 6 months before removal
- Provide migration guide in CHANGELOG.md

### Testing Version Compatibility

**Unit test example:**
```c
// tests/test_protocol_version_mismatch.c
void test_version_mismatch() {
    // Harness v1, Adapter sends v2 → should fail
    // Harness v2, Adapter sends v1 → should downgrade (future)
}
```

---

## References

- **Protocol Specification**: `primitives/adapters/v1/cortex_adapter.h`
- **Wire Format**: `sdk/adapter/include/cortex_wire.h`
- **Error Codes**: `CORTEX_ERROR_VERSION_MISMATCH` (wire.h:198)
- **Implementation**: `sdk/adapter/lib/protocol/protocol.c:169-174`

---

**Last Updated:** 2026-01-11
**Status:** v1 stable, v2 planning phase
