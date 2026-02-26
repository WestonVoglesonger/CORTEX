/*
 * CORTEX Q15 Fixed-Point Arithmetic Utilities
 *
 * Shared Q15 arithmetic for all Q15 kernel implementations.
 * Q15 format: signed Q1.15, range [-1.0, +0.999969482] stored in int16_t.
 *
 * Conventions:
 *   - All functions are static inline for zero-overhead inclusion
 *   - Multiply accumulates in int32_t (Q31) with round-to-nearest
 *   - Saturation arithmetic prevents silent wraparound
 *   - Conversion functions clamp to valid Q15 range
 *
 * Usage: #include "cortex_q15.h" in any Q15 kernel .c file.
 */

#ifndef CORTEX_Q15_H
#define CORTEX_Q15_H

#include <stddef.h>
#include <stdint.h>

#define Q15_ONE      32767
#define Q15_MINUS_ONE (-32768)
#define Q15_SHIFT    15

/* Saturating addition: clamp to [-32768, 32767] */
static inline int16_t q15_sat_add(int16_t a, int16_t b) {
    int32_t sum = (int32_t)a + (int32_t)b;
    if (sum > 32767)  return 32767;
    if (sum < -32768) return -32768;
    return (int16_t)sum;
}

/* Saturating subtraction: clamp to [-32768, 32767] */
static inline int16_t q15_sat_sub(int16_t a, int16_t b) {
    int32_t diff = (int32_t)a - (int32_t)b;
    if (diff > 32767)  return 32767;
    if (diff < -32768) return -32768;
    return (int16_t)diff;
}

/*
 * Q15 multiply with round-to-nearest:
 *   result = (a * b + 0x4000) >> 15
 *
 * Product is Q30 (int32_t), shifted right by 15 to produce Q15.
 * Rounding bias 0x4000 = 1 << 14 gives round-to-nearest behavior.
 */
static inline int16_t q15_mul(int16_t a, int16_t b) {
    int32_t product = (int32_t)a * (int32_t)b;
    int32_t rounded = (product + (1 << 14)) >> 15;
    if (rounded > 32767)  return 32767;
    if (rounded < -32768) return -32768;
    return (int16_t)rounded;
}

/* Convert float [-1.0, 1.0] to Q15. Clamps out-of-range values. */
static inline int16_t float_to_q15(float x) {
    if (x >= 1.0f)  return Q15_ONE;
    if (x <= -1.0f) return Q15_MINUS_ONE;
    /* Scale by 32768 (not 32767) to match standard Q15 conversion.
     * This means +1.0 maps to 32767 (clamped above), -1.0 maps to -32768. */
    float scaled = x * 32768.0f;
    if (scaled >= 32767.0f)  return 32767;
    if (scaled <= -32768.0f) return -32768;
    return (int16_t)(scaled + (scaled >= 0.0f ? 0.5f : -0.5f));
}

/* Convert Q15 to float. Result in [-1.0, +0.999969482]. */
static inline float q15_to_float(int16_t x) {
    return (float)x / 32768.0f;
}

/*
 * Helper: derive element size from dtype bitmask.
 * Returns sizeof(float) for float32, sizeof(int16_t) for Q15, etc.
 */
static inline size_t cortex_dtype_element_size(uint32_t dtype) {
    switch (dtype) {
        case 1u: return sizeof(float);    /* CORTEX_DTYPE_FLOAT32 */
        case 2u: return sizeof(int16_t);  /* CORTEX_DTYPE_Q15 */
        case 4u: return sizeof(int8_t);   /* CORTEX_DTYPE_Q7 */
        default: return 0;               /* unknown dtype — caller must check */
    }
}

/*
 * Helper: dtype bitmask to string name.
 */
static inline const char *cortex_dtype_name(uint32_t dtype) {
    switch (dtype) {
        case 1u: return "float32";
        case 2u: return "q15";
        case 4u: return "q7";
        default: return "unknown";
    }
}

#endif /* CORTEX_Q15_H */
