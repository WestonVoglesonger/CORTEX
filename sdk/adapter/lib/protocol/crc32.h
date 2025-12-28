#ifndef CORTEX_CRC32_H
#define CORTEX_CRC32_H

#include <stddef.h>
#include <stdint.h>

/*
 * CRC32 (IEEE 802.3 polynomial)
 *
 * Standard CRC32 used by Ethernet, ZIP, PNG, etc.
 */

/*
 * Compute CRC32 over buffer
 *
 * Args:
 *   crc: Initial CRC value (0 for first call, previous crc for continuation)
 *   buf: Data buffer
 *   len: Buffer length
 *
 * Returns: CRC32 value
 *
 * Usage:
 *   // Single buffer:
 *   uint32_t crc = cortex_crc32(0, data, len);
 *
 *   // Multiple buffers (continuation):
 *   uint32_t crc = cortex_crc32(0, header, header_len);
 *   crc = cortex_crc32(crc, payload, payload_len);
 */
uint32_t cortex_crc32(uint32_t crc, const uint8_t *buf, size_t len);

#endif /* CORTEX_CRC32_H */
