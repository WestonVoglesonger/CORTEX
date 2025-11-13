# Platform Compatibility

## Overview

CORTEX supports cross-platform builds on macOS and Linux, enabling team collaboration across different development environments and ensuring reproducibility for academic publication.

## Why Cross-Platform Support

**Team Collaboration**: Graduate research teams use diverse development environments (MacBooks, Linux workstations, lab machines). Cross-platform support ensures all team members can build and run the harness without platform-specific barriers.

**Future HIL Development**: Hardware-in-the-Loop (HIL) development will involve various lab equipment running different operating systems. A cross-platform harness enables consistent tooling across all development environments.

**Academic Standards**: Research code must be reproducible across different environments and accessible to reviewers on various platforms.

## Implementation

### Platform Detection

**Compile-time detection** (`__APPLE__` macro):
```c
#ifdef __APPLE__
    snprintf(out_path, out_sz, "plugins/lib%s.dylib", clean);
#else
    snprintf(out_path, out_sz, "plugins/lib%s.so", clean);
#endif
```

**Build-time detection** (`uname -s`):
```makefile
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    LDFLAGS = -lpthread -lm
else
    LDFLAGS = -ldl -lpthread -lm
endif
```

### Platform Differences

| Aspect | macOS | Linux |
|--------|-------|-------|
| **Plugin Extension** | `.dylib` | `.so` |
| **Build Flag** | `-dynamiclib` | `-shared -fPIC` |
| **Linker Flags** | `-lpthread -lm` | `-ldl -lpthread -lm` |
| **dlopen Location** | Built into libSystem | Separate libdl library |

**Key insight**: macOS does not require `-ldl` because `dlopen()`/`dlsym()` are part of libSystem.dylib. Linux requires explicit `-ldl` linking.

### Makefile Pattern

All kernel Makefiles use this pattern:

```makefile
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    SOFLAG = -dynamiclib
    LIBEXT = .dylib
else
    SOFLAG = -shared
    LIBEXT = .so
endif

TARGET = lib$(KERNEL_NAME)$(LIBEXT)
$(TARGET): $(KERNEL_NAME).c
	$(CC) $(CFLAGS) $(SOFLAG) -o $@ $< $(LDFLAGS)
```

## Platform-Specific Notes

### macOS

**Prerequisites**:
- macOS 10.15+ (Catalina or later)
- Xcode Command Line Tools: `xcode-select --install`
- Standard C11 compiler (clang)

**Build**:
```bash
make clean && make
```

**Verify**:
```bash
otool -L cortex
# Should show: /usr/lib/libSystem.B.dylib only
```

### Linux

**Prerequisites**:
- GCC or Clang with C11 support
- Libraries: `libpthread`, `libdl`, `libm`

**Build**:
```bash
make clean && make
```

**Verify**:
```bash
ldd cortex
# Should show: libdl.so, libpthread.so, libm.so
```

### Real-Time Scheduling Differences

**macOS**:
- Real-time scheduling (SCHED_FIFO, SCHED_RR) not supported
- Harness logs warning and continues with standard scheduling
- Benchmarks run normally, but without RT priority

**Linux**:
- Full SCHED_FIFO and SCHED_RR support
- Requires elevated privileges or capabilities:
  ```bash
  sudo setcap cap_sys_nice=eip ./src/engine/harness/cortex
  ```

## Troubleshooting

### Plugin Not Found

**macOS**: Verify `.dylib` extension
```bash
ls primitives/kernels/v1/*/lib*.dylib
```

**Linux**: Verify `.so` extension
```bash
ls primitives/kernels/v1/*/lib*.so
```

### Linker Errors

**macOS**: Should NOT have `-ldl` flag
```bash
# Check Makefile conditionals
make -n | grep LDFLAGS
# Expected: -lpthread -lm (no -ldl)
```

**Linux**: MUST have `-ldl` flag
```bash
make -n | grep LDFLAGS
# Expected: -ldl -lpthread -lm
```

### Platform Detection Failures

Check platform detection:
```bash
uname -s                                    # Should show: Darwin or Linux
gcc -dM -E - < /dev/null | grep __APPLE__  # macOS: shows #define, Linux: no output
```

### Build Warnings

**Known issue** (macOS): NSEC_PER_SEC macro redefinition warning is harmless and can be ignored.

## Future Considerations

**Windows support**: Would require `.dll` extension, `LoadLibrary()` API, and `#ifdef _WIN32` conditionals. Currently out of scope.

**BSD support**: Would require additional `uname -s` cases for FreeBSD/OpenBSD. Currently out of scope.

**Universal binaries** (macOS): Could add `-arch arm64 -arch x86_64` for Intel+Apple Silicon support if needed.

## References

- [System Overview](overview.md) - Architecture and execution model
- [Plugin Interface](../reference/plugin-interface.md) - Plugin ABI specification
- [Troubleshooting Guide](../guides/troubleshooting.md) - Common build issues

## Implementation Status

**Completed**:
- Cross-platform plugin extension detection
- Platform-specific linker flags
- Build system platform detection
- macOS and Linux support verified

🔄 **Future** (out of scope):
- Windows support
- BSD support
- CI/CD cross-platform testing
