#ifndef CORTEX_ENDIAN_H
#define CORTEX_ENDIAN_H

#include <stdint.h>
#include <string.h>

/*
 * Endianness Conversion Helpers
 *
 * ALL wire format data uses little-endian encoding.
 * These helpers convert between wire format (little-endian) and host format.
 *
 * On little-endian hosts (x86, most ARM): These are no-ops (optimized out).
 * On big-endian hosts (rare): These perform byte swapping.
 *
 * CRITICAL: Always use these helpers, never cast packed structs directly.
 * This prevents alignment faults on ARM and ensures correct endianness.
 */

/* Detect host endianness */
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
#define CORTEX_HOST_IS_LITTLE_ENDIAN 1
#elif defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
#define CORTEX_HOST_IS_LITTLE_ENDIAN 0
#else
/* Fall back to runtime detection if compiler doesn't define __BYTE_ORDER__ */
#define CORTEX_HOST_IS_LITTLE_ENDIAN cortex_is_little_endian()
static inline int cortex_is_little_endian(void) {
    uint16_t val = 1;
    return *(uint8_t*)&val == 1;
}
#endif

/*
 * Byte swap functions (inline for performance)
 */
static inline uint16_t cortex_bswap16(uint16_t x) {
    return (x >> 8) | (x << 8);
}

static inline uint32_t cortex_bswap32(uint32_t x) {
    return ((x & 0x000000FFU) << 24) |
           ((x & 0x0000FF00U) <<  8) |
           ((x & 0x00FF0000U) >>  8) |
           ((x & 0xFF000000U) >> 24);
}

static inline uint64_t cortex_bswap64(uint64_t x) {
    return ((x & 0x00000000000000FFULL) << 56) |
           ((x & 0x000000000000FF00ULL) << 40) |
           ((x & 0x0000000000FF0000ULL) << 24) |
           ((x & 0x00000000FF000000ULL) <<  8) |
           ((x & 0x000000FF00000000ULL) >>  8) |
           ((x & 0x0000FF0000000000ULL) >> 24) |
           ((x & 0x00FF000000000000ULL) >> 40) |
           ((x & 0xFF00000000000000ULL) >> 56);
}

/*
 * Little-endian to host conversions
 */
static inline uint16_t cortex_le16toh(uint16_t x) {
#if CORTEX_HOST_IS_LITTLE_ENDIAN
    return x;
#else
    return cortex_bswap16(x);
#endif
}

static inline uint32_t cortex_le32toh(uint32_t x) {
#if CORTEX_HOST_IS_LITTLE_ENDIAN
    return x;
#else
    return cortex_bswap32(x);
#endif
}

static inline uint64_t cortex_le64toh(uint64_t x) {
#if CORTEX_HOST_IS_LITTLE_ENDIAN
    return x;
#else
    return cortex_bswap64(x);
#endif
}

/*
 * Host to little-endian conversions
 */
static inline uint16_t cortex_htole16(uint16_t x) {
#if CORTEX_HOST_IS_LITTLE_ENDIAN
    return x;
#else
    return cortex_bswap16(x);
#endif
}

static inline uint32_t cortex_htole32(uint32_t x) {
#if CORTEX_HOST_IS_LITTLE_ENDIAN
    return x;
#else
    return cortex_bswap32(x);
#endif
}

static inline uint64_t cortex_htole64(uint64_t x) {
#if CORTEX_HOST_IS_LITTLE_ENDIAN
    return x;
#else
    return cortex_bswap64(x);
#endif
}

/*
 * Read little-endian values from wire buffer (safe, no alignment issues)
 *
 * Usage:
 *   uint32_t magic = cortex_read_u32_le(buf);
 *   uint64_t timestamp = cortex_read_u64_le(buf + 8);
 */
static inline uint16_t cortex_read_u16_le(const uint8_t *buf) {
    uint16_t val;
    memcpy(&val, buf, sizeof(val));
    return cortex_le16toh(val);
}

static inline uint32_t cortex_read_u32_le(const uint8_t *buf) {
    uint32_t val;
    memcpy(&val, buf, sizeof(val));
    return cortex_le32toh(val);
}

static inline uint64_t cortex_read_u64_le(const uint8_t *buf) {
    uint64_t val;
    memcpy(&val, buf, sizeof(val));
    return cortex_le64toh(val);
}

static inline float cortex_read_f32_le(const uint8_t *buf) {
    /* IEEE-754 float32 has same byte layout as uint32 */
    uint32_t bits;
    memcpy(&bits, buf, sizeof(bits));
    bits = cortex_le32toh(bits);
    float val;
    memcpy(&val, &bits, sizeof(val));
    return val;
}

/*
 * Write little-endian values to wire buffer (safe, no alignment issues)
 *
 * Usage:
 *   cortex_write_u32_le(buf, magic);
 *   cortex_write_u64_le(buf + 8, timestamp);
 */
static inline void cortex_write_u16_le(uint8_t *buf, uint16_t val) {
    uint16_t le_val = cortex_htole16(val);
    memcpy(buf, &le_val, sizeof(le_val));
}

static inline void cortex_write_u32_le(uint8_t *buf, uint32_t val) {
    uint32_t le_val = cortex_htole32(val);
    memcpy(buf, &le_val, sizeof(le_val));
}

static inline void cortex_write_u64_le(uint8_t *buf, uint64_t val) {
    uint64_t le_val = cortex_htole64(val);
    memcpy(buf, &le_val, sizeof(le_val));
}

static inline void cortex_write_f32_le(uint8_t *buf, float val) {
    /* IEEE-754 float32 has same byte layout as uint32 */
    uint32_t bits;
    memcpy(&bits, &val, sizeof(bits));
    cortex_write_u32_le(buf, bits);
}

#endif /* CORTEX_ENDIAN_H */
